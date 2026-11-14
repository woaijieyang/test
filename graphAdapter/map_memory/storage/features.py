"""Selective, immutable camera features reused across pinned map revisions.

No RGB decoding, perception inference, world-coordinate cache or simulator access.
The owner is one episode's retrieval session; close it at episode end.
"""
from collections import OrderedDict
from pathlib import Path
from types import MappingProxyType
import zipfile
import numpy as np
from .archive import IntegrityError,UnavailableMaterial, array_descriptor, canonical, digest, freeze
from .pages import ImmutableVerifier


def decode_feature_arrays(path, expected, names, *, max_bytes=64*1024*1024):
    names = tuple(names)
    if len(set(names)) != len(names) or not set(names) <= set(expected):
        raise IntegrityError('Invalid feature field selection')
    if sum(expected[k]['bytes'] for k in names) > max_bytes:
        raise IntegrityError('Selected features exceed byte budget')
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) != len(expected) or {e.filename for e in entries} != {k+'.npy' for k in expected}:
                raise IntegrityError('Feature bundle names or duplicate ZIP members')
            selected = [e for e in entries if e.filename[:-4] in names]
            if sum(e.file_size for e in selected) > max_bytes + 4096*len(names):
                raise IntegrityError('Selected feature expansion exceeds budget')
        with np.load(path, allow_pickle=False) as archive:
            result = {}
            for name in names:
                value = archive[name]
                description = dict(expected[name], shape=list(expected[name]['shape']))
                if array_descriptor(value) != description:
                    raise IntegrityError('Feature shape/dtype/size mismatch: '+name)
                result[name] = freeze(value)
        return result
    except (OSError, ValueError, EOFError, zipfile.BadZipFile, KeyError) as error:
        raise UnavailableMaterial('undecodable_features') from error


def _validate_arrays(arrays,metadata):
    count=metadata['count']
    if 'class_id' in arrays:
        classes=arrays['class_id']
        if classes.shape!=(count,) or classes.dtype.kind not in 'iu' or np.any(classes<0):
            raise IntegrityError('Invalid original detection class IDs')
    if 'confidence' in arrays:
        confidence=arrays['confidence']
        if (confidence.shape!=(count,) or confidence.dtype.kind!='f' or not np.isfinite(confidence).all()
                or np.any((confidence<0)|(confidence>1))):
            raise IntegrityError('Invalid detection confidence')
    if 'xyxy' in arrays and arrays['xyxy'].shape!=(count,4):
        raise IntegrityError('Selected box array size differs from detection metadata')
    objects=arrays.get('image_feats')
    if objects is not None:
        if objects.dtype.kind!='f' or not np.isfinite(objects).all():
            raise IntegrityError('Invalid object feature values')
        if not ((objects.ndim==2 and objects.shape[0]==count and objects.shape[1]>0)
                or (count==0 and objects.shape==(0,))):
            raise IntegrityError('Object feature count/dimension mismatch')
        if count and np.any(np.linalg.norm(objects,axis=1)==0):
            raise IntegrityError('Zero object feature is not retrieval evidence')
    full=arrays.get('full_clip')
    if full is not None:
        if full.ndim!=1 or not full.size or full.dtype.kind!='f' or not np.isfinite(full).all() or np.linalg.norm(full)==0:
            raise IntegrityError('Invalid full-image feature')
        if objects is not None and objects.ndim==2 and objects.shape[1]!=full.size:
            raise IntegrityError('Image/object feature dimensions differ')


class EpisodeFeatureCache:
    """One-root byte-bounded cache; only immutable camera-space feature arrays."""
    def __init__(self, root, *, max_bytes=64*1024*1024):
        if type(max_bytes) is not int or max_bytes < 0:
            raise ValueError('Nonnegative feature cache budget required')
        self.root = Path(root).resolve()
        self.max_bytes = max_bytes
        self.bytes = self.peak_bytes = self.hits = self.decodes = 0
        self.items = OrderedDict()
        self.verifier = ImmutableVerifier()
        self.closed = False

    def _retain(self,key,value,size):
        if not 0<size<=self.max_bytes:
            return
        while self.items and self.bytes+size>self.max_bytes:
            _,(_,removed)=self.items.popitem(last=False)
            self.bytes-=removed
        self.items[key]=(value,size)
        self.bytes+=size
        self.peak_bytes=max(self.peak_bytes,self.bytes)

    def read_fields(self,root,record,names):
        """Resolve immutable camera arrays by field, sharing one episode LRU across all read modes."""
        if self.closed or Path(root).resolve()!=self.root:
            raise IntegrityError('Feature cache is closed or belongs to another episode root')
        ref,meta=record['blob'],record['metadata']
        path=self.verifier.verify(self.root,ref)
        if ('full_clip' in ref['arrays'])!=meta['has_full_clip']:
            raise IntegrityError('Full-image feature availability differs from descriptor')
        key=digest(canonical(record))
        previous=self.items.get(key)
        arrays=dict(previous[0]) if previous is not None else {}
        if previous is not None:self.items.move_to_end(key)
        missing=[name for name in names if name not in arrays]
        if not missing:
            self.hits+=1
            return MappingProxyType({name:arrays[name] for name in names})
        before=path.stat()
        try:loaded=decode_feature_arrays(path,ref['arrays'],missing)
        except UnavailableMaterial:
            self.verifier.verify(self.root,ref)
            raise
        after=path.stat()
        signature=lambda st:(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        if signature(before)!=signature(after):raise IntegrityError('Feature payload changed during decode')
        self.verifier.verify(self.root,ref)
        arrays.update(loaded)
        fields={name:arrays[name] for name in names}
        _validate_arrays(fields,meta)
        self.decodes+=1
        size=sum(value.nbytes for value in arrays.values())
        if 0<size<=self.max_bytes:
            if previous is not None:
                del self.items[key]
                self.bytes-=previous[1]
            self._retain(key,MappingProxyType(arrays),size)
        return MappingProxyType(fields)

    def read_boxes(self,root,record):
        return self.read_fields(root,record,('xyxy',))['xyxy']

    def read(self,root,record,*,classes_only=False):
        if classes_only:
            return self.read_fields(root,record,('class_id',))['class_id']
        names=['class_id','confidence','image_feats']
        if record['metadata']['has_full_clip']:names.append('full_clip')
        return self.read_fields(root,record,names)

    def close(self):
        self.items.clear()
        self.verifier.cache.clear()
        self.bytes = 0
        self.closed = True


def feature_reference(reader, uid):
    view=reader._graph['views'][uid]
    capture=reader.materializer.capture(uid)
    if (view['frame_uid'] != uid or capture['frame_uid'] != uid or capture['episode_uid'] != reader.identity['episode_uid']
            or capture['capture_seq'] != view['capture_seq']
            or capture['capture_seq'] > reader.cutoff['capture_seq']
            or capture['event_seq'] > reader.cutoff['event_seq']):
        raise IntegrityError('Feature frame/episode/cutoff identity mismatch')
    # Use the pinned JSON value for canonical provenance encoding, not a later CURRENT.
    record = view.get('detection_record')
    if record is None:
        return freeze(dict(status='unavailable', reason='no_detection_record',
                           frame_uid=uid, snapshot_id=reader.snapshot_id))
    meta = record['metadata']
    model = reader._graph.get('model_identity')
    if (record['frame_uid'] != uid or meta.get('raw_signature') != capture['raw_signature']
            or not model or meta.get('model_identity_hash') != digest(canonical(model))):
        raise IntegrityError('Feature raw-frame/model provenance mismatch')
    if type(meta.get('count')) is not int or meta['count'] < 0 or type(meta.get('has_full_clip')) is not bool:
        raise IntegrityError('Invalid feature count/availability metadata')
    return freeze(dict(status='available', frame_uid=uid, snapshot_id=reader.snapshot_id,
                       capture_seq=view['capture_seq'], source_ref=record['blob'],
                       raw_signature=capture['raw_signature'], model_identity=model,
                       model_identity_hash=meta['model_identity_hash']))


def view_features(reader, uid):
    reference = feature_reference(reader, uid)
    if reference['status'] != 'available':
        return reference
    record = reader._graph['views'][uid]['detection_record']
    arrays = reader._feature_cache.read(reader.root, record)
    # No world positions/poses are cached or silently carried across revisions.
    return MappingProxyType(dict(reference, full_clip=arrays.get('full_clip'),
                       object_clip=arrays['image_feats'], class_ids=arrays['class_id'],
                       confidence=arrays['confidence']))


DOOR_ARRAYS=("door_proposal_indices","door_xyxy","door_confidence","door_mask_bits")

def check_door_arrays(arrays,count,height,width,*,include_masks=True):
    if type(count) is not int or count<0:
        raise IntegrityError("Invalid structural candidate count")
    names=set(arrays).intersection(DOOR_ARRAYS)
    if not count and not names:return
    expected=set(DOOR_ARRAYS if include_masks else DOOR_ARRAYS[:-1])
    if not count or names!=expected:raise IntegrityError("Incomplete structural candidate bundle")
    indices,boxes,confidence=(np.asarray(arrays[n]) for n in DOOR_ARRAYS[:-1])
    if (indices.shape!=(count,) or indices.dtype.kind not in "iu" or np.any(indices<0)
            or (count>1 and not np.all(indices[1:]>indices[:-1]))
            or boxes.shape!=(count,4) or not np.isfinite(boxes).all()
            or confidence.shape!=(count,) or not np.isfinite(confidence).all()
            or np.any((confidence<0)|(confidence>1))):
        raise IntegrityError("Invalid structural observation arrays")
    if include_masks:
        masks=np.asarray(arrays["door_mask_bits"])
        if masks.dtype!=np.uint8 or masks.shape!=(count,height,(width+7)//8):
            raise IntegrityError("Invalid structural observation arrays")


def observed_doors(reader,uid,*,include_masks=True):
    ref=feature_reference(reader,uid)
    if ref["status"]!="available":return ref
    meta=reader._graph["views"][uid]["detection_record"]["metadata"]
    if "door_candidate_count" not in meta:
        return freeze(dict(status="not_recorded",frame_uid=uid,snapshot_id=reader.snapshot_id))
    count=meta["door_candidate_count"]
    blob=ref["source_ref"];fields={}
    if count:
        h,w=meta['image_hw'];desc=blob['arrays'].get('door_mask_bits',{})
        if list(desc.get('shape',[]))!=[count,h,(w+7)//8] or desc.get('dtype')!='|u1':
            raise IntegrityError('Structural mask descriptor differs from the source grid')
        record=reader._graph['views'][uid]['detection_record']
        fields=reader._feature_cache.read_fields(reader.root,record,DOOR_ARRAYS if include_masks else DOOR_ARRAYS[:-1])
    elif set(blob["arrays"]).intersection(DOOR_ARRAYS):
        raise IntegrityError("Door arrays recorded without candidates")
    h,w=meta["image_hw"];check_door_arrays(fields,count,h,w,include_masks=include_masks)
    return freeze(dict(status="available",frame_uid=uid,snapshot_id=reader.snapshot_id,
                       source_ref=blob,raw_signature=ref["raw_signature"],image_hw=(h,w),count=count,
                       evidence_scope="pre_foreground_filter_2d_door_proposals",**fields))


def view_class_ids(reader, uid, *, include_boxes=False, include_confidence=False):
    ref=feature_reference(reader,uid)
    if ref["status"]!="available":return ref
    record=reader._graph["views"][uid]["detection_record"]
    names=['class_id']
    if include_confidence:names.append('confidence')
    if include_boxes:names.append('xyxy')
    values=reader._feature_cache.read_fields(reader.root,record,names)
    result=dict(ref,class_ids=values['class_id'])
    for field in names[1:]:result[field]=values[field]
    return MappingProxyType(result)
