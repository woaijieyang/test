"""Immutable archives and revisions; CURRENT is the sole visibility point.

Storage contains only JSON/PNG/NumPy arrays. No simulator, model or pickle loader.
"""
from __future__ import annotations
from pathlib import Path
from collections import OrderedDict
from collections.abc import Mapping
from types import MappingProxyType
import hashlib,io,json,os,re,sqlite3,uuid,zipfile,fcntl
import numpy as np
from PIL import Image

SCHEMA=1
class StorageError(RuntimeError):pass
class IntegrityError(StorageError):pass
class UnavailableMaterial(IntegrityError):
    """A pinned in-root payload is missing or cannot be decoded, with no detected identity mismatch."""
    def __init__(self,reason):
        if reason not in ('missing_material','undecodable_image','undecodable_features','undecodable_depth'):
            raise ValueError('Unknown evidence availability reason')
        self.reason=reason
        super().__init__(reason)

class ConcurrentWriterError(StorageError):pass
class NoPublishedSnapshot(StorageError):pass
class VersionUnavailable(StorageError):pass

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def digest(data):return hashlib.sha256(data).hexdigest()

def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open("rb")as f:
        for block in iter(lambda:f.read(8*1024*1024),b""):h.update(block)
    return h.hexdigest()

def sync_dir(path):
    fd=os.open(path,os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def freeze(value):
    if isinstance(value,Mapping):return MappingProxyType({k:freeze(v)for k,v in value.items()})
    if isinstance(value,(tuple,list)):return tuple(freeze(v)for v in value)
    if isinstance(value,np.ndarray):
        # An immutable bytes backing prevents callers re-enabling writable flags.
        a=np.ascontiguousarray(value)
        return np.frombuffer(a.tobytes(),dtype=a.dtype).reshape(a.shape)
    return value

def array_descriptor(a):
    a=np.asarray(a)
    if a.dtype.hasobject:raise IntegrityError("Python object arrays are forbidden")
    return dict(shape=list(a.shape),dtype=a.dtype.str,bytes=a.nbytes)

def encode_arrays(arrays):
    if not arrays:raise IntegrityError("Empty array bundle")
    result=io.BytesIO()
    with zipfile.ZipFile(result,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=1)as z:
        for name in sorted(arrays):
            if not re.fullmatch(r"[A-Za-z0-9_]+",name):raise IntegrityError("Unsafe array key")
            a=np.ascontiguousarray(arrays[name]);array_descriptor(a)
            raw=io.BytesIO();np.save(raw,a,allow_pickle=False)
            info=zipfile.ZipInfo(name+".npy",date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o600<<16
            z.writestr(info,raw.getvalue(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=1)
    return result.getvalue()

def decode_arrays(path,expected,*,max_bytes=512*1024*1024):
    if sum(v["bytes"]for v in expected.values())>max_bytes:raise IntegrityError("Array bundle exceeds byte budget")
    with zipfile.ZipFile(path)as z:
        if {x.filename for x in z.infolist()}!={k+".npy"for k in expected}:raise IntegrityError("Array names mismatch")
        if sum(x.file_size for x in z.infolist())>max_bytes+4096*len(expected):raise IntegrityError("Expanded ZIP budget exceeded")
    with np.load(path,allow_pickle=False)as loaded:
        result={}
        for name,description in expected.items():
            a=loaded[name]
            description=dict(description,shape=list(description["shape"]))
            if array_descriptor(a)!=description:raise IntegrityError("Array shape/dtype/size mismatch: "+name)
            result[name]=freeze(a)
    return result

class ByteLRU:
    def __init__(self,max_bytes):
        if type(max_bytes)is not int or max_bytes<0:raise ValueError("Nonnegative cache budget required")
        self.max_bytes=max_bytes;self.bytes=0;self.items=OrderedDict();self.hits=0;self.misses=0
    def get(self,key,loader):
        if key in self.items:
            value,size=self.items.pop(key);self.items[key]=(value,size);self.hits+=1;return value
        self.misses+=1;value=loader();size=value.nbytes
        if size<=self.max_bytes:
            while self.items and self.bytes+size>self.max_bytes:
                _,(_,old)=self.items.popitem(last=False);self.bytes-=old
            self.items[key]=(value,size);self.bytes+=size
        return value
    def clear(self):self.items.clear();self.bytes=0

def _safe_uid(value):
    if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*",value):
        raise IntegrityError("Safe opaque identity required")
    return value

def _owned(root,relative):
    p=(root/relative).resolve()
    if root.resolve()not in p.parents:raise IntegrityError("Reference escapes episode")
    return p

def _file_ref(root,path,data=None):
    return dict(path=path.relative_to(root).as_posix(),sha256=digest(data)if data is not None else file_hash(path),
                bytes=len(data)if data is not None else path.stat().st_size)

def _verify_ref(root,ref):
    p=_owned(root,ref["path"])
    if not p.is_file() or p.stat().st_size!=ref["bytes"] or file_hash(p)!=ref["sha256"]:
        raise IntegrityError("Referenced file checksum/size mismatch: "+ref["path"])
    return p

def _write_immutable(root,relative,data,*,fault=None,stage="file"):
    path=_owned(root,relative);path.parent.mkdir(parents=True,exist_ok=True)
    expected=digest(data)
    if path.exists():
        if file_hash(path)!=expected:raise IntegrityError("Immutable file differs: "+relative)
        return _file_ref(root,path,data)
    pending=root/".pending";pending.mkdir(exist_ok=True)
    temp=pending/(uuid.uuid4().hex+".tmp")
    with temp.open("xb")as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
    if fault:fault(stage+"_tmp_fsynced")
    try:os.link(temp,path)
    except FileExistsError:
        if file_hash(path)!=expected:raise IntegrityError("Concurrent immutable file differs")
    temp.unlink();sync_dir(path.parent)
    if fault:fault(stage+"_renamed")
    return _file_ref(root,path,data)


def owned_references(value):
    found={}
    def visit(item):
        if isinstance(item,dict):
            if {"path","sha256","bytes"}.issubset(item):
                ref={k:item[k]for k in ("path","sha256","bytes")}
                previous=found.setdefault(ref["path"],ref)
                if previous!=ref:raise IntegrityError("Conflicting descriptors for one path")
            for child in item.values():visit(child)
        elif isinstance(item,(list,tuple)):
            for child in item:visit(child)
    visit(value)
    return [found[k]for k in sorted(found)]

def read_manifest(root,snapshot,expected=None):
    if not re.fullmatch("[a-f0-9]{64}",snapshot):raise IntegrityError("Invalid snapshot identity")
    path=root/"revisions"/snapshot/"manifest.json"
    if expected is not None:
        verified=_verify_ref(root,expected)
        if verified!=path.resolve():raise IntegrityError("Noncanonical manifest path")
    manifest=json.loads(path.read_bytes())
    if manifest["snapshot_id"]!=snapshot or manifest["schema_version"]!=SCHEMA:raise IntegrityError("Manifest identity/schema")
    basis={k:v for k,v in manifest.items()if k not in ("snapshot_id","graph")}
    if digest(canonical(basis))!=snapshot:raise IntegrityError("Snapshot content identity mismatch")
    graph=manifest["graph"]
    if graph["sha256"]!=manifest["graph_sha256"] or graph["path"]!="revisions/"+snapshot+"/graph.json":
        raise IntegrityError("Noncanonical graph reference")
    return manifest


def semantic_reference_checks(graph,versions=None):
    views=graph["views"];state=graph.get("scene_state",{});errors=[]
    versions=graph.get("versions",{})if versions is None else versions
    if "versions"in graph and graph["versions"]!=versions:errors.append("graph_manifest_version_mismatch")
    entities=graph.get("entities",[]);aliases=graph.get("aliases",[])
    entity_keys={(x["epoch"],x["id"])for x in entities}
    if len(entity_keys)!=len(entities):errors.append("duplicate_entity")
    if len({(x["epoch"],x["src"])for x in aliases})!=len(aliases):errors.append("duplicate_alias")
    for entity in entities:
        if not set(entity.get("view_uids",[]))<=set(views):errors.append("missing_entity_view")
    for alias in aliases:
        if (alias["epoch"],alias["src"])not in entity_keys:errors.append("missing_alias_source")
        if alias.get("dst")is not None and(alias["dst_epoch"],alias["dst"])not in entity_keys:
            errors.append("missing_alias_target")
        for candidate in alias.get("candidates",[]):
            if(candidate["epoch"],candidate["id"])not in entity_keys:errors.append("missing_ambiguous_candidate")
    lookup={(x["epoch"],x["src"]):x for x in aliases}
    for origin in lookup:
        seen=set();key=origin
        while key in lookup:
            if key in seen:errors.append("alias_cycle");break
            seen.add(key);alias=lookup[key]
            if alias.get("dst")is None:break
            if state.get("epoch")==alias["epoch"]and alias["dst_epoch"]!=state["epoch"]:
                errors.append("backward_current_epoch_alias")
            key=(alias["dst_epoch"],alias["dst"])
    objects={x["id"]:x for x in state.get("objects",[])}
    nulls=0
    for uid,view in state.get("views",{}).items():
        if uid not in views:errors.append("missing_scene_view")
        refs=set(map(int,view["full_obj_list"]))|set(view["cluster"])
        if view["prompt"]is not None:
            refs|=set(view["prompt"]["obj_id"]);nulls+=view["prompt"]["obj_id"].count(None)
        refs.discard(None) # retired/unbound ordinal slots do not name an entity
        if not refs<=set(objects):errors.append("dangling_scene_object")
    anchors=set(state.get("anchor_keys",[]))
    if not anchors<=set(state.get("views",{})):errors.append("missing_anchor_view")
    for obj in objects.values():
        if obj.get("image")is not None and obj["image"]not in anchors:errors.append("missing_object_image_anchor")
    vsm=graph.get("vsm",{})
    if "anchors"in vsm and set(vsm["anchors"])!=anchors:errors.append("anchor_index_membership")
    for key,node in vsm.get("anchors",{}).items():
        if key not in anchors or not set(node["objects"])<=set(objects):errors.append("dangling_vsm_anchor_object")
    for uid,oid in vsm.get("visibility_edges",[]):
        if uid not in anchors or oid not in objects:errors.append("dangling_visibility_edge")
    for node in vsm.get("visited",[]):
        if node["image_key"]not in views:errors.append("missing_visited_view")
    for room in vsm.get("room_type_index",{}).values():
        if not set(room["anchors"])<=anchors or not set(room["objects"])<=set(objects):errors.append("dangling_room_type_index")
        if room.get("frontiers"):errors.append("unexpected_stage001_frontier")
    for item in graph.get("contributions",[]):
        if item["frame_uid"]not in views or item["tile_id"]not in graph.get("tiles",{}):errors.append("dangling_contribution")
        elif views[item["frame_uid"]].get("position_G")is None:errors.append("non_spatial_contribution")
        elif item["pose_binding"]["pose_map_version"]!=versions.get("pose_map_version"):
            errors.append("mixed_contribution_version")
    return dict(entities=len(entities),aliases=len(aliases),anchors=len(anchors),
        contributions=len(graph.get("contributions",[])),retired_prompt_slots=nulls,errors=errors)


SQL="""
CREATE TABLE IF NOT EXISTS observations(uid TEXT PRIMARY KEY,seq INTEGER NOT NULL UNIQUE,
 hash TEXT NOT NULL,refs TEXT NOT NULL,status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS executions(id TEXT PRIMARY KEY,pre TEXT,post TEXT NOT NULL,
 macro INTEGER,primitive INTEGER,result TEXT NOT NULL,UNIQUE(post),FOREIGN KEY(post) REFERENCES observations(uid),FOREIGN KEY(pre) REFERENCES observations(uid));
CREATE TABLE IF NOT EXISTS detections(uid TEXT PRIMARY KEY,frame TEXT NOT NULL,idx INTEGER NOT NULL,
 mask_ref TEXT NOT NULL,payload TEXT NOT NULL,UNIQUE(frame,idx),FOREIGN KEY(frame) REFERENCES observations(uid));
CREATE TABLE IF NOT EXISTS revisions(id TEXT PRIMARY KEY,parent TEXT,status TEXT NOT NULL,
 versions TEXT NOT NULL,manifest_hash TEXT NOT NULL,FOREIGN KEY(parent) REFERENCES revisions(id));
CREATE TABLE IF NOT EXISTS revision_observations(revision TEXT NOT NULL,frame TEXT NOT NULL,payload TEXT NOT NULL,
 PRIMARY KEY(revision,frame),FOREIGN KEY(revision) REFERENCES revisions(id),FOREIGN KEY(frame) REFERENCES observations(uid));
CREATE TABLE IF NOT EXISTS entities(epoch TEXT NOT NULL,id INTEGER NOT NULL,revision TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL,
 PRIMARY KEY(epoch,id,revision),FOREIGN KEY(revision) REFERENCES revisions(id));
CREATE TABLE IF NOT EXISTS aliases(epoch TEXT NOT NULL,src INTEGER NOT NULL,revision TEXT NOT NULL,dst_epoch TEXT,dst INTEGER,payload TEXT NOT NULL,
 PRIMARY KEY(epoch,src,revision),FOREIGN KEY(epoch,src,revision) REFERENCES entities(epoch,id,revision));
CREATE TABLE IF NOT EXISTS view_objects(frame TEXT NOT NULL,epoch TEXT NOT NULL,entity INTEGER NOT NULL,revision TEXT NOT NULL,
 PRIMARY KEY(frame,epoch,entity,revision),FOREIGN KEY(revision,frame) REFERENCES revision_observations(revision,frame),
 FOREIGN KEY(epoch,entity,revision) REFERENCES entities(epoch,id,revision));
CREATE TABLE IF NOT EXISTS edges(id TEXT NOT NULL,type TEXT NOT NULL,src TEXT NOT NULL,dst TEXT NOT NULL,revision TEXT NOT NULL,payload TEXT NOT NULL,
 PRIMARY KEY(id,revision),FOREIGN KEY(revision,src) REFERENCES revision_observations(revision,frame),
 FOREIGN KEY(revision,dst) REFERENCES revision_observations(revision,frame));
CREATE TABLE IF NOT EXISTS contributions(frame TEXT NOT NULL,tile TEXT NOT NULL,revision TEXT NOT NULL,pose_binding TEXT NOT NULL,
 PRIMARY KEY(frame,tile,revision),FOREIGN KEY(revision,frame) REFERENCES revision_observations(revision,frame));
"""
class RawArchive:
    def __init__(self,path,episode_uid,*,dataset,create=True,cache_bytes=128*1024*1024):
        self.root=Path(path).absolute();self.episode_uid=_safe_uid(episode_uid);self.dataset=_safe_uid(dataset)
        if create:self.root.mkdir(parents=True,exist_ok=False)
        elif not self.root.is_dir():raise StorageError("Episode does not exist")
        self._lock=(self.root/"writer.lock").open("a+b")
        try:fcntl.flock(self._lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:self._lock.close();self._lock=None;raise ConcurrentWriterError("Episode already has a writer")
        identity=dict(schema_version=SCHEMA,episode_uid=self.episode_uid,dataset=self.dataset)
        _write_immutable(self.root,"episode_identity.json",canonical(identity))
        self.connection=sqlite3.connect(self.root/"index.sqlite3",isolation_level=None)
        self.connection.execute("PRAGMA journal_mode=WAL");self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA foreign_keys=ON");self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript(SQL);self.connection.execute("PRAGMA user_version=1")
        self.cache=ByteLRU(cache_bytes);self.current=self._pointer()
        self._recover_raw_facts()

    def _pointer(self):
        p=self.root/"CURRENT.json"
        return json.loads(p.read_bytes())if p.exists()else None

    def _append(self,name,row):
        with (self.root/name).open("a",encoding="utf8")as f:
            f.write(canonical(row).decode()+"\n");f.flush();os.fsync(f.fileno())

    def _recover_raw_facts(self):
        for p in sorted((self.root/"observations").glob("*.meta.json")):
            record=json.loads(p.read_bytes())
            if record["episode_uid"]!=self.episode_uid:raise IntegrityError("Raw episode mismatch")
            for ref in record["files"].values():
                if ref is not None:_verify_ref(self.root,ref)
            self._index_raw(record,_file_ref(self.root,p))

    def _index_raw(self,record,meta_ref):
        refs=dict(meta=meta_ref,**record["files"])
        previous=self.connection.execute("SELECT hash FROM observations WHERE uid=?",(record["frame_uid"],)).fetchone()
        if previous and previous[0]!=record["raw_signature"]:raise IntegrityError("Raw observation identity changed")
        self.connection.execute("INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?)",
          (record["frame_uid"],record["capture_seq"],record["raw_signature"],canonical(refs).decode(),record["status"]))

    def archive_frame(self,meta,rgb,raw_depth,aligned_depth,valid_mask,*,host_view=None,host_transform=None,fault=None):
        meta=json.loads(canonical(meta))
        if set(meta)&{"files","arrays","raw_signature","schema_version","host_transform","status"}:
            raise IntegrityError("Reserved raw archive envelope field")
        uid=_safe_uid(meta["frame_uid"])
        if meta["episode_uid"]!=self.episode_uid or not uid.startswith(self.episode_uid+":"):
            raise IntegrityError("Raw episode/frame mismatch")
        seq=meta["capture_seq"]
        if type(seq)is not int or seq<1:raise IntegrityError("Capture ordinal required")
        files={};arrays={}
        if rgb is not None:
            rgb=np.asarray(rgb)
            if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise IntegrityError("uint8 RGB required")
            b=io.BytesIO();Image.fromarray(rgb).save(b,format="PNG")
            files["rgb"]=_write_immutable(self.root,"observations/"+uid+".rgb.png",b.getvalue(),fault=fault,stage="raw_rgb")
        else:files["rgb"]=None
        for name,value in (("raw_depth",raw_depth),("aligned_depth",aligned_depth),("valid_mask",valid_mask)):
            if value is not None:arrays[name]=np.asarray(value)
        if aligned_depth is not None:
            if np.asarray(aligned_depth).dtype!=np.float32 or np.asarray(valid_mask).dtype!=np.bool_:
                raise IntegrityError("Aligned metric float32 depth and bool mask required")
        if arrays:
            data=encode_arrays(arrays)
            files["depth"]=_write_immutable(self.root,"observations/"+uid+".depth.npz",data,fault=fault,stage="raw_depth")
        else:files["depth"]=None
        if aligned_depth is not None and (rgb is None or np.shape(aligned_depth)!=rgb.shape[:2]
              or valid_mask is None or np.shape(valid_mask)!=np.shape(aligned_depth)):
            raise IntegrityError("Raw/aligned dimensions mismatch")
        if host_view is not None:
            host=np.asarray(host_view)
            if host.ndim!=3 or host.shape[-1]!=3 or host.dtype!=np.uint8 or host_transform is None:
                raise IntegrityError("Host view needs explicit uint8 pixels and transform provenance")
            if host_transform.get("kind")=="identity" and (rgb is None or not np.array_equal(host,rgb)):
                raise IntegrityError("Identity host transform changed pixels")
            if host_transform.get("kind")=="identity":
                # Pixel equality was checked above. Reuse the already encoded,
                # durable RGB reference instead of encoding the same image again.
                files["host_view"]=dict(files["rgb"])
            else:
                b=io.BytesIO();Image.fromarray(host).save(b,format="PNG")
                files["host_view"]=(_file_ref(self.root,self.root/files["rgb"]["path"],b.getvalue())
                    if files["rgb"]is not None and digest(b.getvalue())==files["rgb"]["sha256"]else
                    _write_immutable(self.root,"observations/"+uid+".host.png",b.getvalue(),fault=fault,stage="host_view"))
        else:files["host_view"]=None
        record=dict(schema_version=SCHEMA,**meta,files=files,arrays={k:array_descriptor(v)for k,v in arrays.items()},
                    host_transform=host_transform,status="archived"if rgb is not None else"raw_rgb_unavailable")
        record["raw_signature"]=digest(canonical(record))
        ref=_write_immutable(self.root,"observations/"+uid+".meta.json",canonical(record),fault=fault,stage="raw_meta")
        self._index_raw(record,ref)
        self._append("execution.jsonl",dict(kind="raw_archived",frame_uid=uid,capture_seq=seq,meta=ref))
        if fault:fault("raw_index_committed")
        return record

    def raw(self,uid):
        row=self.connection.execute("SELECT refs FROM observations WHERE uid=?",(_safe_uid(uid),)).fetchone()
        if row is None:raise KeyError(uid)
        ref=json.loads(row[0])["meta"];record=json.loads(_verify_ref(self.root,ref).read_bytes())
        if record["frame_uid"]!=uid or record["episode_uid"]!=self.episode_uid:raise IntegrityError("Raw SQL/identity mismatch")
        return record

    def read_rgb(self,uid,*,host=False):
        record=self.raw(uid);ref=record["files"]["host_view"if host else"rgb"]
        if ref is None:return None
        path=_verify_ref(self.root,ref)
        def load():
            with Image.open(path)as image:return freeze(np.array(image.convert("RGB")))
        return self.cache.get(ref["sha256"],load)

    def put_arrays(self,arrays):
        data=encode_arrays(arrays);sha=digest(data)
        ref=_write_immutable(self.root,"blobs/"+sha+".npz",data,stage="blob")
        return dict(**ref,arrays={k:array_descriptor(np.asarray(v))for k,v in arrays.items()})

    def get_arrays(self,ref):
        return decode_arrays(_verify_ref(self.root,ref),ref["arrays"])

    def save_tile(self,tile):
        meta,arrays=tile.export()
        halo=meta["halo_cells"];core=meta["core_cells"]
        slices=tuple(slice(halo,halo+int(n))for n in core)
        owned={k:a[slices]for k,a in arrays.items()}
        meta["blob_layout"]="owner_core_only"
        return dict(meta=meta,blob=self.put_arrays(owned))

    def load_tile(self,record):
        from ..geometry.core import TSDFTile
        meta=record["meta"];arrays=self.get_arrays(record["blob"])
        if meta.get("blob_layout")=="owner_core_only":
            bounds=np.asarray(meta["bounds"],float)
            shape=tuple(np.ceil((bounds[:,1]-bounds[:,0])/meta["voxel_size"]).astype(int))
            h=meta["halo_cells"];slices=tuple(slice(h,h+int(n))for n in meta["core_cells"])
            expanded={}
            for name,a in arrays.items():
                if a.shape!=tuple(meta["core_cells"]):raise IntegrityError("Core array descriptor mismatch")
                expanded[name]=np.full(shape,-1 if name=="tsdf"else 0,dtype=a.dtype)
                expanded[name][slices]=a
            arrays=expanded
        return TSDFTile.restore(meta,arrays)

    def save_detections(self,uid,arrays,metadata):
        uid=_safe_uid(uid);raw=self.raw(uid)
        count=metadata["count"]
        if type(count)is not int or count<0:raise IntegrityError("Detection count required")
        rgb_ref=raw["files"]["rgb"]
        if rgb_ref is None:raise IntegrityError("Detections cannot refer to a missing RGB image")
        with Image.open(_verify_ref(self.root,rgb_ref))as image:
            if list(metadata["image_hw"])!=[image.height,image.width]:
                raise IntegrityError("Detection masks belong to a different RGB grid")
        mask=np.asarray(arrays["mask"])
        if mask.dtype!=np.bool_ or mask.shape!=(count,*metadata["image_hw"]):
            raise IntegrityError("Detection mask count/shape/encoding mismatch")
        if np.asarray(arrays["xyxy"]).shape!=(count,4):raise IntegrityError("Detection boxes mismatch")
        for name,value in arrays.items():
            array_descriptor(value)
        ref=_write_immutable(self.root,"detections/"+uid+".npz",encode_arrays(arrays),stage="detections")
        record=dict(frame_uid=uid,blob=dict(**ref,arrays={k:array_descriptor(np.asarray(v))for k,v in arrays.items()}),metadata=metadata)
        _write_immutable(self.root,"detections/"+uid+".meta.json",canonical(record),stage="detection_meta")
        # All immutable files are durable before indexing. One frame is one
        # SQL transaction, not one FULL-sync autocommit per detection.
        savepoint="detections_"+uuid.uuid4().hex
        self.connection.execute("SAVEPOINT "+savepoint)
        try:
            blob=canonical(record["blob"]).decode()
            for index in range(count):
                identity=uid+":d"+format(index,"05d")
                payload=canonical(dict(frame_uid=uid,index=index,metadata=metadata)).decode()
                self._insert_exact("detections",(identity,uid,index,blob,payload),("uid",))
            self.connection.execute("RELEASE SAVEPOINT "+savepoint)
        except BaseException as error:
            if self.connection.in_transaction:
                try:
                    self.connection.execute("ROLLBACK TO SAVEPOINT "+savepoint)
                    self.connection.execute("RELEASE SAVEPOINT "+savepoint)
                except BaseException as rollback_error:error.rollback_error=repr(rollback_error)
            raise
        return record

    def add_execution(self,row):
        uid=row["post"];post=self.raw(uid)
        if row.get("pre")is None:raise IntegrityError("Executed primitive needs a previous capture")
        pre=self.raw(row["pre"])
        if post["capture_seq"]!=pre["capture_seq"]+1:raise IntegrityError("Execution endpoints are not adjacent")
        identity=digest(canonical({"episode_uid":self.episode_uid,"post":uid}))
        payload=canonical(row).decode()
        previous=self.connection.execute("SELECT result FROM executions WHERE post=?",(uid,)).fetchone()
        if previous and previous[0]!=payload:raise IntegrityError("Executed endpoint action changed")
        self.connection.execute("INSERT OR IGNORE INTO executions VALUES(?,?,?,?,?,?)",
          (identity,row.get("pre"),uid,row.get("macro"),row.get("primitive"),payload))
        return identity

    def raw_contract(self,uid):
        return self.raw(uid)

    def _validate_graph(self,graph,versions,cutoff):
        if graph["episode_uid"]!=self.episode_uid:raise IntegrityError("Graph episode mismatch")
        version=versions.get("pose_map_version")
        for uid,view in graph["views"].items():
            meta=self.raw_contract(uid)
            if meta["capture_seq"]>cutoff["capture_seq"] or meta["event_seq"]>cutoff["event_seq"]:
                raise IntegrityError("Future observation in revision")
            if view.get("position_G")is not None:
                if (view.get("pose_map_version")!=version or
                    meta.get("pose_record",{}).get("geometry_status")!="available"):
                    raise IntegrityError("Mixed version or retroactively valid geometry")
                p=np.asarray(view["position_G"],float)
                if p.shape!=(3,)or not np.isfinite(p).all():raise IntegrityError("Invalid spatial view")
        for edge in graph.get("edges",[]):
            if edge["src"]not in graph["views"]or edge["dst"]not in graph["views"]:raise IntegrityError("Dangling edge")
            if edge["type"]not in ("temporal_next","traversed","visibility"):raise IntegrityError("Undeclared edge meaning")
        for entity in graph.get("entities",[]):
            if entity.get("pose_map_version")is not None and entity["pose_map_version"]!=version:
                raise IntegrityError("Mixed entity geometry version")
            for uid in entity.get("view_uids",[]):
                if uid not in graph["views"]:raise IntegrityError("Dangling object/view reference")
        for tile in graph.get("tiles",{}).values():
            if tile["pose_map_version"]!=version:raise IntegrityError("Mixed tile geometry version")
        semantic=semantic_reference_checks(graph,versions)
        if semantic["errors"]:raise IntegrityError("Candidate semantic reference violation: "+",".join(semantic["errors"]))
        canonical(graph);canonical(versions);canonical(cutoff)



    def _insert_exact(self,table,values,keys):
        if not hasattr(self,"_table_columns"):self._table_columns={}
        if table not in self._table_columns:
            self._table_columns[table]=[x[1]for x in self.connection.execute("PRAGMA table_info("+table+")")]
        columns=self._table_columns[table]
        where=" AND ".join(x+"=?"for x in keys)
        parameters=tuple(values[columns.index(x)]for x in keys)
        actual=self.connection.execute("SELECT * FROM "+table+" WHERE "+where,parameters).fetchone()
        if actual is not None:
            if actual!=tuple(values):raise IntegrityError("Immutable SQL row differs: "+table)
            return
        self.connection.execute("INSERT INTO "+table+" VALUES("+",".join("?"for _ in values)+")",values)
        actual=self.connection.execute("SELECT * FROM "+table+" WHERE "+where,parameters).fetchone()
        if actual!=tuple(values):raise IntegrityError("Immutable SQL row differs: "+table)

    def close(self):
        if getattr(self,"cache",None)is not None:self.cache.clear()
        if getattr(self,"connection",None)is not None:self.connection.close();self.connection=None
        if getattr(self,"_lock",None)is not None:
            fcntl.flock(self._lock,fcntl.LOCK_UN);self._lock.close();self._lock=None

class LegacySnapshotReader:
    def __init__(self,path,revision="CURRENT",*,cache_bytes=128*1024*1024):
        self.root=Path(path).absolute();self.identity=json.loads((self.root/"episode_identity.json").read_bytes())
        if revision=="CURRENT":
            try:self.pointer=json.loads((self.root/"CURRENT.json").read_bytes())
            except FileNotFoundError:raise NoPublishedSnapshot("No committed snapshot")
            manifest_path=_verify_ref(self.root,self.pointer["manifest"])
            self.snapshot_id=self.pointer["snapshot_id"]
        else:
            if not isinstance(revision,str)or not re.fullmatch("[a-f0-9]{64}",revision):raise IntegrityError("Invalid revision")
            pointer_file=self.root/"CURRENT.json"
            if not pointer_file.exists():raise NoPublishedSnapshot("No committed ancestor chain")
            current=json.loads(pointer_file.read_bytes());seen=set()
            ancestor=current["snapshot_id"]
            while ancestor is not None and ancestor!=revision:
                if ancestor in seen:raise IntegrityError("Revision parent cycle")
                seen.add(ancestor)
                parent_manifest=read_manifest(self.root,ancestor,current["manifest"]if ancestor==current["snapshot_id"]else None)
                ancestor=parent_manifest["parent"]
            if ancestor!=revision:raise NoPublishedSnapshot("Requested revision is an uncommitted orphan")
            self.snapshot_id=revision;manifest_path=self.root/"revisions"/revision/"manifest.json"
            self.pointer=None
        self.manifest=read_manifest(self.root,self.snapshot_id,self.pointer["manifest"]if self.pointer else None)
        if self.manifest["episode_uid"]!=self.identity["episode_uid"]:raise IntegrityError("Manifest episode mismatch")
        self.connection=sqlite3.connect("file:"+str(self.root/"index.sqlite3")+"?mode=ro",uri=True,isolation_level=None)
        self.connection.execute("PRAGMA query_only=ON");self.connection.execute("PRAGMA foreign_keys=ON")
        row=self.connection.execute("SELECT manifest_hash FROM revisions WHERE id=?",(self.snapshot_id,)).fetchone()
        if row is None or row[0]!=file_hash(manifest_path):raise IntegrityError("Manifest/SQLite revision mismatch")
        graph_path=_verify_ref(self.root,self.manifest["graph"])
        self._graph=json.loads(graph_path.read_bytes())
        self.versions=freeze(self.manifest["versions"]);self.cutoff=freeze(self.manifest["cutoff"])
        self.cache=ByteLRU(cache_bytes*3//4)
        self._history_cache=ByteLRU(cache_bytes-cache_bytes*3//4);self._lineage=None

    def iter_verified_history(self):
        sid=self.snapshot_id;seen=set();seen_refs=set();cutoff=None
        while sid is not None:
            if sid in seen:raise IntegrityError("Revision parent cycle")
            seen.add(sid);manifest=read_manifest(self.root,sid)
            path=self.root/"revisions"/sid/"manifest.json"
            sql=self.connection.execute("SELECT manifest_hash FROM revisions WHERE id=?",(sid,)).fetchone()
            if sql is None or sql[0]!=file_hash(path):raise IntegrityError("Historical manifest/SQL mismatch")
            if manifest["episode_uid"]!=self.identity["episode_uid"]:raise IntegrityError("Historical episode mismatch")
            if cutoff is not None and any(manifest["cutoff"][k]>cutoff[k]for k in ("capture_seq","event_seq")):
                raise IntegrityError("Historical cutoff exceeds pinned revision")
            for ref in [manifest["graph"],*manifest["files"]]:
                key=(ref["path"],ref["sha256"],ref["bytes"])
                if key not in seen_refs:_verify_ref(self.root,ref);seen_refs.add(key)
            graph=json.loads((self.root/manifest["graph"]["path"]).read_bytes())
            members={x[0]for x in self.connection.execute("SELECT frame FROM revision_observations WHERE revision=?",(sid,))}
            if members!=set(graph["views"]):raise IntegrityError("Historical SQL view membership mismatch")
            checks=semantic_reference_checks(graph,manifest["versions"])
            if checks["errors"]:raise IntegrityError("Historical semantic reference violation: "+",".join(checks["errors"]))
            yield dict(snapshot_id=sid,parent=manifest["parent"],graph=graph,versions=manifest["versions"],
                cutoff=manifest["cutoff"],verified_unique_files=len(seen_refs))
            cutoff=manifest["cutoff"];sid=manifest["parent"]

    def require_pose_version(self,episode_uid,map_version):
        if episode_uid!=self.identity["episode_uid"]or map_version!=self.versions["pose_map_version"]:
            raise VersionUnavailable("Pinned geometry/current pose mismatch;nonspatial images remain readable")

    def get_view(self,uid,*,include_images=True,include_depth=False):
        row=self.connection.execute("SELECT payload FROM revision_observations WHERE revision=? AND frame=?",(self.snapshot_id,uid)).fetchone()
        if row is None:raise KeyError(uid)
        view=json.loads(row[0])
        if canonical(view)!=canonical(self._graph["views"].get(uid)):raise IntegrityError("View SQL/manifest mismatch")
        entry=next(x for x in self.manifest["observations"]if x["uid"]==uid)
        meta=json.loads(_verify_ref(self.root,entry["refs"]["meta"]).read_bytes())
        value=dict(view,snapshot_id=self.snapshot_id,capture=meta,raw_rgb_ref=entry["refs"]["rgb"],host_view_ref=entry["refs"]["host_view"])
        if include_images:
            for key,name in (("raw_rgb","rgb"),("host_view","host_view")):
                ref=entry["refs"][name]
                if ref is None:value[key]=None;continue
                p=_verify_ref(self.root,ref)
                def load(p=p):
                    with Image.open(p)as img:return freeze(np.array(img.convert("RGB")))
                value[key]=self.cache.get(ref["sha256"],load)
        if include_depth and entry["refs"]["depth"] is not None:
            value["depth"]=decode_arrays(_verify_ref(self.root,entry["refs"]["depth"]),meta["arrays"])
        return freeze(value)

    def _lineage_ranks(self):
        if self._lineage is None:
            ranks={};sid=self.snapshot_id;cutoff=self.manifest["cutoff"]
            while sid is not None:
                if sid in ranks:raise IntegrityError("Revision parent cycle")
                manifest=read_manifest(self.root,sid)
                if manifest["episode_uid"]!=self.identity["episode_uid"]:raise IntegrityError("Historical episode mismatch")
                if any(manifest["cutoff"][k]>cutoff[k]for k in ("capture_seq","event_seq")):
                    raise IntegrityError("Historical revision exceeds pinned cutoff")
                row=self.connection.execute("SELECT manifest_hash FROM revisions WHERE id=?",(sid,)).fetchone()
                if row is None or row[0]!=file_hash(self.root/"revisions"/sid/"manifest.json"):
                    raise IntegrityError("Historical manifest/SQL mismatch")
                ranks[sid]=len(ranks);cutoff=manifest["cutoff"];sid=manifest["parent"]
            self._lineage=ranks
        return self._lineage

    def _revision_graph(self,revision):
        if revision==self.snapshot_id:return self._graph
        if revision not in self._lineage_ranks():raise NoPublishedSnapshot("Object source is not a pinned ancestor")
        manifest=read_manifest(self.root,revision)
        def load():
            return np.frombuffer(_verify_ref(self.root,manifest["graph"]).read_bytes(),dtype=np.uint8)
        data=self._history_cache.get((revision,manifest["graph_sha256"]),load)
        return json.loads(data.tobytes())

    def _object_row(self,table,epoch,native_id):
        # Keys are fixed table schemas,not caller-provided SQL. Look only at
        # the reader's exact revision/ancestor ranks;never max(revision),a
        # prepared orphan or a newer CURRENT published after this reader pinned.
        if table=="aliases":column,collection,key="src","aliases","src"
        elif table=="entities":column,collection,key="id","entities","id"
        else:raise IntegrityError("Invalid object lookup table")
        current=self.connection.execute("SELECT payload FROM "+table+" WHERE epoch=? AND "+column+"=? AND revision=?",
            (epoch,native_id,self.snapshot_id)).fetchone()
        if current:revision,payload=self.snapshot_id,current[0]
        else:
            ranks=self._lineage_ranks()
            choices=[(ranks[rev],rev,payload)for rev,payload in self.connection.execute(
                "SELECT revision,payload FROM "+table+" WHERE epoch=? AND "+column+"=?",(epoch,native_id))if rev in ranks]
            if not choices:return None,None
            _,revision,payload=min(choices,key=lambda x:x[0])
        value=json.loads(payload)
        signed=next((x for x in self._revision_graph(revision).get(collection,[])
            if (x["epoch"],x[key])==(epoch,native_id)),None)
        if signed is None or canonical(value)!=canonical(signed):raise IntegrityError("Object SQL/manifest mismatch")
        return value,revision

    def get_object(self,epoch,native_id,revision=None):
        if revision is not None and revision!=self.snapshot_id:raise VersionUnavailable("Reader pinned to another revision")
        visited=set();requested=(epoch,native_id)
        while True:
            if (epoch,native_id)in visited:raise IntegrityError("Alias cycle")
            visited.add((epoch,native_id))
            alias,source_revision=self._object_row("aliases",epoch,native_id)
            if alias is None:break
            if alias.get("status")=="ambiguous":
                return freeze(dict(status="ambiguous",requested=requested,candidates=alias["candidates"],
                    snapshot_id=self.snapshot_id,source_revision=source_revision))
            if alias.get("dst")is None:break
            epoch,native_id=alias["dst_epoch"],alias["dst"]
        entity,source_revision=self._object_row("entities",epoch,native_id)
        if entity is None:raise KeyError((epoch,native_id))
        current_epoch=self._graph.get("scene_state",{}).get("epoch")
        if current_epoch is not None and entity["epoch"]!=current_epoch:
            if entity["status"]not in ("retired","historical","ambiguous"):
                raise IntegrityError("Historical active entity has no pinned transition")
            # An immutable historical source remains inspectable at its own
            # revision. Current retired/tombstone results expose no stale pose.
            entity=dict(entity,attributes=None,pose_map_version=None)
        return freeze(dict(entity,snapshot_id=self.snapshot_id,requested=requested,
            source_revision=entity.get("source_revision",source_revision)))

    def get_geometry(self,tile_id,revision=None):
        if revision is not None and revision!=self.snapshot_id:raise VersionUnavailable("Reader pinned to another revision")
        tile=self._graph.get("tiles",{}).get(tile_id)
        if tile is None:raise KeyError(tile_id)
        if tile["pose_map_version"]!=self.versions["pose_map_version"]:raise IntegrityError("Mixed tile version")
        ref=tile["record"]["blob"];arrays=decode_arrays(_verify_ref(self.root,ref),ref["arrays"])
        return freeze(dict(submap_id=tile_id,snapshot_id=self.snapshot_id,pose_map_version=tile["pose_map_version"],
                           metadata=tile["record"]["meta"],arrays=arrays,
                           array_origin_Nlocal=[0.,0.,0.],core_cells=tile["record"]["meta"]["core_cells"]))

    def get_trace(self,start=0,end=None):
        end=self.cutoff["capture_seq"]if end is None else min(end,self.cutoff["capture_seq"])
        rows=self.connection.execute("""SELECT executions.result FROM executions
          JOIN observations ON observations.uid=executions.post
          JOIN revision_observations ON revision_observations.frame=observations.uid
          WHERE revision_observations.revision=? AND observations.seq>=? AND observations.seq<=?
          ORDER BY observations.seq""",(self.snapshot_id,start,end)).fetchall()
        known={x["id"]:x["sha256"]for x in self.manifest.get("executions",[])}
        result=[]
        for row in rows:
            payload=json.loads(row[0]);identity=digest(canonical({"episode_uid":self.identity["episode_uid"],"post":payload["post"]}))
            if known.get(identity)!=digest(row[0].encode()):raise IntegrityError("Execution SQL/manifest mismatch")
            result.append(payload)
        return freeze(result)

    def _verify_semantic_references(self):
        graph=self._graph;result=semantic_reference_checks(graph,self.versions)
        for table,key,collection in (("entities","id","entities"),("aliases","src","aliases"),("edges","id","edges")):
            expected={((x["epoch"],x[key])if table!="edges"else x[key]):x for x in graph.get(collection,[])}
            actual={}
            for payload, in self.connection.execute("SELECT payload FROM "+table+" WHERE revision=?",(self.snapshot_id,)):
                value=json.loads(payload);identity=(value["epoch"],value[key])if table!="edges"else value[key]
                actual[identity]=value
            if actual!=expected:result["errors"].append(table+"_SQL_payload_mismatch")
        expected={(uid,e["epoch"],e["id"])for e in graph.get("entities",[])for uid in e.get("view_uids",[])}
        actual=set(self.connection.execute("SELECT frame,epoch,entity FROM view_objects WHERE revision=?",(self.snapshot_id,)))
        if actual!=expected:result["errors"].append("view_objects_SQL_membership")
        expected={(x["frame_uid"],x["tile_id"]):x["pose_binding"]for x in graph.get("contributions",[])}
        actual={(frame,tile):json.loads(binding)for frame,tile,binding in self.connection.execute(
            "SELECT frame,tile,pose_binding FROM contributions WHERE revision=?",(self.snapshot_id,))}
        if actual!=expected:result["errors"].append("contributions_SQL_payload")
        for alias in graph.get("aliases",[]):self.get_object(alias["epoch"],alias["src"])
        return result

    def verify(self,*,hashes=True,references=True):
        views=self._graph["views"];semantic=None
        if references:
            sql={x[0]for x in self.connection.execute("SELECT frame FROM revision_observations WHERE revision=?",(self.snapshot_id,))}
            if sql!=set(views):raise IntegrityError("Graph/SQL view membership differs")
            if self.connection.execute("PRAGMA foreign_key_check").fetchall():raise IntegrityError("Database reference violation")
            for edge in self._graph.get("edges",[]):
                if edge["src"]not in views or edge["dst"]not in views:raise IntegrityError("Dangling graph edge")
            semantic=self._verify_semantic_references()
            if semantic["errors"]:raise IntegrityError("Semantic reference violation: "+",".join(semantic["errors"]))
        files=0
        if hashes:
            for ref in self.manifest.get("files",owned_references(self._graph)):
                _verify_ref(self.root,ref);files+=1
        return dict(status="VERIFIED",snapshot_id=self.snapshot_id,views=len(views),verified_files=files,reference_checks=semantic,
                    scope="stored snapshot integrity,not navigation or detector quality")

    def close(self):self.connection.close();self.cache.clear();self._history_cache.clear()

