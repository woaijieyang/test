"""Public episode storage API: one paged writer and compatible pinned readers."""
from pathlib import Path
from collections.abc import Mapping
import os,json,sqlite3,hashlib,fcntl,uuid
import numpy as np
from . import archive as legacy
from .archive import (StorageError,IntegrityError,ConcurrentWriterError,NoPublishedSnapshot,VersionUnavailable,canonical,digest,file_hash,sync_dir,freeze,array_descriptor,encode_arrays,decode_arrays,ByteLRU,_safe_uid,_owned,_file_ref,_verify_ref,_write_immutable,owned_references,read_manifest,semantic_reference_checks)
from .pages import BundlePages,SelectiveReader,ImmutableVerifier,FactMaterializer,Pinned,read_revision,decode_page
_PARENT_UNSET=object()

def identity(epoch,native_id):return epoch+':'+str(native_id)

def clip_detection_box(box, image_shape, *, legacy_integer=False):
    """Return original pixels and their intersection with the original image."""
    box = np.asarray(box, dtype=float)
    if box.shape != (4,) or not np.isfinite(box).all():
        return None
    x0, y0, x1, y1 = box
    if x0 >= x1 or y0 >= y1:
        return None
    height, width = image_shape[:2]
    start, end = (int, int) if legacy_integer else (np.floor, np.ceil)
    a = max(0, min(width, int(start(x0))))
    b = max(0, min(height, int(start(y0))))
    c = max(0, min(width, int(end(x1))))
    d = max(0, min(height, int(end(y1))))
    return (a,b,c,d) if a<c and b<d else None
class WriteLedger:
 """One writer accounts known immutable files;mutable SQL/WAL headers use stat."""
 def __init__(self,root):
  self.root=Path(root);self.immutable={};self.new_file_bytes=0;self.appended_log_bytes=0;self.reconciliations=0
  self.mutable={"CURRENT.json","execution.jsonl","updates.jsonl","errors.jsonl",
      "episode_scope.json","episode_summary.json","FAILED.json","writer.lock","page-writer.lock","pins.lock"}
  self.calls=0;self.scan_initial()
 def is_mutable(self,path):
  return path.name in self.mutable or path.name.startswith(("index.sqlite3","pages.sqlite3"))
 def scan_initial(self):
  for p in self.root.rglob("*"):
   if p.is_file()and not self.is_mutable(p)and".pending"not in p.parts and not p.name.endswith(".CURRENT.tmp"):
    self.immutable[str(p.relative_to(self.root))]=p.stat().st_size
 def note(self,path):
  path=Path(path);size=path.stat().st_size
  if self.is_mutable(path):return
  key=str(path.relative_to(self.root))
  old=self.immutable.get(key)
  if old is not None and old!=size:raise legacy.IntegrityError("Immutable file size changed")
  if old is None:self.immutable[key]=size;self.new_file_bytes+=size
 def total(self):
  self.calls+=1
  mutable={p for name in self.mutable if(p:=self.root/name).is_file()}
  for stem in("index.sqlite3","pages.sqlite3"):mutable.update(self.root.glob(stem+"*"))
  pending=list((self.root/".pending").glob("*"))+list(self.root.glob("*.CURRENT.tmp"))
  return sum(self.immutable.values())+sum(p.stat().st_size for p in mutable if p.is_file())+sum(p.stat().st_size for p in pending if p.is_file())
 def reconcile(self):
  estimate=self.total();actual=sum(p.stat().st_size for p in self.root.rglob("*")if p.is_file())
  self.reconciliations+=1
  if actual!=estimate:raise legacy.IntegrityError("Incremental file accounting differs from periodic/terminal scan: "+repr((estimate,actual)))
  return actual
class EpisodeStore(legacy.RawArchive):
 """Reuse one raw archive implementation;only derived revision storage changes."""
 def __init__(self,*args,**kwargs):
  point=Path(args[0])/"CURRENT.json" if args else Path(kwargs["path"])/"CURRENT.json"
  if point.exists() and json.loads(point.read_bytes()).get("storage_codec")!="literal_history_v1":
   raise VersionUnavailable("Legacy episodes are read-only; start a new owned attempt")
  self._contracts={};self._contract_refs={}
  budget=kwargs.pop("cache_bytes",128*1024*1024)
  self.pages=None;self.raw_materializer=None
  try:
   super().__init__(*args,cache_bytes=budget//2,**kwargs)
   self.pages=BundlePages(self.root,create=False)
   from .replay import recover_replay_scratch
   recover_replay_scratch(self)
   self._facts={};self._executions={};self._entities={};self._aliases={};self._execution_posts=set()
   self._verified=ImmutableVerifier();self.ledger=WriteLedger(self.root)
   self._raw_refs={}
   self.raw_materializer=FactMaterializer(self.root,self._raw_refs,metadata_bytes=budget//4,image_bytes=budget//4)
   if self.current is not None:
    reader=SelectiveReader(self.root)
    try:
     bundle=reader.graph();self._facts=bundle['facts'];self._executions=bundle['executions']
     self._entities=bundle['entities'];self._aliases=bundle['aliases'];self._execution_posts={x['post']for x in self._executions.values()}
    finally:reader.close()
  except BaseException:
   self.close();raise
 def _index_raw(self,record,meta_ref):
  super()._index_raw(record,meta_ref)
  uid=record["frame_uid"]
  row=self.connection.execute("SELECT refs FROM observations WHERE uid=?",(uid,)).fetchone()
  expected=json.loads(row[0])["meta"]
  if expected["sha256"]!=meta_ref["sha256"]or expected["bytes"]!=meta_ref["bytes"]:
   raise legacy.IntegrityError("Raw contract metadata differs from immutable source index")
  self._contract_refs[uid]=expected
  self._contracts[uid]=legacy.freeze(dict(capture_seq=record["capture_seq"],event_seq=record["event_seq"],
     pose_record=dict(geometry_status=record.get("pose_record",{}).get("geometry_status"))))
 def raw_contract(self,uid):
  if uid not in self._contracts:raise KeyError(uid)
  self._verified.verify(self.root,self._contract_refs[uid])
  return self._contracts[uid]
 def raw(self,uid):
  if not hasattr(self,"raw_materializer"):return super().raw(uid)
  if uid not in self._raw_refs:
   row=self.connection.execute("SELECT refs FROM observations WHERE uid=?",(uid,)).fetchone()
   if row is None:raise KeyError(uid)
   self._raw_refs[uid]=json.loads(row[0])
  return self.raw_materializer.capture(uid)
 def read_rgb(self,uid,*,host=False):
  if uid not in self._raw_refs:self.raw(uid)
  return self.raw_materializer.image(self._raw_refs[uid]["host_view" if host else "rgb"])
 def open_reader(self,revision="CURRENT",**kwargs):
  return load_episode(self.root,revision,**kwargs)
 def put_arrays(self,arrays):
  ref=super().put_arrays(arrays)
  if hasattr(self,"ledger"):self.ledger.note(self.root/ref["path"])
  return ref
 def import_replay_blob(self,source,ref):
  """Install validated replay output without re-encoding its bytes."""
  rel=ref["path"]
  if rel!=f'blobs/{ref["sha256"]}.npz':
   raise legacy.IntegrityError("Unexpected content-addressed replay path")
  staged=_verify_ref(source,ref)
  target=_owned(self.root,rel)
  existed=target.is_file()
  actual=_write_immutable(self.root,rel,staged.read_bytes(),stage="replay_blob")
  if any(actual[k]!=ref[k]for k in ("path","sha256","bytes")):
   raise legacy.IntegrityError("Replay promotion changed immutable identity")
  self.ledger.note(target)
  return 0 if existed else actual["bytes"]
 def archive_frame(self,*args,**kwargs):
  value=super().archive_frame(*args,**kwargs)
  if hasattr(self,"ledger"):
   for ref in value["files"].values():
    if ref is not None:self.ledger.note(self.root/ref["path"])
   self.ledger.note(self.root/"observations"/(value["frame_uid"]+".meta.json"))
  return value
 def save_detections(self,frame_uid,arrays,metadata):
  result=super().save_detections(frame_uid,arrays,metadata)
  if hasattr(self,"ledger"):
   self.ledger.note(self.root/"detections"/(frame_uid+".meta.json"));self.ledger.note(self.root/"detections"/(frame_uid+".npz"))
  return result
 def register_rendered_outputs(self):
  # The renderer is the only registered terminal producer outside the store.
  folder=self.root/"visualizations"
  for path in folder.rglob("*"):
   if path.is_file():self.ledger.note(path)
 def accounted_bytes(self,*,terminal=False):
  if terminal or self.ledger.calls%64==63:return self.ledger.reconcile()
  return self.ledger.total()
 def publish(self,graph,versions,cutoff,*,fault=None,expected_parent_id=_PARENT_UNSET):
  self._validate_graph(graph,versions,cutoff)
  parent=self._pointer()
  if parent!=self.current:raise legacy.ConcurrentWriterError('Stale paged parent')
  if expected_parent_id is not _PARENT_UNSET and (parent['snapshot_id'] if parent else None)!=expected_parent_id:
   raise legacy.ConcurrentWriterError('Prepared snapshot base is no longer CURRENT')
  if parent is not None:
   # Late derived work must not erase newly admitted observations. Correction
   # may publish at the same cutoff, but may never move the public frontier back.
   for field in ('capture_seq','event_seq'):
    value=cutoff.get(field)
    if type(value)is not int or value<parent['cutoff'][field]:
     raise legacy.VersionUnavailable('Publication cutoff regressed: '+field)
   previous_version=parent['versions'].get('pose_map_version')
   next_version=versions.get('pose_map_version')
   if previous_version is not None and (type(next_version)is not int or next_version<previous_version):
    raise legacy.VersionUnavailable('Publication pose version regressed')
   if not set(self._facts).issubset(graph['views']):
    raise legacy.IntegrityError('Publication drops committed observations')
  facts=dict(self._facts);executions=dict(self._executions);queried=set(self._execution_posts)
  changes=dict(facts={},executions={},entities={},aliases={})
  for uid in graph['views']:
   if uid not in facts:
    row=self.connection.execute('SELECT refs FROM observations WHERE uid=?',(uid,)).fetchone()
    if row is None:raise legacy.IntegrityError('Missing raw source')
    facts[uid]=json.loads(row[0]);changes['facts'][uid]=facts[uid]
   if uid not in queried:
    for eid,payload in self.connection.execute('SELECT id,result FROM executions WHERE post=?',(uid,)):
     previous=executions.setdefault(eid,json.loads(payload));changes['executions'][eid]=previous
     if canonical(previous)!=payload.encode():raise legacy.IntegrityError('Execution immutable source differs')
    queried.add(uid)
  entities=dict(self._entities);aliases=dict(self._aliases)
  for entity in graph.get('entities',[]):
   key=identity(entity['epoch'],entity['id']);row=json.loads(canonical(entity))
   entities[key]=row;changes['entities'][key]=row
  for alias in graph.get('aliases',[]):
   key=identity(alias['epoch'],alias['src']);row=json.loads(canonical(alias))
   aliases[key]=row;changes['aliases'][key]=row
  refs=legacy.owned_references(dict(graph=graph,facts=facts))
  for ref in refs:self._verified.verify(self.root,ref)
  public=dict(versions=versions,cutoff=cutoff,episode_uid=self.episode_uid,storage_codec="literal_history_v1")
  bundle=dict(graph=graph,facts=facts,executions=executions,entities=entities,aliases=aliases,public=public)
  before=self.pages.pointer()
  try:pointer=self.pages.publish(bundle,digest(canonical(public)),public=public,changes=changes,fault=fault)
  except BaseException:
   actual=self.pages.pointer()
   if actual!=before:
    self.current=actual;self._facts=facts;self._executions=executions;self._entities=entities;self._aliases=aliases;self._execution_posts=queried
   raise
  self.current=pointer;self._facts=facts;self._executions=executions;self._entities=entities;self._aliases=aliases;self._execution_posts=queried
  if fault:fault("memory_installed")
  return pointer
 def evict_caches(self):
  """Drop only decoded caches; immutable facts and writer state remain."""
  if getattr(self,'cache',None)is not None:self.cache.clear()
  if getattr(self,'raw_materializer',None)is not None:
   self.raw_materializer.close();self.raw_materializer.verifier.cache.clear()
  if getattr(self,'_verified',None)is not None:self._verified.cache.clear()
  return dict(decoded_arrays=0,raw_metadata=0,raw_images=0,verification_cache=0)
 def release_audit(self):
  """Inspect actual store closure; native pose has a separate owner."""
  counts={name:len(getattr(self,name,())or())for name in
   ('_facts','_executions','_entities','_aliases','_execution_posts','_raw_refs','_contracts','_contract_refs')}
  closed=all(getattr(self,name,None)is None for name in('connection','_lock','pages','raw_materializer'))
  pins_zero=False
  guard=self.root/'pins.lock'
  if guard.exists():
   with guard.open('rb')as handle:
    try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);pins_zero=True
    except BlockingIOError:pass
  return dict(memory_closed=closed,cache_entries=counts,pins_zero=pins_zero,
   native_closed=None,scope='memory store only; native closure needs owner receipt')
 def close(self):
  if getattr(self,'pages',None)is not None:self.pages.close();self.pages=None
  if getattr(self,'raw_materializer',None)is not None:
   self.raw_materializer.close();self.raw_materializer=None
  for name in ("_facts","_executions","_entities","_aliases","_execution_posts","_raw_refs","_contracts","_contract_refs"):
   value=getattr(self,name,None)
   if value is not None:value.clear()
  verifier=getattr(self,"_verified",None)
  if verifier is not None:verifier.cache.clear()
  super().close()
class PinnedMap(Mapping):
    """A pinned content-addressed map; individual lookups do not expand siblings."""
    def __init__(self, pages, name):
        self.pages, self.name = pages, name
    def __getitem__(self, key):
        return self.pages.lookup((self.name, key))
    def __iter__(self):
        return iter(self.pages.lookup((self.name,)))
    def __len__(self):
        return len(self.pages.lookup((self.name,)))
    def values(self):
        return self.pages.lookup((self.name,)).values()
    def items(self):
        return self.pages.lookup((self.name,)).items()
DEFAULT_SNAPSHOT_CACHE_BYTES=128*1024*1024

class SnapshotReader:
 def __init__(self, path, revision='CURRENT', *, cache_bytes=DEFAULT_SNAPSHOT_CACHE_BYTES, _history_cache=None, feature_cache=None, image_cache=None):
     self.root = Path(path)
     # Capture one visibility header. A concurrent publication may advance CURRENT
     # later; the captured revision stays an allowed ancestor under reader pins.
     pointer = json.loads((self.root/'CURRENT.json').read_bytes()) if revision == 'CURRENT' else None
     target = pointer['snapshot_id'] if pointer is not None else revision
     self.pages = SelectiveReader(self.root, target, cache_bytes//2)
     try:
         self.identity = json.loads((self.root/'episode_identity.json').read_bytes())
         self.history_page_cache=_history_cache
         if _history_cache is not None:
             from .pages import HistoryPageCache
             if not isinstance(_history_cache,HistoryPageCache):raise TypeError('Typed history cache required')
             _history_cache.bind(self.root,self.identity['episode_uid'])
             self.pages._history_cache=_history_cache
             if _history_cache.episode is not None:self.pages._checked_shared_keys=set()
         self.snapshot_id = self.pages.sid
         self.__graph = None
         self._facts = PinnedMap(self.pages, 'facts')
         self._executions = PinnedMap(self.pages, 'executions')
         self._entities = PinnedMap(self.pages, 'entities')
         self._aliases = PinnedMap(self.pages, 'aliases')
         public = self.pages.lookup(('public',))
         expected_source = digest(canonical([digest(canonical(public)), digest(canonical(public))]))
         if self.pages.source_id != expected_source:
             raise legacy.IntegrityError('Public contract differs from revision identity')
         if pointer is not None:
             basis = dict(schema_version=2, parent=self.pages.parent, root=self.pages.root_node,
                 logical_hash=self.pages.logical_hash, context=self.pages.context,
                 source_id=self.pages.source_id, ordinal=self.pages.ordinal,
                 snapshot_id=self.snapshot_id, **public)
             if canonical(pointer) != canonical(basis):
                 raise legacy.IntegrityError('Pointer public contract or revision header differs from signed state')
         self.versions, self.cutoff = legacy.freeze(public['versions']), legacy.freeze(public['cutoff'])
         if public['episode_uid'] != self.identity['episode_uid']:
             raise legacy.IntegrityError('Episode identity')
         if image_cache is not None:image_cache.bind(self.root,self.identity['episode_uid'])
         self.materializer = FactMaterializer(self.root, self._facts,image_cache=image_cache,
             metadata_bytes=cache_bytes//4, image_bytes=cache_bytes//4)
         self.verifier = self.materializer.verifier
         from .features import EpisodeFeatureCache
         if feature_cache is not None and (not isinstance(feature_cache,EpisodeFeatureCache) or feature_cache.closed or feature_cache.root != self.root.resolve()):
             raise IntegrityError('Feature cache must belong to this episode root')
         self._owns_feature_cache = feature_cache is None
         self._feature_cache = feature_cache if feature_cache is not None else EpisodeFeatureCache(self.root)
     except BaseException:
         self.pages.close()
         raise
 @property
 def _graph(self):
     if self.__graph is None:
         self.__graph = self.pages.lookup(('graph',))
     return self.__graph
 @property
 def manifest(self):
     facts = self.pages.lookup(('facts',))
     return dict(schema_version=2, snapshot_id=self.snapshot_id,
         versions=dict(self.versions), cutoff=dict(self.cutoff),
         observations=[dict(uid=uid, refs=refs) for uid, refs in facts.items()],
         files=legacy.owned_references(dict(graph=self._graph, facts=facts)))

 def iter_verified_history(self,*,page_cache_bytes=None):
  """Cold-check every ancestor, reusing verified raw pages only within this audit."""
  from .pages import HistoryPageCache
  cache=HistoryPageCache(self.root,self.pages.limit if page_cache_bytes is None else page_cache_bytes)
  sid=self.snapshot_id;seen_revisions=set();seen_nodes=set();seen_files=set()
  previous_cutoff=None;complete=False;bytes_before=self.verifier.bytes_read
  try:
   while sid is not None:
    if sid in seen_revisions:raise IntegrityError("Revision parent cycle")
    seen_revisions.add(sid)
    row=read_revision(self.pages.db,sid);parent,root=row[:2]
    queue=[root]
    while queue:
     key=queue.pop()
     if key in seen_nodes:continue
     _,children,_=cache.read(self.pages.db,key);seen_nodes.add(key);queue.extend(children)
    historical=SnapshotReader(self.root,sid,_history_cache=cache)
    try:
     graph=historical._graph;versions=dict(historical.versions);cutoff=dict(historical.cutoff)
     checks=legacy.semantic_reference_checks(graph,versions)
     if checks["errors"]:raise IntegrityError("Historical semantic reference violation: "+",".join(checks["errors"]))
     if previous_cutoff is not None and any(cutoff[k]>previous_cutoff[k]for k in ("capture_seq","event_seq")):
      raise IntegrityError("Historical cutoff exceeds pinned parent chain")
     manifest=historical.manifest
     for ref in manifest["files"]:
      key=(ref["path"],ref["sha256"],ref["bytes"])
      if key not in seen_files:
       # Same-reader receipts are valid only while device/inode/size/mtime/ctime
       # match. New or changed files still receive a full SHA verification.
       self.verifier.verify(self.root,ref);seen_files.add(key)
     yield dict(snapshot_id=sid,parent=parent,graph=graph,versions=versions,cutoff=cutoff,
      verified_unique_files=len(seen_files),verified_unique_pages=len(seen_nodes))
     previous_cutoff=cutoff
    finally:historical.close()
    sid=parent
   complete=True
  finally:
   self.last_history_audit=dict(complete=complete,cache_limit_bytes=cache.limit,
    peak_cache_bytes=cache.peak_bytes,cache_hits=cache.hits,decoded_pages=cache.decodes,
    verified_unique_pages=len(seen_nodes),verified_unique_files=len(seen_files),
    file_bytes_read=self.verifier.bytes_read-bytes_before)
   cache.clear()

 def require_pose_version(self,episode_uid,map_version):
  if episode_uid!=self.identity['episode_uid']or map_version!=self.versions['pose_map_version']:
   raise legacy.VersionUnavailable('Pinned pose revision differs')
 def get_view(self,uid,*,include_images=True,include_depth=False):
  if uid not in self._graph['views']:raise KeyError(uid)
  return self.materializer.view(uid,self._graph['views'][uid],self.snapshot_id,images=include_images,depth=include_depth)
 def get_camera_pose_view(self,uid):
  """Resolve one pinned camera row and its immutable capture without loading any scene layers."""
  keys=('frame_uid','capture_seq','source_event_seq','env_step','pose_map_version','pose_binding','T_G_cv')
  row={key:self.pages.lookup(('graph','views',uid,key)) for key in keys}
  capture=self.materializer.capture(uid)
  fields=('episode_uid','frame_uid','capture_seq','event_seq','env_step','sensor_timestamp_ns',
          'pose_provider','pose_record','T_base_camera','calibration_hash')
  return legacy.freeze(dict(row,capture={key:capture[key] for key in fields},snapshot_id=self.snapshot_id))
 def get_retrieval_index(self):
  graph=self._graph
  return legacy.freeze(dict(view_uids=tuple(sorted(graph['views'])),
   model_identity=graph.get('model_identity',{}),edges=graph.get('edges',()),
   entities=[dict(epoch=e['epoch'],id=e['id'],status=e['status'],view_uids=e.get('view_uids',()))for e in graph.get('entities',())],
   anchors=graph.get('vsm',{}).get('anchors',{}),
   visibility_edges=graph.get('vsm',{}).get('visibility_edges',()),
   scene_epoch=graph.get('scene_state',{}).get('epoch')))
 def get_retrieval_view(self,uid,*,verify_images=True):
  from ..retrieval.contracts import ViewRef
  view=self._graph['views'][uid]
  refs=self._facts[uid]
  capture=self.materializer.capture(uid)
  if (capture['episode_uid']!=self.identity['episode_uid'] or capture['frame_uid']!=uid
      or view['frame_uid']!=uid or capture['capture_seq']!=view['capture_seq']):
   raise IntegrityError('Retrieval view/capture identity differs')
  rgb,host=refs['rgb'],refs['host_view']
  if rgb is None or host is None:return None
  if verify_images:
   self._feature_cache.verifier.verify(self.root,rgb)
   self._feature_cache.verifier.verify(self.root,host)
  if not hasattr(self,'_retrieval_entity_index'):
   index={}
   for entity in self._graph.get('entities',()):
    for frame in entity.get('view_uids',()):index.setdefault(frame,[]).append((entity['epoch'],entity['id']))
   self._retrieval_entity_index={frame:tuple(sorted(values))for frame,values in index.items()}
  entities=self._retrieval_entity_index.get(uid,())
  position=view.get('position_G')
  if position is not None:
   position=np.asarray(position,dtype=float)
   if position.shape!=(3,)or not np.isfinite(position).all():raise IntegrityError('Invalid estimated view position')
   position=tuple(float(x)for x in position)
  def plain(value):
   if isinstance(value,Mapping):return {k:plain(v)for k,v in value.items()}
   if isinstance(value,(tuple,list)):return [plain(v)for v in value]
   return value
  return ViewRef(self.identity['episode_uid'],self.snapshot_id,uid,view['capture_seq'],capture['event_seq'],
    capture['env_step'],rgb['sha256'],host['sha256'],position,view.get('pose_map_version'),entities,
    view.get('room_type_hint'),digest(canonical(plain(capture.get('host_transform')))),source_snapshot_id=self.snapshot_id)
 def get_observed_doors(self,uid,*,include_masks=True):
  from .features import observed_doors
  return observed_doors(self,uid,include_masks=include_masks)
 def get_view_feature_reference(self,uid):
  from .features import feature_reference
  return feature_reference(self,uid)
 def get_view_class_ids(self,uid,*,include_boxes=False,include_confidence=False):
  from .features import view_class_ids
  return view_class_ids(self,uid,include_boxes=include_boxes,include_confidence=include_confidence)
 def get_view_features(self,uid):
  from .features import view_features
  return view_features(self,uid)
 def get_geometry(self,tile_id,revision=None):
  if revision is not None and revision!=self.snapshot_id:raise legacy.VersionUnavailable('Pinned revision')
  tile=self._graph.get('tiles',{}).get(tile_id)
  if tile is None:raise KeyError(tile_id)
  if tile['pose_map_version']!=self.versions['pose_map_version']:raise legacy.IntegrityError('Tile version')
  ref=tile['record']['blob'];arrays=legacy.decode_arrays(self.verifier.verify(self.root,ref),ref['arrays'])
  return legacy.freeze(dict(submap_id=tile_id,snapshot_id=self.snapshot_id,pose_map_version=tile['pose_map_version'],
   metadata=tile['record']['meta'],arrays=arrays,array_origin_Nlocal=[0.,0.,0.],core_cells=tile['record']['meta']['core_cells']))
 def get_object(self,epoch,native_id,revision=None):
  if revision is not None and revision!=self.snapshot_id:raise legacy.VersionUnavailable('Pinned revision')
  requested=(epoch,native_id);seen=set()
  while True:
   key=identity(epoch,native_id)
   if key in seen:raise legacy.IntegrityError('Alias cycle')
   seen.add(key);alias=self._aliases.get(key)
   if alias is None:break
   if alias.get('status')=='ambiguous':return legacy.freeze(dict(status='ambiguous',requested=requested,candidates=alias['candidates'],snapshot_id=self.snapshot_id))
   if alias.get('dst')is None:break
   epoch,native_id=alias['dst_epoch'],alias['dst']
  row=self._entities.get(identity(epoch,native_id))
  if row is None:raise KeyError((epoch,native_id))
  current_epoch=self._graph.get('scene_state',{}).get('epoch')
  if current_epoch is not None and row['epoch']!=current_epoch and row['status']=='active':
   raise legacy.IntegrityError('Historical active object has no transition')
  result = dict(row,requested=requested,snapshot_id=self.snapshot_id,
     source_revision=row.get('source_revision',self.snapshot_id))
  attributes = row.get('attributes')
  if row['status'] == 'active' and isinstance(attributes, Mapping):
   current_class = attributes.get('class_name')
   if isinstance(current_class, str):
    # Read legacy entity rows with the current aggregate class, without rewriting a snapshot.
    historical = row.get('historical_class_name', row.get('class_name'))
    if historical is not None:
     result['historical_class_name'] = historical
    result['class_name'] = current_class
  return legacy.freeze(result)
 def get_object_evidence(self,epoch,native_id,*,frame_uid=None,detection_index=None,revision=None):
  """Read all original detection members, or select an exact frame and index."""
  if detection_index is not None and (frame_uid is None or type(detection_index) is not int or detection_index<0):
   raise ValueError("Detection index must be a nonnegative integer with a frame UID")
  if frame_uid is not None and (not isinstance(frame_uid,str) or not frame_uid):
   raise ValueError("Frame UID must be a nonempty string")
  obj=self.get_object(epoch,native_id,revision=revision)
  result=dict(object=obj,snapshot_id=self.snapshot_id,sources=[],independent_rgbd_observations=0,
              ambiguities=[],label_scope="Aggregate object label; original detection class IDs are provenance")
  from .evidence_claims import describe_association
  result.update(describe_association(obj,[],filtered=frame_uid is not None))
  if obj['status']!='active':
   if frame_uid is not None:raise KeyError((frame_uid,detection_index))
   if obj['status']=='ambiguous':result['ambiguities'].append('ambiguous_object_alias')
   return legacy.freeze(result)
  selected={}
  for member in obj.get('members',()):
   uid,sep,index=member.rpartition(':d')
   if not sep or not uid or not index.isascii() or not index.isdecimal():
    raise IntegrityError("Invalid object detection member identity")
   ix=int(index)
   if frame_uid is not None and uid!=frame_uid:continue
   if detection_index is not None and ix!=detection_index:continue
   selected.setdefault(uid,[]).append((ix,member))
  if frame_uid is not None and not selected:raise KeyError((frame_uid,detection_index))
  hashes=set();classes=set()
  for uid,members in sorted(selected.items(),key=lambda x:self._graph['views'][x[0]]['capture_seq']):
   view=self.get_view(uid,include_images=True,include_depth=False)
   self.require_pose_version(view['capture']['episode_uid'],view['pose_map_version'])
   rgb=view['raw_rgb']; detection=view.get('detection_record')
   if rgb is None or not detection:raise IntegrityError("Object evidence lacks RGB or detection material")
   ref=detection['blob'];arrays=decode_arrays(self.verifier.verify(self.root,ref),ref['arrays'])
   raw_rgb=view['raw_rgb_ref'];depth=view['capture']['files']['depth']
   if raw_rgb is None or depth is None:raise IntegrityError("Object evidence lacks original RGB-D references")
   endpoint=(raw_rgb['sha256'],depth['sha256'])
   hashes.add(endpoint)
   if len(members)>1 and 'multiple_detections_same_frame' not in result['ambiguities']:
    result['ambiguities'].append('multiple_detections_same_frame')
   for ix,member in sorted(members):
    if ix>=len(arrays['xyxy']):raise IntegrityError("Object detection index is outside the source record")
    raw_box=np.asarray(arrays['xyxy'][ix],dtype=float)
    bounds=clip_detection_box(raw_box,rgb.shape)
    class_id=int(arrays['class_id'][ix]);classes.add(class_id)
    original_box=raw_box.tolist() if raw_box.shape==(4,) and np.isfinite(raw_box).all() else None
    crop=None
    if bounds is not None:
     a,b,c,d=bounds;crop=rgb[b:d,a:c].copy()
    elif 'source_crop_unavailable' not in result['ambiguities']:
     result['ambiguities'].append('source_crop_unavailable')
    result['sources'].append(dict(member=member,frame_uid=uid,detection_index=ix,
     capture_seq=view['capture_seq'],source_class_id=class_id,confidence=float(arrays['confidence'][ix]),
     original_box=original_box,crop_box=bounds,crop=crop,
     crop_status='available' if crop is not None else 'invalid_or_empty_box',
     raw_rgb_ref=raw_rgb,raw_depth_ref=depth,pose_map_version=view['pose_map_version']))
  if len(classes)>1:result['ambiguities'].append('mixed_source_classes')
  result['source_class_ids']=sorted(classes)
  result['source_class_vocabulary_sha256']=self._graph.get('model_identity',{}).get('vocabulary_sha256')
  result['independent_rgbd_observations']=len(hashes)
  result.update(describe_association(obj,result['sources'],filtered=frame_uid is not None))
  return legacy.freeze(result)
 def get_trace(self,start=0,end=None):
  end=self.cutoff['capture_seq']if end is None else min(end,self.cutoff['capture_seq'])
  if end<start:return legacy.freeze([])
  # The writer already keys execution records by episode and post-frame ID.
  # Narrow windows can use those pinned page keys without expanding every
  # execution. Full scans retain the existing fast bulk path.
  if type(start)is int and type(end)is int and (end-start+1)*2 < self.cutoff['capture_seq']:
   selected=sorted((view['capture_seq'],uid) for uid,view in self._graph['views'].items()
                   if start<=view['capture_seq']<=end)
   rows=[]
   for seq,uid in selected:
    key=digest(canonical(dict(episode_uid=self.identity['episode_uid'],post=uid)))
    execution=self._executions.get(key)
    if execution is not None:
     if execution['post']!=uid:raise IntegrityError('Pinned execution key and source frame disagree')
     rows.append(execution)
   return legacy.freeze(rows)
  values=[]
  for value in self._executions.values():
   post=value['post']
   if post not in self._graph['views']:continue
   seq=self._graph['views'][post]['capture_seq']
   if start<=seq<=end:values.append((seq,value))
  return legacy.freeze([value for _,value in sorted(values,key=lambda x:x[0])])
 def verify(self,*,hashes=True,references=True):
  # Force re-expand/hash the canonical bundle.Cold/seal reads bypass node/file caches.
  fresh=self.pages.graph(force=hashes)
  if canonical(fresh['graph'])!=canonical(self._graph):raise legacy.IntegrityError('Pinned logical graph mutated')
  checks=legacy.semantic_reference_checks(self._graph,self.versions)if references else None
  if checks and checks['errors']:raise legacy.IntegrityError(','.join(checks['errors']))
  files=0
  if hashes:
   for ref in self.manifest['files']:self.verifier.verify(self.root,ref,force=True);files+=1
  return dict(status='VERIFIED',snapshot_id=self.snapshot_id,views=len(self._graph['views']),
   verified_files=files,reference_checks=checks,scope='Pinned content-addressed snapshot')
 def close(self):
  if getattr(self,"_owns_feature_cache",False):self._feature_cache.close()
  if getattr(self,"pages",None)is not None:self.pages.close();self.pages=None
  if getattr(self,"materializer",None)is not None:self.materializer.close();self.materializer=None
  self.__graph=None

def load_episode(path,revision="CURRENT",**kwargs):
    pointer=Path(path)/"CURRENT.json"
    if not pointer.exists():raise NoPublishedSnapshot("No committed snapshot")
    header=json.loads(pointer.read_bytes())
    if header.get("schema_version")==1:
        kwargs.pop('image_cache',None)
        kwargs.pop('_history_cache',None)
        return legacy.LegacySnapshotReader(path,revision,**kwargs)
    if header.get("schema_version")!=2:raise IntegrityError("Unknown storage schema")
    try:return SnapshotReader(path,revision,**kwargs)
    except IntegrityError as error:
        if "Uncommitted/future/orphan revision" in str(error):
            raise NoPublishedSnapshot("Requested revision is not a committed ancestor") from error
        raise
