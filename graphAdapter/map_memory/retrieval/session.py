"""One episode's private-worker retrieval over existing immutable map snapshots."""
from contextlib import ExitStack
from dataclasses import asdict,replace
from collections.abc import Mapping
import threading
from graphAdapter.map_memory.retrieval.protocol import FrozenMemoryRead,native_slot_indices
from .contracts import MemoryQuery
from .candidates import get_candidates,CameraTextScores
from .bundles import build_bundles,selected_relations
from .selector import select_history, select_grounded_single_slot, select_linked_view
from ..storage.features import EpisodeFeatureCache
from ..storage.store import load_episode,IntegrityError


def plain(value):
    if isinstance(value,Mapping):return {k:plain(v)for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [plain(v)for v in value]
    return value


class MemoryRetrievalSession:
    """No observation, geometry, detector, pose or navigation updates occur here."""
    def __init__(self,root,episode_uid,episode_instance,encoder,vocabulary,*,feature_cache_bytes=64*1024*1024,evidence_policy='ranked',landmark_query=None,context_bundle=False):
        self.root=root;self.episode_uid=episode_uid;self.episode_instance=episode_instance
        if evidence_policy not in ('ranked', 'instruction_grounded', 'grounded_single_slot','linked_history_single_slot','linked_view_gain','additive_text','context_text','landmark_attachment','evo_event_attachment','dynamic_evo_context','historical_approach','evo_topology'):
            raise ValueError('Unknown evidence policy')
        self.evidence_policy=evidence_policy
        self.landmark_query=landmark_query
        self.context_bundle=context_bundle
        self.encoder=encoder;self.vocabulary=vocabulary
        from ..storage.pages import HistoryPageCache
        from ..storage.store import DEFAULT_SNAPSHOT_CACHE_BYTES
        self.page_cache=HistoryPageCache(root,DEFAULT_SNAPSHOT_CACHE_BYTES//2,episode=episode_uid) if evidence_policy=='evo_topology' else None
        self.feature_cache=EpisodeFeatureCache(root,max_bytes=feature_cache_bytes)
        # Bound scalar entries separately from decoded arrays; honor zero-cache operation.
        entries=min(512,feature_cache_bytes//512)
        self.instruction_scores=CameraTextScores(entries)
        self.reasoning_scores=CameraTextScores(entries)
        self.owner=threading.get_ident();self.closed=False

    def get_selected_views(self, reader, query, current, budget):
        """Resolve host sample ordinals in the pinned graph, without renumbering missing frames."""
        indices=native_slot_indices(current.capture_seq,budget)
        required={i+1 for i in indices if i is not None and i+1!=current.capture_seq}
        by_seq={}
        for uid,view in reader._graph['views'].items():
            seq=view['capture_seq']
            if seq in required:
                if seq in by_seq:raise IntegrityError('Duplicate sampled capture sequence')
                by_seq[seq]=uid
        if required-set(by_seq):return None
        selected=[]
        for i in indices:
            if i is None:continue
            if i+1==current.capture_seq:
                selected.append(current)
                continue
            v=reader.get_retrieval_view(by_seq[i+1])
            if v is None:return None
            if (v.capture_seq!=i+1 or v.frame_uid!=by_seq[i+1] or v.episode_uid!=query.episode_uid
                    or v.snapshot_id!=query.snapshot_id or v.source_snapshot_id!=query.snapshot_id
                    or v.capture_seq>query.cutoff_capture_seq or v.event_seq>query.cutoff_event_seq):
                raise IntegrityError('Sampled history differs from pinned endpoint')
            selected.append(v)
        return selected

    def read(self,request,*,current_snapshot_id):
        if self.closed:raise RuntimeError('Retrieval session has been released')
        if threading.get_ident()!=self.owner:raise RuntimeError('Only the private worker owner may read this session')
        frozen=FrozenMemoryRead.create(request);request=frozen.request
        raw=dict(request['query'])
        decision_id=raw.pop('decision_id',None)
        query=MemoryQuery(**raw)
        if (query.episode_uid,request['episode_instance'])!=(self.episode_uid,self.episode_instance):
            raise IntegrityError('Query belongs to another episode/session')
        with ExitStack()as resources:
            reader=load_episode(self.root,revision=query.snapshot_id,feature_cache=self.feature_cache,_history_cache=self.page_cache)
            resources.callback(reader.close)
            if reader.identity['episode_uid']!=self.episode_uid or dict(reader.cutoff)!={'capture_seq':query.cutoff_capture_seq,'event_seq':query.cutoff_event_seq}:
                raise IntegrityError('Query snapshot/cutoff binding differs')
            current_reader=reader
            if current_snapshot_id!=query.snapshot_id:
                current_reader=load_episode(self.root,revision=current_snapshot_id,feature_cache=self.feature_cache,_history_cache=self.page_cache)
                resources.callback(current_reader.close)
            if current_reader.identity['episode_uid']!=self.episode_uid or current_reader.cutoff['capture_seq']!=query.current_capture_seq:
                raise IntegrityError('Current cue must come from the exact current host frame frontier')
            source_current=current_reader.get_retrieval_view(query.current_frame_uid)
            if source_current is None or source_current.capture_seq!=query.current_capture_seq:
                raise IntegrityError('Current host image source unavailable')
            # The transaction is pinned to old history, while current RGB is a
            # normal live observation. Preserve its separate actual source SID.
            current=replace(source_current,snapshot_id=query.snapshot_id,source_snapshot_id=current_reader.snapshot_id)
            query=replace(query,current_position=source_current.position,pose_map_version=source_current.pose_map_version)
            result=dict(request_id=request['request_id'],episode_uid=query.episode_uid,episode_instance=self.episode_instance,
                snapshot_id=query.snapshot_id,current_source_snapshot_id=current_reader.snapshot_id,
                episode_root=str(self.root),mode=request['mode'],read_only=True,
                cutoff=dict(reader.cutoff),versions=dict(reader.versions),current_frame_uid=current.frame_uid,current_capture_seq=current.capture_seq)
            if decision_id is not None:
                result.update(decision_id=decision_id,decision_event_seq=query.decision_event_seq)
            if self.evidence_policy == 'historical_approach':
                from .semantic_topology import requested_exit_room,historical_approach
                room=requested_exit_room(query.instruction,query.last_reasoning)
                approach=historical_approach(reader,current.capture_seq,room) if room else None
                if approach is None:
                    result.update(evidence_policy=self.evidence_policy,unavailable_reason='no_connected_approach')
                    return frozen.validate_reply(result)
            compact=request['protocol_version']>=2
            if compact:
                selected=self.get_selected_views(reader,query,current,request['budget'])
                if selected is None:
                    result.update(unavailable_reason='native_sample_unavailable')
                    return frozen.validate_reply(result)
                result['native_views']=[asdict(v) for v in selected]
            else:
                views=[]
                for uid in reader.get_retrieval_index()['view_uids']:
                    v=reader.get_retrieval_view(uid)
                    if v is not None and v.capture_seq<query.current_capture_seq:
                        if v.capture_seq>query.cutoff_capture_seq or v.event_seq>query.cutoff_event_seq:
                            raise IntegrityError('Future uniform history in pinned snapshot')
                        views.append(v)
                views.sort(key=lambda v:(v.capture_seq,v.frame_uid));views.append(current)
                result['uniform_views']=[asdict(v) for v in views]
            if request['mode']in ('uniform_original','uniform_tagged'):
                result.update(selection=None,candidate_views=[],channels={},relations={})
                return frozen.validate_reply(result)
            if self.evidence_policy == 'historical_approach':
                result.update(selection=None,channels={},evidence_policy=self.evidence_policy,approach=approach)
                return frozen.validate_reply(result)
            if self.evidence_policy=='evo_topology':
                from .evo_material import read_evo_material
                material=read_evo_material(reader,query,self.vocabulary)
                if self.context_bundle:
                    from .evo_context import read_context_bundle
                    result['evo_context']=read_context_bundle(self,reader,query,current,current_reader,request['budget'])
                result.update(selection=None,candidate_views=[],channels={'EvoAnchor':[a['uid'] for a in material['anchors']]},
                              candidates=[],relations={},evidence_policy=self.evidence_policy,evo_material=material)
                return frozen.validate_reply(result)
            index=reader.get_retrieval_index()
            if self.evidence_policy in ('evo_event_attachment','dynamic_evo_context'):
                from .candidates import propose_anchor,label_from_upstream
                from .evidence import landmark_query_cues
                from types import SimpleNamespace
                cues=None
                if self.landmark_query=='current_plan':
                    cues=landmark_query_cues(query.instruction,query.last_reasoning,self.vocabulary.labels)
                    result['landmark_query_cues']=list(cues)
                    result['landmark_reasoning_event']=query.last_reasoning_event_seq
                if compact:
                    native={v.frame_uid for v in selected}
                    anchors=[]
                    for uid in (index['anchors'] if cues is None or cues else ()):
                        seq=reader._graph['views'][uid]['capture_seq']
                        if uid in native or seq>=current.capture_seq:continue
                        v=reader.get_retrieval_view(uid)
                        if v is None:continue
                        if v.event_seq>query.cutoff_event_seq or seq>query.cutoff_capture_seq:
                            raise IntegrityError('Anchor outside pinned evidence')
                        anchors.append(v)
                else:
                    anchors,native=views[:-1],None
                proposals=propose_anchor(anchors,current,index,reader,self.vocabulary,query.instruction,
                                         request['budget'],native_uids=native,query_cues=cues)
                shortlisted=[item['uid']for item in proposals]
                if self.landmark_query=='current_plan':
                    from .semantic_topology import visible_detection_owners
                    result['ranked_landmarks']=[
                        dict(proposal,object_id=visible_detection_owners(reader,proposal['uid'])[proposal['index']])
                        for proposal in proposals]

                if proposals:
                    from .semantic_topology import visible_detection_owners
                    uid=proposals[0]['uid']
                    ordinal=proposals[0]['index']
                    result['anchor_object']=dict(epoch=index['scene_epoch'],
                        object_id=visible_detection_owners(reader,uid)[ordinal],member=f'{uid}:d{ordinal:05d}')
                    if self.evidence_policy=='evo_event_attachment' or not compact:
                        room=index['anchors'][uid].get('room_type_hint') or 'unknown'
                        row=reader.get_view(uid,include_images=True,include_depth=False)
                        result['anchor_prompt_label']=label_from_upstream(query.instruction,SimpleNamespace(image=row['host_view']),room)
                if self.context_bundle:
                    from .evo_context import read_context_bundle
                    result['evo_context']=read_context_bundle(self,reader,query,current,current_reader,request['budget'])
                result.update(selection=None,candidate_views=[],channels={'EvoAnchor':shortlisted},candidates=[],relations={},
                    evidence_policy=self.evidence_policy,additional_evidence=proposals[:1])
                return frozen.validate_reply(result)
            encoded=self.encoder.encode(query)
            current_features=current_reader.get_view_features(query.current_frame_uid)
            candidates=get_candidates(reader,query,encoded,self.vocabulary,current_features=current_features,
                                      instruction_scores=self.instruction_scores,reasoning_scores=self.reasoning_scores)
            result['semantic_score_cache']=dict(instruction_hits=self.instruction_scores.hits,instruction_misses=self.instruction_scores.misses,
                                                reasoning_hits=self.reasoning_scores.hits,reasoning_misses=self.reasoning_scores.misses)
            if self.evidence_policy in ('additive_text','context_text','landmark_attachment','evo_event_attachment'):
                from .evidence import propose
                from .evidence import propose_context
                build=propose_context if self.evidence_policy=='context_text' else propose
                proposals=build(candidates,current,reader,self.vocabulary,query.instruction,request['budget'])
                if self.evidence_policy=='landmark_attachment':
                    proposals=[item for item in proposals if item['kind']=='landmark']
                result.update(selection=None,candidate_views=[],channels=plain(candidates.channels),
                    candidates=[asdict(v) for v in candidates.ranked],relations={},evidence_policy=self.evidence_policy,
                    additional_evidence=proposals)
                return frozen.validate_reply(result)
            # Keep Q/V/C recall intact. Admission controls the use of global slots.
            # This experimental policy is deliberately conservative for relational
            # or material-only instructions that object detection cannot substantiate.
            grounded = self.evidence_policy in ('instruction_grounded','grounded_single_slot')
            eligible = candidates
            if grounded:
                eligible = replace(candidates, ranked=tuple(c for c in candidates.ranked if c.matched_categories))
            result['evidence_policy'] = self.evidence_policy
            result['grounded_seed_uids'] = [c.view.frame_uid for c in candidates.ranked if c.matched_categories]
            if self.evidence_policy in ('linked_history_single_slot','linked_view_gain'):
                def camera_feature(uid):
                    features=current_features if uid==current.frame_uid else reader.get_view_features(uid)
                    return features.get('full_clip')
                selection=select_linked_view(candidates,current,index,budget=request['budget'],
                    full_image_feature=camera_feature if self.evidence_policy=='linked_view_gain' else None)
            elif self.evidence_policy=='grounded_single_slot':
                selection=select_grounded_single_slot(eligible,current,budget=request['budget'])
            else:
                bundles=build_bundles(eligible,index,pose_map_version=reader.versions['pose_map_version'],
                                      expand=request['mode']!='flat_equal_budget')
                selection=select_history(eligible,bundles,current,budget=request['budget'])
            if grounded and not eligible.ranked:
                selection=replace(selection,fallback_reason='no_instruction_grounded_seed')
            source_labels=[]
            if grounded:
                for group in selection.groups:
                    row=reader.get_view_features(group.seed_ref)
                    if row['status']!='available':continue
                    for detection_index,class_id in enumerate(row['class_ids']):
                        label=self.vocabulary.labels[int(class_id)]
                        if label in candidates.category_cues:
                            source_labels.append(dict(frame_uid=group.seed_ref,detection_index=detection_index,
                                label=label,class_id=int(class_id),vocabulary_sha256=self.vocabulary.source_sha256,
                                raw_signature=row['raw_signature'],source_ref=row['source_ref']['sha256']))
            result['instruction_detections']=source_labels
            relations=selected_relations(selection,index)
            result.update(selection=asdict(selection),**({} if compact else {'candidate_views':[asdict(v)for v in candidates.views]}),
                candidates=[asdict(v)for v in candidates.ranked],channels=plain(candidates.channels),relations=relations,
                query_encoder=dict(model_identity_hash=encoded.model_identity_hash,tokenizer_identity_hash=encoded.tokenizer_identity_hash,
                    model_batches=self.encoder.model_batches,cache_hits=self.encoder.cache_hits,cache_bytes=self.encoder.cache_bytes),
                feature_cache=dict(bytes=self.feature_cache.bytes,decodes=self.feature_cache.decodes,hits=self.feature_cache.hits))
            return frozen.validate_reply(result)

    def close(self):
        self.instruction_scores.clear();self.reasoning_scores.clear()
        if self.page_cache is not None:self.page_cache.close()
        self.feature_cache.close();self.closed=True
        # Encoder/model belong to the worker, not this episode's reader.


class WorkerRetrieval:
    """One private worker owns the text encoder; one episode owns each snapshot reader."""
    def __init__(self, project_root):
        self.project_root = project_root
        self.encoder = None
        self.session = None
        self.vocabulary = None

    def read(self, request, *, options, service, store, models, model_identity, prepared):
        from .protocol import FrozenMemoryRead
        incoming = FrozenMemoryRead.create(request).request
        if options is None or incoming['mode'] != options['mode']:
            raise ValueError('Retrieval mode is not enabled for this worker')
        if service is None or store is None or models is None or prepared is not None or service.prepared is not None:
            raise ValueError('Retrieval requires a committed live episode without a pending transaction')
        query = incoming['query']
        packet = service.frames.get(query['current_frame_uid'])
        if packet is None or packet['episode_uid']!=query['episode_uid'] or packet['capture_seq']!=query['current_capture_seq']:
            raise ValueError('Read current frame is not a committed source observation')
        if packet['pose_provider']!='simulator_ground_truth':
            raise ValueError('Current retrieval deployment uses SimulatorAdapter pose only')
        instance=packet['pose_record'].get('episode_instance')
        if not instance or instance!=incoming['episode_instance']:
            raise ValueError('Read pose/source session differs')
        if self.encoder is None:
            from .query_adapter import QueryEncoder
            from .contracts import CategoryVocabulary
            self.vocabulary=CategoryVocabulary.from_file(self.project_root/'vendor_sources/EvoMemNav/data/scannet200_classes.txt')
            self.encoder=QueryEncoder(models,model_identity,self.vocabulary,overlap=options['overlap'],
                                      batch_windows=options['batch_windows'],max_bytes=options['query_cache_bytes'])
        if self.session is None:
            self.session=MemoryRetrievalSession(store.root,store.episode_uid,instance,self.encoder,self.vocabulary,
                feature_cache_bytes=options['feature_cache_bytes'],evidence_policy=options['evidence_policy'],
                landmark_query=options.get('landmark_query'),context_bundle=options.get('context_bundle',False))
        from ..storage.archive import UnavailableMaterial
        try:return self.session.read(incoming,current_snapshot_id=service.pointer['snapshot_id'])
        except UnavailableMaterial as error:
            # Only ordinary payload unavailability crosses as a negative read. No partial selection.
            clock={key:query[key] for key in ('decision_id','decision_event_seq')} if incoming['protocol_version']==3 else {}
            return dict(**clock,request_id=incoming['request_id'],episode_uid=query['episode_uid'],episode_instance=instance,
                        snapshot_id=query['snapshot_id'],mode=incoming['mode'],episode_root=str(store.root),read_only=True,
                        current_frame_uid=query['current_frame_uid'],current_capture_seq=query['current_capture_seq'],
                        cutoff=dict(capture_seq=query['cutoff_capture_seq'],event_seq=query['cutoff_event_seq']),
                        unavailable_reason=error.reason)

    def end_episode(self):
        if self.session is not None:
            self.session.close()
            self.session=None

    def close(self):
        self.end_episode()
        if self.encoder is not None:
            self.encoder.close()
            self.encoder=None

