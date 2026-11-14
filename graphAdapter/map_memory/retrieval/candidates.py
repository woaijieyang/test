"""Retrieve instruction-ranked views or directly shortlist EvoMemNav anchors."""
import hashlib,json,re
from collections import OrderedDict
from collections.abc import Mapping
from types import MappingProxyType
import numpy as np
from evomemnav.policy.coarse import AnchorCandidate,rank_anchors
from .contracts import Candidate,CandidateResult,ViewRef,CategoryVocabulary
from ..storage.archive import IntegrityError,canonical,digest
import re
from evomemnav.policy.coarse import AnchorCandidate,select_candidates
from evomemnav.vlm.prompts import AnchorPromptItem,build_selection_query
from ..storage.archive import IntegrityError
from graphAdapter.map_memory.retrieval.protocol import native_slot_indices


from .evidence import match_category_cues


def _unit(values):
    a=np.asarray(values,dtype=np.float64)
    if not np.isfinite(a).all():raise IntegrityError('Nonfinite query/camera feature')
    norms=np.linalg.norm(a,axis=-1,keepdims=True)
    if np.any(norms==0):raise IntegrityError('Zero feature is not similarity evidence')
    return a/norms


def _max_similarity(query,features):
    pieces=[]
    if features.get('full_clip') is not None:pieces.append(np.asarray(features['full_clip'])[None,:])
    objects=features.get('object_clip')
    if objects is not None and np.asarray(objects).size:pieces.append(np.asarray(objects))
    if not pieces:return None
    if any(a.ndim!=2 or a.shape[1]!=query.shape[1]for a in pieces):
        raise IntegrityError('Query/camera feature dimensions differ')
    return max(float(np.max(query@_unit(a).T))for a in pieces)


class CameraTextScores:
    """Reuse text-to-camera dot products only; ranks, geometry and native slots are decision-local."""
    def __init__(self,max_entries=512):
        if type(max_entries)is not int or max_entries<0:raise ValueError('Invalid camera score entry limit')
        self.max_entries=max_entries
        self.rows=OrderedDict()
        self.embedding=None
        self.identity=None
        self.hits=self.misses=0

    def bind(self,embedding,identity):
        # The encoder yields the same immutable matrix on hits. Retaining the object also
        # prevents reuse of an allocator address after eviction or a changed encoding window.
        if self.embedding is not embedding or self.identity!=identity:
            self.rows.clear()
            self.embedding=embedding
            self.identity=identity

    def score(self,windows,features):
        # Only verified archive readers return source_ref. Legacy/unidentified material is recomputed.
        blob=features.get('source_ref')
        key=blob.get('sha256') if blob else None
        if key is not None and key in self.rows:
            self.hits+=1
            self.rows.move_to_end(key)
            return self.rows[key]
        self.misses+=1
        value=_max_similarity(windows,features)
        if key is not None and self.max_entries:
            if len(self.rows)>=self.max_entries:self.rows.popitem(last=False)
            self.rows[key]=value
        return value

    def clear(self):
        self.rows.clear()
        self.embedding=self.identity=None


def _time_order(views,limit):
    if not views:return []
    remaining=list(views);selected=[remaining.pop(0)]
    if remaining and limit>1:selected.append(remaining.pop())
    while remaining and len(selected)<limit:
        best=min(remaining,key=lambda v:(-min(abs(v.capture_seq-s.capture_seq)for s in selected),v.capture_seq,v.frame_uid))
        selected.append(best);remaining.remove(best)
    return selected


def _coverage_order(views,query,limit):
    temporal=_time_order(views,limit)
    spatial=sorted((v for v in views if v.position is not None and v.pose_map_version==query.pose_map_version),
                   key=lambda v:(v.capture_seq,v.frame_uid))
    if query.current_position is None or not spatial:return temporal
    positions=np.asarray([v.position for v in spatial],dtype=np.float64)
    def distances(point):
        delta=positions-point
        return np.sum(delta*delta,axis=1)
    current_dist=distances(np.asarray(query.current_position))
    # Stable ties follow capture sequence and frame UID, including coincident camera positions.
    nearby=[spatial[i] for i in np.argsort(current_dist,kind='stable')[:limit]]
    nearest=current_dist
    used=np.zeros(len(spatial),dtype=bool);spread=[]
    for _ in range(min(limit,len(spatial))):
        i=int(np.argmax(nearest));spread.append(spatial[i]);used[i]=True
        # After the first pick, the spread channel measures distance only to selected
        # historical views. The current camera is used solely to choose the first one.
        latest=distances(positions[i])
        nearest=latest if len(spread)==1 else np.minimum(nearest,latest)
        nearest[used]=-np.inf
    result=[];seen=set()
    for i in range(limit):
        for channel in (temporal,nearby,spread):
            if i<len(channel) and channel[i].frame_uid not in seen:
                result.append(channel[i]);seen.add(channel[i].frame_uid)
                if len(result)==limit:return result
    return result


def get_candidates(reader,query,encoded,vocabulary,*,aliases=None,room_hints=(),per_channel=8,current_features=None,instruction_scores=None,reasoning_scores=None,metadata_only=False):
    if type(per_channel)is not int or not 1<=per_channel<=8:
        raise ValueError('Stage002 per-channel candidate budget must be between1and8')
    if (reader.snapshot_id!=query.snapshot_id or reader.identity['episode_uid']!=query.episode_uid
            or reader.cutoff['capture_seq']!=query.cutoff_capture_seq or reader.cutoff['event_seq']!=query.cutoff_event_seq):
        raise IntegrityError('Query must bind the exact published snapshot and cutoff')
    index=reader.get_retrieval_index();model=index['model_identity']
    def plain(value):
        if isinstance(value,Mapping):return {k:plain(v)for k,v in value.items()}
        if isinstance(value,(tuple,list)):return [plain(v)for v in value]
        return value
    model_hash=digest(canonical(plain(model)))
    if encoded.instruction_hash!=query.instruction_hash or encoded.model_identity_hash!=model_hash:
        raise IntegrityError('Query features belong to another instruction or model')
    if not isinstance(vocabulary,CategoryVocabulary):raise TypeError('Source-bound CategoryVocabulary required')
    if model.get('vocabulary_sha256')!=vocabulary.source_sha256:raise IntegrityError('Frozen category vocabulary differs')
    vocabulary=vocabulary.labels
    if encoded.reasoning is not None:
        if query.last_reasoning is None or hashlib.sha256(query.last_reasoning.encode()).hexdigest()!=encoded.reasoning_hash:
            raise IntegrityError('Reasoning features lack causal source binding')
    cues=match_category_cues(query.instruction,vocabulary,aliases=aliases)
    if instruction_scores is not None:
        instruction_scores.bind(encoded.windows,(encoded.instruction_hash,model_hash,encoded.tokenizer_identity_hash))
    if reasoning_scores is not None:
        reasoning_scores.bind(encoded.reasoning,(encoded.reasoning_hash,model_hash,encoded.tokenizer_identity_hash))
    windows=_unit(encoded.windows);reasoning=_unit(encoded.reasoning)if encoded.reasoning is not None else None
    views=[];rejected=[];availability={}
    current=None
    for uid in sorted(index['view_uids']):
        # Q/V/C ranks pinned metadata and stored features; the host verifies each
        # actually selected photo separately when compiling visual attachments.
        row=reader.get_retrieval_view(uid,verify_images=False) if metadata_only else reader.get_retrieval_view(uid)
        if row is None:rejected.append((uid,'unavailable'));continue
        view=row if isinstance(row,ViewRef)else ViewRef(**row)
        if view.frame_uid!=uid or view.episode_uid!=query.episode_uid:
            raise IntegrityError('Cross-frame or cross-episode retrieval material')
        if view.snapshot_id!=query.snapshot_id:raise IntegrityError('Snapshot mismatch')
        if view.capture_seq>query.cutoff_capture_seq or view.event_seq>query.cutoff_event_seq or view.capture_seq>query.current_capture_seq:
            rejected.append((uid,'future'));continue
        if uid==query.current_frame_uid:
            if view.capture_seq!=query.current_capture_seq:raise IntegrityError('Current frame/ordinal mismatch')
            current=view;continue
        if view.capture_seq==query.current_capture_seq:raise IntegrityError('Two identities for current observation')
        views.append(view)
    views.sort(key=lambda v:(v.capture_seq,v.frame_uid))
    if len({v.capture_seq for v in views})!=len(views):raise IntegrityError('Duplicate capture ordinal')
    current_vector=None
    if current_features is not None:
        if current_features.get('frame_uid')!=query.current_frame_uid or current_features.get('capture_seq')!=query.current_capture_seq:
            raise IntegrityError('Current visual cue belongs to another host observation')
        f=current_features
    else:f=reader.get_view_features(current.frame_uid)if current is not None else None
    if f is not None and f['status']=='available':
        if f['model_identity_hash']!=model_hash:raise IntegrityError('Current feature model differs')
        if f.get('full_clip')is not None:current_vector=_unit(np.asarray(f['full_clip'])[None,:])
    semantic={};visual={};categories={};anchors=[]
    for view in views:
        uid=view.frame_uid;f=reader.get_view_features(uid)
        availability[uid]=(f.get('full_clip') is not None,len(f.get('class_ids',()))>0)
        labels=()
        if f['status']=='available':
            if f['model_identity_hash']!=model_hash:raise IntegrityError('Historical feature model differs')
            ids=f['class_ids']
            if any(int(i)<0 or int(i)>=len(vocabulary)for i in ids):raise IntegrityError('Class outside frozen vocabulary')
            labels=tuple(sorted({vocabulary[int(i)]for i in ids}))
            value=instruction_scores.score(windows,f) if instruction_scores is not None else _max_similarity(windows,f)
            if value is not None:
                supplement=None
                if reasoning is not None:
                    supplement=reasoning_scores.score(reasoning,f) if reasoning_scores is not None else _max_similarity(reasoning,f)
                semantic[uid]=value+(0.05*supplement if supplement is not None else 0.)
            if current_vector is not None and f.get('full_clip')is not None:
                if len(f['full_clip'])!=current_vector.shape[1]:raise IntegrityError('Current/history feature dimensions differ')
                visual[uid]=float((current_vector@_unit(np.asarray(f['full_clip'])[None,:]).T)[0,0])
        categories[uid]=tuple(c for c in cues if c in labels)
        # Zero recency leaves stable capture/frame input order as the final tie.
        anchors.append(AnchorCandidate(uid,view.room_hint or 'unknown',list(labels),0))
    coarse=rank_anchors(anchors,target='',room_hints=room_hints,category_hints=cues)
    coarse_rank={a.view_id:i for i,a in enumerate(coarse)}
    by_uid={v.frame_uid:v for v in views}
    q_order=sorted(semantic,key=lambda uid:(-semantic[uid],coarse_rank[uid],by_uid[uid].capture_seq,uid))
    v_order=sorted(visual,key=lambda uid:(-visual[uid],by_uid[uid].capture_seq,uid))
    channels={'Q':tuple(q_order[:per_channel]),'V':tuple(v_order[:per_channel]),
              'C':tuple(v.frame_uid for v in _coverage_order(views,query,per_channel)[:per_channel])}
    ranks={}
    for channel,order in channels.items():
        for rank,uid in enumerate(order,1):ranks.setdefault(uid,[]).append((channel,rank))
    weights={'Q':.5,'V':.25,'C':.25};ranked=[]
    for uid,positions in ranks.items():
        has_image,has_objects=availability[uid];available=['rgb','capture_time']
        if by_uid[uid].position is not None and by_uid[uid].pose_map_version==query.pose_map_version:available.append('estimated_geometry')
        if has_image:available.append('image_clip')
        if has_objects:available.extend(('object_clip','source_categories'))
        ranked.append(Candidate(by_uid[uid],sum(weights[c]/(60+n)for c,n in positions),tuple(positions),
            semantic.get(uid),visual.get(uid),categories[uid],tuple(available)))
    ranked.sort(key=lambda c:(-c.score,c.view.capture_seq,c.view.frame_uid))
    return CandidateResult(query.snapshot_id,tuple(views),tuple(ranked),MappingProxyType(channels),tuple(sorted(rejected)),cues)


def propose_anchor(views,current,index,reader,vocabulary,instruction,budget,*,native_uids=None,query_cues=None):
    cues=match_category_cues(instruction,vocabulary.labels) if query_cues is None else query_cues
    if not cues:return []
    from .semantic_topology import visible_detection_owners
    native=native_uids
    if native is None:
        timeline=sorted((*views,current),key=lambda v:v.capture_seq)
        native={timeline[i].frame_uid for i in native_slot_indices(len(timeline),budget) if i is not None}
    views={v.frame_uid:v for v in views}
    anchors=[];sources={}
    for uid,node in index['anchors'].items():
        if uid not in views or uid in native:continue
        owners=visible_detection_owners(reader,uid)
        if not owners:continue
        features=reader.get_view_class_ids(uid,include_confidence=True)
        if features.get('status')!='available':continue
        classes=features['class_ids']
        if any(i>=len(classes) for i in owners):
            raise IntegrityError('Graph member outside source detection array')
        labels={}
        for i in owners:
            class_id=int(classes[i])
            if not 0<=class_id<len(vocabulary.labels):raise IntegrityError('Invalid source class on anchor')
            labels[i]=vocabulary.labels[class_id]
        matches=[i for i,label in labels.items() if label in cues]
        if not matches:continue
        best=max(matches,key=lambda i:(float(features['confidence'][i]),-i))
        room=node.get('room_type_hint') or 'unknown'
        anchors.append(AnchorCandidate(uid,room,list(labels.values()),views[uid].capture_seq))
        sources[uid]=dict(kind='landmark',uid=uid,index=best,label=labels[best])
    rooms=sorted({a.room for a in anchors if re.search(r'\b'+re.escape(a.room)+r'\b',instruction,re.I)})
    ranked=select_candidates(anchors,[],target='',room_hints=rooms,category_hints=cues,
        k_a=5,k_f=0,w_gain=0.,w_distance=0.)
    return [sources[a.view_id]for a in ranked.anchors]


def label_from_upstream(instruction,attachment,room):
    import numpy as np
    pixels=np.asarray(attachment.image)
    item=AnchorPromptItem(image=pixels,room=room,evidence=())
    parts=build_selection_query(question=instruction,goal_image=None,egocentric_view=None,topo_summary=None,anchors=[item],frontiers=[])
    bound=[part for part in parts if isinstance(part,tuple) and part[1] is pixels]
    if len(bound)!=1:raise IntegrityError('Upstream prompt builder failed anchor-image binding')
    return bound[0][0]
