"""Verified historical RGB materialization and bounded evidence-only text.

The original host sampler and processor remain caller-owned. This module never
runs a simulator, model, navigation parser, or action executor.
"""

from dataclasses import dataclass
from collections.abc import Mapping
from hashlib import sha256
import numpy as np
from PIL import Image
from ..storage.archive import IntegrityError, canonical, digest
import json
import re


def plain(value):
    if isinstance(value,Mapping):return {k:plain(v)for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [plain(v)for v in value]
    return value


def pixel_hash(value):
    a=np.asarray(value)
    if a.dtype!=np.uint8 or a.ndim!=3 or a.shape[2]!=3:
        raise IntegrityError('Host image must be original uint8 RGB')
    return sha256(canonical(dict(shape=list(a.shape),dtype=a.dtype.str))+np.ascontiguousarray(a).tobytes()).hexdigest()

@dataclass(frozen=True)
class ImageSlot:
    index: int
    frame_uid: str | None
    env_step: int | None
    sensor_seq: int | None
    source_kind: str
    evidence_group: tuple
    source_image_hash: str | None
    host_image_hash: str | None
    host_view_transform_hash: str | None
    raw_pixel_hash: str | None
    host_pixel_hash: str
    is_current: bool
    source_snapshot_id: str | None = None

@dataclass(frozen=True)
class PreparedHistory:
    images: tuple
    slots: tuple[ImageSlot,...]
    snapshot_id: str
    budget: int

@dataclass(frozen=True)
class RecordedFact:
    kind: str
    slots: tuple[int,...]
    source_ref: str

    def render(self):
        if self.kind=='movement'and len(self.slots)==2:
            return f'Images {self.slots[0]} and {self.slots[1]} have a recorded movement connection (historical).'
        if self.kind=='object_association'and len(self.slots)>=2:
            return 'Images '+', '.join(map(str,self.slots))+' share a stored object association (uncertain).'
        raise IntegrityError('Unsupported structured historical fact')

@dataclass(frozen=True)
class LandmarkFact:
    slots: tuple[int,...]
    label: str
    source_ref: str

    def render(self):
        import re
        if len(self.slots)!=1 or not re.fullmatch(r"[a-z0-9][a-z0-9 -]{0,60}",self.label):
            raise IntegrityError('Invalid detector label or image reference')
        return f'Image {self.slots[0]}: possible {self.label} in this historical view.'


def grounded_fact_lines(history, detections, reader, vocabulary):
    """Resolve each candidate label against the actual selected archival detection."""
    slots={slot.frame_uid:slot for slot in history.slots if slot.frame_uid and not slot.is_current}
    seen=set();facts=[]
    for source in detections:
        uid=source['frame_uid'];slot=slots.get(uid)
        if slot is None:continue
        row=reader.get_view_features(uid);i=source['detection_index']
        if (row['status']!='available' or row['snapshot_id']!=history.snapshot_id
                or row['source_ref']['sha256']!=source['source_ref'] or row['raw_signature']!=source['raw_signature']
                or vocabulary.source_sha256!=source['vocabulary_sha256'] or type(i)is not int
                or not 0<=i<len(row['class_ids'])):
            raise IntegrityError('Landmark fact lost its pinned detection source')
        class_id=int(row['class_ids'][i])
        if not 0<=class_id<len(vocabulary.labels) or class_id!=source['class_id'] or vocabulary.labels[class_id]!=source['label']:
            raise IntegrityError('Landmark label differs from the original detection')
        key=(slot.index,source['label'])
        if key not in seen:
            facts.append(LandmarkFact((slot.index,),source['label'],f'{uid}:d{i:05d}'));seen.add(key)
    return tuple(facts)

@dataclass(frozen=True)
class SpatialFact:
    slots: tuple[int,...]
    source_ref: str
    relative_current_cv: tuple[float,float,float]
    pose_map_version: int

    def render(self):
        x,y,z=self.relative_current_cv
        distance=float(np.linalg.norm((x,y,z)))
        lateral='right'if x>0.05 else 'left'if x<-.05 else 'near the centerline'
        depth='ahead'if z>.05 else 'behind'if z<-.05 else 'near the current camera plane'
        return (f'Object association from image {self.slots[0]}: estimated straight-line distance '
                f'about {distance:.1f} m from the current camera, {lateral}, {depth}.')


def relative_spatial_fact(position_G,*,entity_pose_version,current_T_G_cv,current_pose_version,source_slot,source_ref):
    # No spatial facts from missing/mixed versions; historical RGB stays eligible.
    if position_G is None or current_T_G_cv is None or entity_pose_version is None or current_pose_version is None or entity_pose_version!=current_pose_version:
        return None
    if type(current_pose_version)is not int or current_pose_version<0 or type(source_slot)is not int or source_slot<1:
        raise IntegrityError('Versioned entity and selected slot identity required')
    position=np.asarray(position_G,dtype=float);transform=np.asarray(current_T_G_cv,dtype=float)
    if position.shape!=(3,)or transform.shape!=(4,4)or not np.isfinite(position).all()or not np.isfinite(transform).all():
        raise IntegrityError('Invalid spatial fact source geometry')
    rotation=transform[:3,:3]
    if not np.allclose(transform[3],[0,0,0,1],atol=1e-7)or not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-5)or not np.isclose(np.linalg.det(rotation),1.,atol=1e-5):
        raise IntegrityError('Current optical camera transform is not rigid')
    relative=rotation.T@(position-transform[:3,3])
    return SpatialFact((source_slot,),source_ref,tuple(float(v)for v in relative),current_pose_version)

@dataclass(frozen=True)
class CompiledQuestion:
    question: str
    added_tokens: int
    dropped_facts: int
    fallback_reason: str | None


def materialize_history(selection,reader,current_rgb,*,current,sampler,width=512,height=512):
    if selection.fallback_reason or not selection.slots:
        raise ValueError('Fallback selections must use the unchanged original host history')
    if reader.snapshot_id!=current.snapshot_id or reader.identity['episode_uid']!=current.episode_uid:
        raise IntegrityError('Materialization reader/current identity mismatch')
    if selection.slots[-1]!=current or len(selection.slots)>selection.budget:
        raise IntegrityError('Selection lost the current frame or exceeded host budget')
    if list(selection.slots)!=sorted(selection.slots,key=lambda v:(v.capture_seq,v.frame_uid)):
        raise IntegrityError('Selected frames are not in capture order')
    groups={v.frame_uid:tuple(i for i,b in enumerate(selection.groups)if any(x.frame_uid==v.frame_uid for x in b.views))for v in selection.slots}
    images=[];records=[];live=np.asarray(current_rgb);live_hash=pixel_hash(live)
    for ref in selection.slots:
        if ref.episode_uid!=current.episode_uid or ref.snapshot_id!=reader.snapshot_id:
            raise IntegrityError('Cross-episode/snapshot materialization')
        is_current=ref.frame_uid==current.frame_uid
        row=None
        try:row=reader.get_view(ref.frame_uid,include_images=True,include_depth=False)
        except KeyError:
            if not is_current or ref.capture_seq<=reader.cutoff['capture_seq']:raise
            if ref.source_snapshot_id is not None:
                from ..storage.store import load_episode
                materializer=getattr(reader,'materializer',None)
                cache=None if getattr(materializer,'owns_image_cache',True) else materializer.image_cache
                source_reader=load_episode(reader.root,revision=ref.source_snapshot_id,image_cache=cache,_history_cache=getattr(reader,'history_page_cache',None))
                try:
                    if source_reader.identity['episode_uid']!=current.episode_uid or source_reader.cutoff['capture_seq']!=current.capture_seq:
                        raise IntegrityError('Current source snapshot is not the exact current observation frontier')
                    row=source_reader.get_view(ref.frame_uid,include_images=True,include_depth=False)
                finally:source_reader.close()
        if row is None:
            # The live host RGB is available before its asynchronous map update.
            # Do not claim a pinned historical archive proof for this current image.
            rgb=live;raw_hash=None;kind='host_current_unpublished'
        else:
            capture=row['capture']
            if (row['frame_uid']!=ref.frame_uid or row['snapshot_id']!=(ref.source_snapshot_id if is_current and ref.source_snapshot_id is not None else reader.snapshot_id)
                    or capture['episode_uid']!=ref.episode_uid or capture['frame_uid']!=ref.frame_uid
                    or row['capture_seq']!=ref.capture_seq):
                raise IntegrityError('Materialized raw frame differs from selected frame')
            if is_current and ref.source_snapshot_id is not None:
                xyz=row.get('position_G')
                position=None if xyz is None else tuple(float(component) for component in xyz)
                version=row.get('pose_map_version')
                if (ref.position!=position or ref.pose_map_version!=version or type(ref.pose_map_version)is not type(version)
                        or ref.event_seq!=capture['event_seq'] or ref.env_step!=capture['env_step']):
                    raise IntegrityError('Current geometry or clock differs from the pinned camera')
            if row['raw_rgb_ref']['sha256']!=ref.image_hash or row['host_view_ref']['sha256']!=ref.host_image_hash:
                raise IntegrityError('Selected source image identity differs')
            transform=digest(canonical(plain(capture.get('host_transform'))))
            if transform!=ref.host_transform_hash:raise IntegrityError('Selected host transform identity differs')
            raw_hash=pixel_hash(row['raw_rgb']);rgb=row['host_view']
            if is_current and pixel_hash(rgb)!=live_hash:raise IntegrityError('Current archived host RGB differs from actual host RGB')
            kind='host_current'if is_current else 'archived_host_view'
        host_hash=pixel_hash(rgb)
        images.append(Image.fromarray(np.asarray(rgb).copy(),'RGB'))
        records.append(ImageSlot(0,ref.frame_uid,ref.env_step,ref.capture_seq,kind,groups[ref.frame_uid],
            ref.image_hash,ref.host_image_hash,ref.host_transform_hash,raw_hash,host_hash,is_current,
            row['snapshot_id']if row is not None else None))
    # Selection never exceeds B: native sampler therefore only prepends padding,
    # and its original linspace leaves the chosen real frames in exact order.
    output=tuple(sampler(images,num_frames=selection.budget,width=width,height=height))
    padding=selection.budget-len(images)
    black=np.zeros((height,width,3),dtype=np.uint8);black_hash=pixel_hash(black)
    expected=[black_hash]*padding+[row.host_pixel_hash for row in records]
    if len(output)!=selection.budget or [pixel_hash(image)for image in output]!=expected:
        raise IntegrityError('Native sampler changed selected frames/padding/order')
    from dataclasses import replace
    slots=[ImageSlot(0,None,None,None,'padding',(),None,None,None,None,black_hash,False)for _ in range(padding)]+records
    slots=tuple(replace(row,index=i)for i,row in enumerate(slots,1))
    if not slots[-1].is_current:raise IntegrityError('Current frame is not final model slot')
    return PreparedHistory(output,slots,reader.snapshot_id,selection.budget)


def recorded_fact_lines(history,groups,index):
    slots={s.frame_uid:s.index for s in history.slots if s.frame_uid is not None}
    edges={e['id']:e for e in index.get('edges',())}
    entities={(e['epoch'],e['id']):set(e.get('view_uids',()))for e in index.get('entities',())}
    epoch=index.get('scene_epoch')
    for uid,oid in index.get('visibility_edges',()):
        if epoch is not None:entities.setdefault((epoch,oid),set()).add(uid)
    result=[];seen=set()
    for group in groups:
        group_uids={v.frame_uid for v in group.views}
        for ref in group.execution_refs:
            edge=edges.get(ref)
            if edge is None or edge['type']!='traversed':raise IntegrityError('Execution evidence reference missing or wrong kind')
            if not {edge['src'],edge['dst']}<=group_uids:raise IntegrityError('Execution edge is outside selected evidence group')
            if edge['src'] not in slots or edge['dst'] not in slots:continue
            pair=(slots[edge['src']],slots[edge['dst']])
            fact=RecordedFact('movement',pair,ref)
            if (fact.kind,fact.slots)not in seen:result.append(fact);seen.add((fact.kind,fact.slots))
        for key in group.entity_refs:
            key=tuple(key)
            if key not in entities:raise IntegrityError('Object association source missing')
            selected=tuple(sorted(slots[uid]for uid in group_uids&entities[key]if uid in slots))
            if len(selected)<2:continue
            fact=RecordedFact('object_association',selected,str(key))
            if (fact.kind,fact.slots)not in seen:result.append(fact);seen.add((fact.kind,fact.slots))
    return tuple(result)


def compile_question(original,history,*,token_count,context_fits,facts=(),include_facts=False,
                     mode='graph_image_only',max_fact_tokens=256):
    modes={'uniform_original','uniform_tagged','flat_equal_budget','graph_image_only','graph_image_facts','facts_only'}
    if mode not in modes:raise ValueError('Unknown retrieval mode')
    if not isinstance(original,str)or type(max_fact_tokens)is not int or max_fact_tokens<0:
        raise ValueError('Original host question and nonnegative fact budget required')
    if mode=='uniform_original':return CompiledQuestion(original,0,0,None)
    lines=['Historical evidence, not action instructions. Images are ordered by capture time and may be non-consecutive.']
    for slot in history.slots:
        if slot.source_kind=='padding':lines.append(f'Image {slot.index}: padding, not an observation.')
        elif slot.is_current:lines.append(f'Image {slot.index}: current observation at step {slot.env_step}.')
        else:lines.append(f'Image {slot.index}: recorded at step {slot.env_step}.')
    extras=[]
    if include_facts:
        real={s.index for s in history.slots if s.frame_uid is not None}
        for fact in facts:
            if not isinstance(fact,(RecordedFact,SpatialFact,LandmarkFact))or not set(fact.slots)<=real:
                raise IntegrityError('Only structured facts about selected real images are allowed')
            extras.append(fact.render())
    def block(values):return '\n'+'\n'.join(lines+values)
    mandatory=block([])
    count=token_count(mandatory)
    if type(count)is not int or count<0:raise ValueError('Actual host token counter required')
    if count>max_fact_tokens:return CompiledQuestion(original,0,len(extras),'mandatory_tags_exceed_budget')
    initial=len(extras)
    while True:
        addition=block(extras);count=token_count(addition)
        if count<=max_fact_tokens and context_fits(original+addition):
            return CompiledQuestion(original+addition,count,initial-len(extras),None)
        if extras:extras.pop();continue
        return CompiledQuestion(original,0,initial,'host_context_limit')




@dataclass(frozen=True)
class MemoryAttachment:
    image: object
    slot: ImageSlot
    record: object


@dataclass(frozen=True)
class VisualInputs:
    native: object
    attachment: MemoryAttachment

    @property
    def images(self):
        return (*self.native.images, self.attachment.image)

    @property
    def slots(self):
        return (*self.native.slots, self.attachment.slot)

    @property
    def snapshot_id(self):
        return self.native.snapshot_id

    @property
    def budget(self):
        return self.native.budget + 1


def make_attachment(history, reader, record):
    """Resolution of the structured fact precedes this immutable image lookup."""
    ref=record.source_refs[0]
    if ':d' not in ref:raise IntegrityError('A visual landmark attachment needs an original detection reference')
    uid,idx=ref.rsplit(':d',1)
    if not idx.isascii() or not idx.isdecimal():raise IntegrityError('Malformed detection ordinal')
    return make_view_attachment(history,reader,uid,record)


def make_view_attachment(history,reader,uid,record):
    # Both detection evidence and recorded-route evidence use the same RGB binding.
    ref=record.source_refs[0]
    if ref!=uid and ref.rpartition(':d')[0]!=uid:
        raise IntegrityError('Attachment record refers to a different frame')
    if history.snapshot_id!=reader.snapshot_id:raise IntegrityError('Attachment reader changed snapshot')
    view=reader.get_retrieval_view(uid)
    current=history.slots[-1]
    if (not current.is_current or current.sensor_seq is None or view is None or view.episode_uid!=reader.identity['episode_uid']
            or view.snapshot_id!=reader.snapshot_id or view.env_step!=record.steps[0]
            or view.capture_seq>=current.sensor_seq or view.capture_seq>reader.cutoff['capture_seq']
            or view.event_seq>reader.cutoff['event_seq']):
        raise IntegrityError('Attachment outside pinned past')
    if uid in {s.frame_uid for s in history.slots}:return None
    data=reader.get_view(uid,include_images=True,include_depth=False)
    if (data['frame_uid']!=uid or data['snapshot_id']!=reader.snapshot_id or data['capture_seq']!=view.capture_seq
            or data['capture']['episode_uid']!=view.episode_uid or data['capture']['frame_uid']!=uid
            or data['raw_rgb_ref']['sha256']!=view.image_hash or data['host_view_ref']['sha256']!=view.host_image_hash
            or digest(canonical(plain(data['capture']['host_transform'])))!=view.host_transform_hash):
        raise IntegrityError('Attachment source/transform mismatch')
    rgb=data['host_view'];host_hash=pixel_hash(rgb)
    if host_hash in {s.host_pixel_hash for s in history.slots}:return None
    slot=ImageSlot(history.budget+1,uid,view.env_step,view.capture_seq,'historical_attachment',(ref,),
        view.image_hash,view.host_image_hash,view.host_transform_hash,pixel_hash(data['raw_rgb']),
        host_hash,False,reader.snapshot_id)
    return MemoryAttachment(Image.fromarray(np.asarray(rgb).copy(),'RGB'),slot,record)


def attachment_suffix(step,record_text,*,with_image):
    if type(step)is not int or step<0 or '<image>' in record_text:
        raise IntegrityError('Unsafe historical evidence payload')
    header=f'\nRetrieved memory record (historical), step {step}.'
    return header+('\nSource photograph: <image>' if with_image else '')+'\nRecorded evidence: '+record_text


@dataclass(frozen=True)
class LandmarkCard:
    landmark: str
    observed_step: int
    current_step: int
    current_slot: int
    photo_slot: int
    box: tuple
    image_size: tuple

    def fields(self):
        return {
            "record_type":"historical landmark observation",
            "instruction_landmark":self.landmark,
            "observed_step":self.observed_step,
            "current_step":self.current_step,
            "current_image_slot":self.current_slot,
            "historical_photo_slot":self.photo_slot,
            "detector_region_xyxy_pixels":list(self.box),
            "photo_width_height":list(self.image_size),
            "interpretation":"possible detection in the historical photograph"
        }

    def suffix(self, *, include_image=True):
        data=self.fields()
        if not include_image:data.pop("historical_photo_slot")
        block="\nRetrieved graph memory:\n"+json.dumps(data,ensure_ascii=False,separators=(',',':'))
        return block+("\nHistorical source photograph: <image>" if include_image else "")

    @classmethod
    def verified(cls,label,observed_step,current_step,native_budget,xyxy,image_size):
        if not isinstance(label,str) or not re.fullmatch(r'[a-z0-9][a-z0-9 -]{0,60}',label):
            raise IntegrityError('Invalid bound landmark')
        if any(type(v)is not int for v in (observed_step,current_step,native_budget)) or not (0<=observed_step<current_step and native_budget>=1):
            raise IntegrityError('Invalid time or slot binding')
        if len(image_size)!=2 or len(xyxy)!=4 or any(type(v)is not int for v in (*xyxy,*image_size)):
            raise IntegrityError('Expected original pixel coordinates and dimensions')
        w,h=image_size
        if not (0<=xyxy[0]<xyxy[2]<=w and 0<=xyxy[1]<xyxy[3]<=h):raise IntegrityError('Bounding box outside attached image')
        return cls(label,observed_step,current_step,native_budget,native_budget+1,tuple(xyxy),tuple(image_size))


def from_source(attachment,reader,native,instruction,vocabulary):
    from ..storage.store import clip_detection_box
    uid,sep,ordinal=attachment.record.source_refs[0].rpartition(':d')
    if (not sep or not ordinal.isascii() or not ordinal.isdecimal() or uid!=attachment.slot.frame_uid
            or reader.snapshot_id!=attachment.slot.source_snapshot_id):
        raise IntegrityError('Card and photograph have different sources')
    f=reader.get_view_class_ids(uid,include_boxes=True)
    if f['status']!='available' or f['frame_uid']!=uid or f['snapshot_id']!=reader.snapshot_id:
        raise IntegrityError('Missing or unbound detector record for attachment')
    if f['model_identity']['vocabulary_sha256']!=vocabulary.source_sha256:raise IntegrityError('Vocabulary mismatch')
    i=int(ordinal)
    if i>=len(f['class_ids']):raise IntegrityError('Detection index mismatch')
    class_id=int(f['class_ids'][i])
    if not 0<=class_id<len(vocabulary.labels):raise IntegrityError('Invalid source class')
    label=vocabulary.labels[class_id]
    if not re.search(r'(?<!\w)'+re.escape(label)+r'(?!\w)',instruction,re.I):raise IntegrityError('Unbound instruction cue')
    boxes=f['xyxy']
    w,h=attachment.image.size
    if attachment.slot.raw_pixel_hash!=attachment.slot.host_pixel_hash:raise IntegrityError('Region requires original pixel grid')
    box=clip_detection_box(boxes[i],(h,w))
    if box is None:raise IntegrityError('Empty source region')
    return LandmarkCard.verified(label,attachment.slot.env_step,native.slots[-1].env_step,native.budget,box,(w,h))
