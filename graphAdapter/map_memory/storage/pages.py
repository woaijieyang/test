"""Content-addressed revisions, pinned page reads and immutable fact materialization.

One owner for page/file verification and byte-bounded caches. No model imports.
"""
from pathlib import Path
from collections import OrderedDict
from collections.abc import Mapping
from types import MappingProxyType
import os,json,hashlib,sqlite3,zlib,fcntl,uuid,sys,stat,zipfile
import numpy as np
from PIL import Image
from .archive import UnavailableMaterial,canonical,digest,sync_dir as sync,IntegrityError,StorageError,freeze,decode_arrays
class Pinned(StorageError):pass
def decode_page(key,row):
 if row is None:raise IntegrityError("Missing page")
 data,declared_children,raw_bytes=row
 raw=zlib.decompress(data)
 if len(raw)!=raw_bytes or digest(raw)!=key:raise IntegrityError("Page checksum")
 value=json.loads(raw);kind,payload=value
 if kind in ("m","l"):
  values=[item[1]for item in payload]if kind=="m"else payload
  children=sorted({item[1]for item in values if item[0]=="r"})
 elif kind=="b":children=sorted(set(payload.values()))
 elif kind=="q":children=sorted(set(payload))
 else:raise IntegrityError("Unknown page kind")
 if json.loads(declared_children)!=children:raise IntegrityError("Page child index mismatch")
 return value,children,len(data),len(raw)

def read_revision(db,sid):
 row=db.execute("SELECT parent,root,logical_hash,context,source_id,ordinal FROM revisions WHERE id=?",(sid,)).fetchone()
 if row is None:raise IntegrityError("Published revision missing")
 parent,root,logical_hash,context,source_id,ordinal=row
 basis=dict(schema_version=2,parent=parent,root=root,logical_hash=logical_hash,
  context=json.loads(context),source_id=source_id,ordinal=ordinal)
 if digest(canonical(basis))!=sid:raise IntegrityError("Revision content identity")
 return row

def file_signature(st):
 return st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns

class ImmutableVerifier:
 def __init__(self,limit=8192):
  self.limit=limit;self.cache=OrderedDict();self.bytes_read=0;self.hits=0
 def verify(self,root,ref,*,force=False):
  root=Path(root).resolve();path=(root/ref['path']).resolve()
  if not path.is_relative_to(root):raise IntegrityError('Reference outside source')
  try:before=path.stat()
  except FileNotFoundError as error:raise UnavailableMaterial('missing_material') from error
  if not stat.S_ISREG(before.st_mode):raise IntegrityError('Reference is not a regular file')
  signature=file_signature(before)
  key=(str(path),ref['sha256'],ref['bytes'])
  if before.st_size!=ref['bytes']:raise IntegrityError('Reference size')
  if not force and self.cache.get(key)==signature:
   self.hits+=1;self.cache.move_to_end(key);return path
  h=hashlib.sha256()
  with path.open('rb')as f:
   for block in iter(lambda:f.read(1024*1024),b''):
    self.bytes_read+=len(block);h.update(block)
   after=os.fstat(f.fileno())
  final=file_signature(after)
  if signature!=final or h.hexdigest()!=ref['sha256']:raise IntegrityError('Reference checksum or concurrent mutation')
  self.cache[key]=signature;self.cache.move_to_end(key)
  while len(self.cache)>self.limit:self.cache.popitem(last=False)
  return path
class PageStore:
 def __init__(self,root,*,create=True,checkpoint_interval=64,lock_name="writer.lock"):
  self.root=Path(root)
  if create:self.root.mkdir(parents=True,exist_ok=False)
  self.lock=(self.root/lock_name).open('a+b')
  self.db=None
  try:
   fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   (self.root/'pins.lock').touch(exist_ok=True)
   self.db=sqlite3.connect(self.root/'pages.sqlite3',isolation_level=None)
   self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
   self.db.execute('PRAGMA foreign_keys=ON')
   self.db.executescript("""CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY,data BLOB NOT NULL,children TEXT NOT NULL,raw_bytes INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS revisions(id TEXT PRIMARY KEY,parent TEXT,root TEXT NOT NULL,logical_hash TEXT NOT NULL,context TEXT NOT NULL,source_id TEXT NOT NULL,ordinal INTEGER NOT NULL,FOREIGN KEY(parent)REFERENCES revisions(id));
 CREATE TABLE IF NOT EXISTS checkpoints(revision TEXT PRIMARY KEY,ordinal INTEGER NOT NULL,FOREIGN KEY(revision)REFERENCES revisions(id));""")
   self.interval=checkpoint_interval;self.seen=set();self.tx_seen=set()
   self.metrics=dict(new_pages=0,raw_page_bytes=0,compressed_page_bytes=0,logical_graph_bytes=0)
  except BaseException:
   self.close();raise
 def pointer(self):
  path=self.root/'CURRENT.json';return json.loads(path.read_bytes())if path.exists()else None
 def node(self,kind,payload,children=()):
  raw=canonical([kind,payload]);key=digest(raw)
  if key in self.seen or key in self.tx_seen:return key
  data=zlib.compress(raw,6);kids=sorted(set(children))
  inserted=self.db.execute('INSERT OR IGNORE INTO nodes VALUES(?,?,?,?)',(key,data,canonical(kids).decode(),len(raw))).rowcount
  actual=self.db.execute('SELECT data,children,raw_bytes FROM nodes WHERE id=?',(key,)).fetchone()
  if actual!=(data,canonical(kids).decode(),len(raw)):raise IntegrityError('Immutable page collision')
  self.tx_seen.add(key)
  # Counts are candidate writes,including a rolled-back candidate;final disk is separate.
  if inserted:
   self.metrics['new_pages']+=1;self.metrics['raw_page_bytes']+=len(raw);self.metrics['compressed_page_bytes']+=len(data)
  return key
 def context(self,g):
  current=g.get('scene_state',{}).get('epoch')
  previous={x['epoch']for x in g.get('entities',[])if x['epoch']!=current}
  sources={x.get('source_revision')for x in g.get('entities',[])if x.get('source_revision')}
  return dict(version=g.get('versions',{}).get('pose_map_version'),current_epoch=current,
   previous_epoch=next(iter(previous))if len(previous)==1 else None,
   transition_source=next(iter(sources))if len(sources)==1 else None,
   binding_hash=digest(canonical(g.get('pose_bindings'))))
 def value(self,x,path,context):
  key=path[-1]if path else None
  if len(path)==1 and path[0]in getattr(self,"history_roots",{}):
   return ["r",self.history_roots[path[0]]]
  if not isinstance(x,(dict,list)):
   if context.get("_literal"):return ["v",x]
   if key=='pose_map_version'and x is not None and x==context['version']:return['c','version']
   if key=='snapshot_hash'and x==context['binding_hash']:return['c','binding_hash']
   if key in ('epoch','dst_epoch')and isinstance(x,str):
    if x==context['current_epoch']:return['c','current_epoch']
    if x==context['previous_epoch']:return['c','previous_epoch']
   if key=='source_revision'and x is not None and x==context['transition_source']:return['c','transition_source']
   return['v',x]
  if isinstance(x,dict):
   if any(not isinstance(k,str)for k in x):raise IntegrityError('JSON string keys required')
   entries=[(k,self.value(v,path+(k,),context))for k,v in sorted(x.items())]
   return['r',self.map(entries)]
  values=[self.value(v,path+(str(i),),context)for i,v in enumerate(x)]
  if len(values)<=32:
   return['r',self.node('l',values,[v[1]for v in values if v[0]=='r'])]
  # Content-defined chunks keep unchanged sequence interiors reusable after insertion.
  chunks=[];batch=[]
  for v in values:
   batch.append(v)
   if len(batch)>=64 or(len(batch)>=8 and hashlib.sha256(canonical(v)).digest()[0]&31==0):
    chunks.append(self.node('l',batch,[i[1]for i in batch if i[0]=='r']));batch=[]
  if batch:chunks.append(self.node('l',batch,[i[1]for i in batch if i[0]=='r']))
  return['r',self.node('q',chunks,chunks)]
 def map(self,entries,depth=0):
  if len(entries)<=16 or depth>=64:
   return self.node('m',entries,[v[1]for _,v in entries if v[0]=='r'])
  grouped={}
  for key,value in entries:grouped.setdefault(hashlib.sha256(key.encode()).hexdigest()[depth],[]).append((key,value))
  children={key:self.map(values,depth+1)for key,values in sorted(grouped.items())}
  return self.node('b',children,children.values())
 def descriptor(self,root,key,depth=0):
  row=self.db.execute("SELECT data,children,raw_bytes FROM nodes WHERE id=?",(root,)).fetchone()
  (kind,payload),_,_,_=decode_page(root,row)
  if kind=="m":
   for name,value in payload:
    if name==key:return value
   raise KeyError(key)
  if kind=="b":
   bucket=hashlib.sha256(key.encode()).hexdigest()[depth]
   if bucket not in payload:raise KeyError(key)
   return self.descriptor(payload[bucket],key,depth+1)
  raise IntegrityError("Persistent map required")
 def map_update(self,root,changes,depth=0):
  if root is None:return self.map(sorted(changes.items()),depth)
  row=self.db.execute("SELECT data,children,raw_bytes FROM nodes WHERE id=?",(root,)).fetchone()
  (kind,payload),_,_,_=decode_page(root,row)
  if kind=="m":
   values=dict(payload);values.update(changes)
   return self.map(sorted(values.items()),depth)
  if kind!="b":raise IntegrityError("Persistent map required")
  children=dict(payload);grouped={}
  for key,value in changes.items():
   bucket=hashlib.sha256(key.encode()).hexdigest()[depth]
   grouped.setdefault(bucket,{})[key]=value
  for bucket,values in grouped.items():
   children[bucket]=self.map_update(children.get(bucket),values,depth+1)
  return self.node("b",children,children.values())
 def close(self):
  if getattr(self,"db",None)is not None:self.db.close();self.db=None
  if getattr(self,"lock",None)is not None:
   fcntl.flock(self.lock,fcntl.LOCK_UN);self.lock.close();self.lock=None
 def gc(self):
  guard=(self.root/'pins.lock').open('rb')
  try:fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:guard.close();raise Pinned('Active reader;no collection')
  try:
   current=self.pointer();reachable=set();sid=current['snapshot_id']if current else None
   roots=[];seen_revisions=set()
   while sid is not None:
    if sid in seen_revisions:raise IntegrityError("Published ancestry cycle")
    seen_revisions.add(sid)
    row=read_revision(self.db,sid)
    sid,root=row[:2];roots.append(root)
   queue=list(roots)
   while queue:
    node=queue.pop()
    if node in reachable:continue
    reachable.add(node)
    row=self.db.execute('SELECT data,children,raw_bytes FROM nodes WHERE id=?',(node,)).fetchone()
    _,children,_,_=decode_page(node,row);queue.extend(children)
   candidates=[x[0]for x in self.db.execute('SELECT id FROM nodes')if x[0]not in reachable]
   # All published ancestors remain materialized; only unreachable metadata is collectible.
   self.db.execute('BEGIN IMMEDIATE')
   try:
    self.db.executemany('DELETE FROM nodes WHERE id=?',[(x,)for x in candidates]);self.db.execute('COMMIT')
   except BaseException:
    self.db.execute('ROLLBACK');raise
   self.seen.difference_update(candidates)
   return dict(unreachable_metadata_pages_removed=len(candidates),published_roots_kept=len(roots))
  finally:fcntl.flock(guard,fcntl.LOCK_UN);guard.close()
class Reader:
 def __init__(self,root,revision='CURRENT',cache_bytes=8*1024*1024):
  self.root=Path(root);self.guard=(self.root/'pins.lock').open('rb');fcntl.flock(self.guard,fcntl.LOCK_SH)
  try:
   self.db=sqlite3.connect('file:'+str(self.root/'pages.sqlite3')+'?mode=ro',uri=True,isolation_level=None)
   self.db.execute('PRAGMA query_only=ON')
   pointer=json.loads((self.root/'CURRENT.json').read_bytes());sid=pointer['snapshot_id']
   target=sid if revision=='CURRENT'else revision;seen=set()
   while sid is not None and sid!=target:
    if sid in seen:raise IntegrityError('Revision cycle')
    seen.add(sid);row=self.db.execute('SELECT parent FROM revisions WHERE id=?',(sid,)).fetchone()
    if row is None:raise IntegrityError('Unknown parent')
    sid=row[0]
   if sid!=target:raise IntegrityError('Uncommitted/future/orphan revision')
   self.sid=sid
   row=read_revision(self.db,sid)
   self.parent,self.root_node,self.logical_hash,context,self.source_id,self.ordinal=row
   self.context=json.loads(context)
   basis=dict(schema_version=2,parent=self.parent,root=self.root_node,logical_hash=self.logical_hash,
    context=self.context,source_id=self.source_id,ordinal=self.ordinal)
   if digest(canonical(basis))!=sid:raise IntegrityError('Revision content identity')
   self.limit=cache_bytes;self.cache=OrderedDict();self.bytes=0;self.read_bytes=0;self.hits=0
  except BaseException:
   if hasattr(self,'db'):self.db.close()
   fcntl.flock(self.guard,fcntl.LOCK_UN);self.guard.close();raise

 def node(self,key,force=False):
  if not force and key in self.cache:
   value,size=self.cache.pop(key);self.cache[key]=(value,size);self.hits+=1;return value
  row=self.db.execute('SELECT data,children,raw_bytes FROM nodes WHERE id=?',(key,)).fetchone()
  value,_,compressed,size=decode_page(key,row);self.read_bytes+=compressed
  if size<=self.limit:
   while self.cache and self.bytes+size>self.limit:
    _,(_,n)=self.cache.popitem(last=False);self.bytes-=n
   self.cache[key]=(value,size);self.bytes+=size
  return value
 def value(self,desc,force=False,depth=0):
  if depth>256:raise IntegrityError('Page depth limit')
  kind,payload=desc
  if kind=='v':return payload
  if kind=='c':return self.context[payload]
  if kind!='r':raise IntegrityError('Unknown descriptor')
  kind,payload=self.node(payload,force)
  if kind=='m':return {k:self.value(v,force,depth+1)for k,v in payload}
  if kind=='b':
   result={}
   for root in payload.values():result.update(self.value(['r',root],force,depth+1))
   return result
  if kind=='l':return [self.value(v,force,depth+1)for v in payload]
  if kind=='q':
   result=[]
   for root in payload:result.extend(self.value(['r',root],force,depth+1))
   return result
  raise IntegrityError('Unknown page kind')
 def graph(self,force=False):
  result=self.value(['r',self.root_node],force)
  if digest(canonical(result))!=self.logical_hash:raise IntegrityError('Expanded logical state differs')
  return result
 def close(self):
  self.cache.clear()
  if getattr(self,"db",None)is not None:self.db.close();self.db=None
  if getattr(self,"guard",None)is not None:
   fcntl.flock(self.guard,fcntl.LOCK_UN);self.guard.close();self.guard=None
def deep_size(value):
 seen=set()
 def measure(x):
  if id(x)in seen:return 0
  seen.add(id(x));n=sys.getsizeof(x)
  if isinstance(x,Mapping):
   if isinstance(x,MappingProxyType):n+=sys.getsizeof(dict(x))
   n+=sum(measure(k)+measure(v)for k,v in x.items())
  elif isinstance(x,(list,tuple)):n+=sum(measure(v)for v in x)
  return n
 return measure(value)
class HistoryPageCache:
 """Byte-bounded raw-page reuse within one cold audit of one map root.

 Values are verified descriptors, never context-expanded graphs. Each reader
 still resolves version/epoch substitutions through its own revision context.
 """
 def __init__(self,root,limit,*,episode=None):
  if type(limit)is not int or limit<0:raise ValueError('History page cache byte budget must be a nonnegative integer')
  self.root=Path(root).resolve();self.limit=limit;self.episode=episode;self.closed=False
  self.items=OrderedDict();self.bytes=0;self.peak_bytes=0;self.hits=0;self.decodes=0
 def bind(self,root,episode=None):
  if self.closed or (self.episode is not None and episode!=self.episode):raise IntegrityError('History page cache episode differs or is closed')
  if Path(root).resolve()!=self.root:raise IntegrityError('History cache belongs to another map root')
 def read(self,db,key,*,force=False,recheck=False):
  if self.closed:raise IntegrityError('History page cache is closed')
  entry=self.items.get(key)
  row=None
  if recheck and entry is not None and not force:
   row=db.execute('SELECT data,children,raw_bytes FROM nodes WHERE id=?',(key,)).fetchone()
   if row!=entry[3]:force=True
  if force and entry is not None:
   self.bytes-=self.items.pop(key)[2];entry=None
  if entry is not None:
   self.hits+=1;self.items.move_to_end(key)
   return entry[0],entry[1],0
  if row is None:row=db.execute('SELECT data,children,raw_bytes FROM nodes WHERE id=?',(key,)).fetchone()
  try:value,children,compressed,_=decode_page(key,row)
  except (zlib.error,UnicodeDecodeError,json.JSONDecodeError) as err:
   raise IntegrityError('Invalid compressed history page') from err
  self.decodes+=1
  stored=row if self.episode is not None else None
  size=deep_size((value,children,stored))+sys.getsizeof(key)+128
  if size<=self.limit:
   while self.items and self.bytes+size>self.limit:
    _,(_,_,old,_)=self.items.popitem(last=False);self.bytes-=old
   self.items[key]=(value,children,size,stored);self.bytes+=size;self.peak_bytes=max(self.peak_bytes,self.bytes)
  return value,children,compressed
 def close(self):
  self.clear();self.closed=True
 def clear(self):
  self.items.clear();self.bytes=0

class SelectiveReader(Reader):
 def node(self,key,force=False):
  shared=getattr(self,'_history_cache',None)
  if shared is not None:
   checked=getattr(self,'_checked_shared_keys',None)
   value,_,read_bytes=shared.read(self.db,key,force=force,recheck=checked is not None and key not in checked)
   if checked is not None:checked.add(key)
   self.read_bytes+=read_bytes
   if read_bytes==0:self.hits+=1
   return value
  # Immutable cached pages already carry their measured retained size.
  if not force and key in self.cache:return super().node(key,False)
  if force and key in self.cache:self.bytes-=self.cache.pop(key)[1]
  value=super().node(key,force)
  if key in self.cache:
   self.bytes-=self.cache.pop(key)[1]
   size=deep_size(value)
   if size<=self.limit:
    while self.cache and self.bytes+size>self.limit:
     _,(_,n)=self.cache.popitem(last=False);self.bytes-=n
    self.cache[key]=(value,size);self.bytes+=size
  return value
 def map_key(self,root,key,depth=0):
  kind,payload=self.node(root)
  if kind=='m':
   for name,value in payload:
    if name==key:return value
   raise KeyError(key)
  if kind=='b':
   bucket=hashlib.sha256(key.encode()).hexdigest()[depth]
   if bucket not in payload:raise KeyError(key)
   return self.map_key(payload[bucket],key,depth+1)
  raise IntegrityError('Map required')
 def sequence_index(self,root,index):
  kind,payload=self.node(root)
  if index<0:raise IndexError(index)
  if kind=='l':return payload[index]
  if kind=='q':
   for child in payload:
    ckind,values=self.node(child)
    if ckind!='l':raise IntegrityError('Sequence chunk required')
    if index<len(values):return values[index]
    index-=len(values)
   raise IndexError(index)
  raise IntegrityError('Sequence required')
 def lookup(self,path):
  descriptor=['r',self.root_node]
  for part in path:
   if descriptor[0]!='r':raise KeyError(part)
   descriptor=self.map_key(descriptor[1],part)if isinstance(part,str)else self.sequence_index(descriptor[1],part)
  return self.value(descriptor)
class EpisodeImageCache:
 """Byte-bounded decoded RGB only. View bindings are always resolved on the caller's revision."""
 def __init__(self,root,limit,*,episode=None):
  if type(limit) is not int or limit<0:raise ValueError('Invalid image byte budget')
  self.root=Path(root).resolve();self.episode=episode
  self.images=OrderedDict();self.image_bytes=0;self.image_limit=limit
  self.verifier=ImmutableVerifier();self.decodes=0;self.closed=False

 def bind(self,root,episode):
  if self.closed or self.root!=Path(root).resolve() or self.episode!=episode:
   raise IntegrityError('Image cache is closed or belongs to another episode')

 def image(self,ref):
  if self.closed:raise IntegrityError("Image cache is closed")
  if ref is None:return None
  path=self.verifier.verify(self.root,ref);key=(ref['path'],ref['sha256'])
  if key in self.images:
   value,size=self.images.pop(key);self.images[key]=(value,size);return value
  try:
   verified=self.verifier.cache[(str(path),ref['sha256'],ref['bytes'])]
   with path.open('rb') as stream:
    if file_signature(os.fstat(stream.fileno()))!=verified:raise IntegrityError('Image source changed before decoding')
    with Image.open(stream)as image:value=freeze(np.asarray(image.convert('RGB')))
    if file_signature(os.fstat(stream.fileno()))!=verified:raise IntegrityError('Image source changed during decoding')
   self.verifier.verify(self.root,ref)
  except (OSError,ValueError) as error:
   # A changed checksum remains an integrity failure, even if the decoder failed first.
   self.verifier.verify(self.root,ref)
   raise UnavailableMaterial('undecodable_image') from error
  self.decodes+=1
  size=value.nbytes
  if size<=self.image_limit:
   while self.images and self.image_bytes+size>self.image_limit:
    _,(_,n)=self.images.popitem(last=False);self.image_bytes-=n
   self.images[key]=(value,size);self.image_bytes+=size
  return value
 def close(self):
  self.images.clear();self.image_bytes=0;self.verifier.cache.clear();self.closed=True


class FactMaterializer:
 def __init__(self,root,facts,*,metadata_bytes=8*1024*1024,image_bytes=16*1024*1024,image_cache=None):
  self.root=root;self.facts=facts;self.verifier=ImmutableVerifier()
  self.metadata=OrderedDict();self.metadata_bytes=0;self.metadata_limit=metadata_bytes
  self.owns_image_cache=image_cache is None
  self.image_cache=EpisodeImageCache(root,image_bytes) if image_cache is None else image_cache
 def capture(self,uid):
  ref=self.facts[uid]['meta'];path=self.verifier.verify(self.root,ref);key=(ref['path'],ref['sha256'])
  if key in self.metadata:
   value,size=self.metadata.pop(key);self.metadata[key]=(value,size);return value
  value=freeze(json.loads(path.read_bytes()));size=deep_size(value)
  if size<=self.metadata_limit:
   while self.metadata and self.metadata_bytes+size>self.metadata_limit:
    _,(_,n)=self.metadata.popitem(last=False);self.metadata_bytes-=n
   self.metadata[key]=(value,size);self.metadata_bytes+=size
  return value
 def image(self,ref):
  return self.image_cache.image(ref)
 def view(self,uid,view,snapshot_id,*,images=True,depth=False):
  refs=self.facts[uid];capture=self.capture(uid)
  value=dict(view,capture=capture,snapshot_id=snapshot_id,raw_rgb_ref=refs['rgb'],host_view_ref=refs['host_view'])
  if depth and refs['depth']is not None:
   ref=refs['depth'];path=self.verifier.verify(self.root,ref)
   try:value['depth']=decode_arrays(path,capture['arrays'])
   except (OSError,ValueError,EOFError,zipfile.BadZipFile) as error:
    self.verifier.verify(self.root,ref)
    raise UnavailableMaterial('undecodable_depth') from error
  result={key:freeze(field) for key,field in value.items()}
  if images:
   # Decoded images already have immutable byte backing; the returned view can
   # safely outlive cache eviction without taking another full-frame copy.
   result['raw_rgb']=self.image(refs['rgb'])
   result['host_view']=self.image(refs['host_view'])
  return MappingProxyType(result)
 def close(self):
  self.metadata.clear();self.metadata_bytes=0
  if self.owns_image_cache:self.image_cache.close()
class BundlePages(PageStore):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,lock_name="page-writer.lock",**kwargs)
 def context(self,bundle):return super().context(bundle['graph'])
 def publish(self,bundle,source_id,*,public,changes,fault=None):
  original_fault=fault
  if original_fault is not None:
   aliases={"after_sql_commit":"sqlite_prepared_committed","after_current_tmp_fsync":"current_tmp_fsynced",
    "after_current_replace":"current_replaced","after_current_dir_fsync":"current_directory_fsynced"}
   def fault(stage):
    original_fault(stage)
    if stage in aliases:original_fault(aliases[stage])
  old=self.pointer();parent=old['snapshot_id']if old else None
  number=self.db.execute('SELECT ordinal FROM revisions WHERE id=?',(parent,)).fetchone()[0]+1 if parent else 1
  context=self.context(bundle);logical=canonical(bundle);self.metrics['logical_graph_bytes']+=len(logical)
  self.tx_seen=set();self.db.execute('BEGIN IMMEDIATE')
  try:
   self.history_roots={}
   for field,delta in changes.items():
    prior=None
    if old is not None:
     descriptor=self.descriptor(old["root"],field)
     if descriptor[0]!="r":raise IntegrityError("History index must be a map")
     prior=descriptor[1]
    values={key:self.value(value,(field,key),dict(context,_literal=True))for key,value in delta.items()}
    self.history_roots[field]=self.map_update(prior,values)
   root=self.value(bundle,(),context)[1]
   # The public contract is itself bound into the opaque source identity and
   # inside the bundle;the original PageStore revision shape stays reusable.
   contract=digest(canonical(public));source=digest(canonical([source_id,contract]))
   basis=dict(schema_version=2,parent=parent,root=root,logical_hash=digest(logical),
      context=context,source_id=source,ordinal=number)
   sid=digest(canonical(basis))
   values=(sid,parent,root,basis['logical_hash'],canonical(context).decode(),source,number)
   self.db.execute('INSERT OR IGNORE INTO revisions VALUES(?,?,?,?,?,?,?)',values)
   if self.db.execute('SELECT * FROM revisions WHERE id=?',(sid,)).fetchone()!=values:raise IntegrityError('Revision collision')
   if number%self.interval==0:self.db.execute('INSERT OR IGNORE INTO checkpoints VALUES(?,?)',(sid,number))
   if fault:fault('before_sql_commit')
   self.db.execute('COMMIT')
  except BaseException:
   if self.db.in_transaction:self.db.execute('ROLLBACK')
   self.tx_seen=set();raise
  self.seen.update(self.tx_seen);self.tx_seen=set()
  if len(self.seen)>65536:self.seen.clear()
  if fault:fault('after_sql_commit')
  pointer=dict(snapshot_id=sid,**basis,**public)
  tmp=self.root/(uuid.uuid4().hex+'.CURRENT.tmp')
  with tmp.open('xb')as f:f.write(canonical(pointer));f.flush();os.fsync(f.fileno())
  if fault:fault('after_current_tmp_fsync')
  if self.pointer()!=old:raise IntegrityError('Stale visibility parent')
  os.replace(tmp,self.root/'CURRENT.json')
  if fault:fault('after_current_replace')
  sync(self.root)
  if fault:fault('after_current_dir_fsync')
  if number%self.interval==0:self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
  return pointer
