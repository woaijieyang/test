"""Bind one host decision to one published snapshot and original AwareVLN inputs."""
from contextlib import closing,contextmanager,nullcontext
from dataclasses import dataclass, field, replace
from pathlib import Path
import uuid
import time
from graphAdapter.map_memory.retrieval.protocol import native_slot_indices

from graphAdapter.map_memory.retrieval.protocol import retrieval_settings
from ..async_admission import ReadAdmissionFull, ReadDeadlineExpired
from ..storage.archive import UnavailableMaterial
from ..storage.store import load_episode, IntegrityError
from .contracts import ViewRef, Selection, EvidenceBundle
from .host_input_compiler import (
    materialize_history, recorded_fact_lines, grounded_fact_lines, compile_question, pixel_hash,
)
from .input_audit import observe_process_images, audit_final_inputs, verified_prompt_tokens


def _view(row):
    fields = dict(row)
    fields["entity_refs"] = tuple(tuple(ref) for ref in fields["entity_refs"])
    position = fields["position"]
    fields["position"] = tuple(position) if position is not None else None
    return ViewRef(**fields)


def _selection(row):
    groups = []
    for bundle in row["groups"]:
        fields = dict(bundle)
        fields["views"] = tuple(_view(v) for v in fields["views"])
        for name in ("execution_refs", "edge_types", "time_span", "missing_evidence"):
            fields[name] = tuple(fields[name])
        fields["entity_refs"] = tuple(tuple(ref) for ref in fields["entity_refs"])
        groups.append(EvidenceBundle(**fields))
    return Selection(tuple(_view(v) for v in row["slots"]), tuple(groups),
                     tuple(row["protected_recent"]), tuple(row["rejected"]),
                     row["fallback_reason"], row["budget"])


def verify_anchor_proposal(reader,reply):
    from .semantic_topology import visible_detection_owners
    proposals=reply['additional_evidence']
    if not proposals:
        if 'anchor_object' in reply:raise IntegrityError('Object receipt without a selected photograph')
        return None
    if len(proposals)!=1:raise IntegrityError('Ambiguous anchor evidence receipt')
    proposal=proposals[0]
    uid=proposal.get('uid');ordinal=proposal.get('index')
    if proposal.get('kind')!='landmark' or not isinstance(uid,str) or type(ordinal)is not int:
        raise IntegrityError('Invalid anchor detection reference')
    owners=visible_detection_owners(reader,uid)
    if ordinal not in owners:
        raise IntegrityError('Proposed detection lacks a visible object on the pinned anchor')
    expected=dict(epoch=reader._graph['scene_state']['epoch'],object_id=owners[ordinal],member=f'{uid}:d{ordinal:05d}')
    actual=reply.get('anchor_object')
    if not isinstance(actual,dict) or type(actual.get('object_id'))is not int or actual!=expected:
        raise IntegrityError('Worker and host disagree on the graph object behind the photograph')
    return expected


def checked_landmark_ranks(reader,reply,vocabulary,native_frames,current_seq):
    """Verify the bounded upstream shortlist on the host before recording the choice."""
    from .semantic_topology import visible_detection_owners
    rows=reply.get('ranked_landmarks')
    if not isinstance(rows,list) or len(rows)>5:
        raise IntegrityError('Missing or oversized landmark shortlist')
    sources=reply['channels']['EvoAnchor']
    if [row['uid'] for row in rows]!=sources or len(set(sources))!=len(sources):
        raise IntegrityError('Landmark shortlist disagrees with the ranked views')
    if [dict((k,row[k]) for k in ('kind','uid','index','label')) for row in rows[:1]]!=reply['additional_evidence']:
        raise IntegrityError('Selected landmark differs from the first ranked proposal')
    allowed=reply['landmark_query_cues']
    checked=[]
    for row in rows:
        uid=row['uid']
        ordinal=row['index']
        if (row['kind']!='landmark' or not isinstance(uid,str) or uid in native_frames
                or type(ordinal) is not int or ordinal<0 or type(row['object_id']) is not int
                or row['label'] not in allowed or visible_detection_owners(reader,uid).get(ordinal)!=row['object_id']):
            raise IntegrityError('Invalid ranked object binding')
        record=reader.get_view_class_ids(uid)
        if (record['status']!='available' or record['frame_uid']!=uid or record['snapshot_id']!=reader.snapshot_id
                or not 0<record['capture_seq']<=reader.cutoff['capture_seq'] or record['capture_seq']>=current_seq
                or record['model_identity']['vocabulary_sha256']!=vocabulary.source_sha256 or ordinal>=len(record['class_ids'])):
            raise IntegrityError('Landmark shortlist crossed its source scope')
        label_id=int(record['class_ids'][ordinal])
        if not 0<=label_id<len(vocabulary.labels) or vocabulary.labels[label_id]!=row['label']:
            raise IntegrityError('Ranked landmark label differs from its source')
        checked.append(dict(frame_uid=uid,step=record['capture_seq']-1,label=row['label'],
                            object_id=row['object_id'],member=f'{uid}:d{ordinal:05d}'))
    return checked


def verified_relation_facts(reader,history,selection,worker_relations):
    from .bundles import selected_relations
    if reader.snapshot_id!=history.snapshot_id:
        raise IntegrityError('Relation facts differ from the materialized snapshot')
    expected=selected_relations(selection,reader.get_retrieval_index())
    if expected!=worker_relations:
        raise IntegrityError('Worker relation payload differs from pinned graph')
    return recorded_fact_lines(history,selection.groups,expected)


class ReadUnavailable(Exception):
    """An expected availability failure for the original uniform fallback."""


@dataclass
class HostDecision:
    hook: object
    event: dict
    mode: str
    settings: dict
    history: object = None
    evo_evidence: object = None
    evo_cutoff_step: int | None = None
    facts: tuple = ()
    fallback: str | None = None
    request_id: str | None = None
    used_context: tuple = ()
    used_frame_records: tuple = ()
    attachment: object = None
    evidence_card: object = None
    anchor_object: dict | None = None
    object_position: object = None
    photo_support: object = None
    approach: object = None
    approach_scope: tuple | None = None
    started_monotonic: float = field(default_factory=time.monotonic)
    landmark_delivery: object = None
    landmark_delivery_key: tuple | None = None
    window: object = None
    combined: object = None

    @property
    def model_visuals(self):
        return self.combined or self.history

    def emit(self, event_kind, **fields):
        return self.hook.coordinator.emit(event_kind,
            frame_uid=self.event["frame_uid"], decision_id=self.event["decision_id"],
            env_step=self.event["env_step"], request_id=self.request_id, mode=self.mode, **fields)

    def use_uniform(self, reason):
        self.history = None
        self.facts = ()
        self.attachment = self.combined = None
        self.fallback = reason
        self.emit("MemoryReadFallback", reason=reason, elapsed_seconds=time.monotonic()-self.started_monotonic)

    def compile(self, question, prompt_fn, tokenizer, tokenize_prompt, model):
        if self.history is None:
            return question
        per_image, limit = vision_budget(model)
        def fits(text):
            ids = tokenize_prompt(prompt_fn(text))
            return len(ids.reshape(-1)) + self.history.budget * (per_image - 1) + 256 <= limit
        if self.settings['evidence_policy']=='evo_topology':
            from .evo_host import compile_evo
            try:return compile_evo(self,question,prompt_fn,tokenize_prompt,per_image,limit)
            except UnavailableMaterial as error:
                self.use_uniform(error.reason)
                return question
        if self.settings['evidence_policy']=='historical_approach':
            import json
            a=self.approach
            fields=dict(earlier_view_step=a['before_step'],later_view_step=a['inside_step'],
                        later_room_visual_hint=a['room_hint'],recorded_forward_movements=len(a['traversed_edges']))
            if a['unverified_forward_steps']:
                fields['forward_steps_without_traversal_evidence']=a['unverified_forward_steps']
            for role, uid in [('earlier',a['before']),('later',a['inside'])]:
                slot=next((i for i,v in enumerate(self.history.slots,1) if v.frame_uid==uid),None)
                if slot is not None:fields[role+'_image_slot']=slot
            suffix='\nHistorical approach observations:\n'+json.dumps(fields,separators=(',',':'))
            if len(tokenizer.encode(suffix,add_special_tokens=False))>self.settings['max_fact_tokens'] or not fits(question+suffix):
                self.use_uniform('approach_exceeds_budget')
                return question
            photo=self.attachment
            if photo is not None:
                from .host_input_compiler import VisualInputs
                extra='\nEarlier source view at step '+str(a['before_step'])+': <image>'
                ids=tokenize_prompt(prompt_fn(question+suffix+extra)).reshape(-1)
                if (len(ids)+(self.history.budget+1)*(per_image-1)+256<=limit and
                        len(tokenizer.encode(suffix+extra,add_special_tokens=False))<=self.settings['max_fact_tokens']):
                    self.combined=VisualInputs(self.history,photo)
                    suffix+=extra
            self.emit('ApproachCompiled',fields=fields,source=a,snapshot_id=self.history.snapshot_id,
                      attachment_frame=photo.slot.frame_uid if self.combined else None,photo_support=self.photo_support,
                      reasoning_event=self.approach_scope[-1],model_suffix=suffix)
            return question+suffix
        if self.settings['evidence_policy']=='dynamic_evo_context':
            import json
            from .host_input_compiler import VisualInputs
            if self.window is None:raise IntegrityError('Missing decision-scoped graph window')
            fields=dict(self.window.fields)
            a=self.attachment
            if a is not None:
                fields['historical_landmark']=self.evidence_card.fields()
                if self.object_position is not None:
                    fields['historical_landmark']['object_center_estimate_current_camera']=self.object_position[0]
            def render(f,photo):
                suffix='\nGraph memory for this decision:\n'+json.dumps(f,separators=(',',':'),allow_nan=False)
                if photo:suffix+='\nHistorical source photograph: <image>'
                return suffix
            def fits_window(suffix,n):
                ids=tokenize_prompt(prompt_fn(question+suffix)).reshape(-1)
                tokens=len(tokenizer.encode(suffix,add_special_tokens=False))
                return tokens<=self.settings['max_fact_tokens'] and len(ids)+n*(per_image-1)+256<=limit
            suffix=render(fields,a is not None)
            if self.object_position is not None and not fits_window(suffix,self.history.budget+1):
                fields['historical_landmark'].pop('object_center_estimate_current_camera',None)
                suffix=render(fields,True)
            if a is not None and not fits_window(suffix,self.history.budget+1):
                fields.pop('historical_landmark')
                fields.pop('distance_to_historical_camera_m_estimate',None)
                a=None
                suffix=render(fields,False)
            if self.settings.get('context_admission')=='native_plan_photo' and a is None:
                self.use_uniform('plan_photo_exceeds_budget')
                return question
            if (self.settings.get('context_admission')=='landmark_or_collision' and a is None
                    and not fields.get('recent_path',{}).get('recorded_collisions',0)):
                self.use_uniform('routine_path_without_landmark_or_collision')
                return question
            if len(fields)==1 or not fits_window(suffix,self.history.budget+int(a is not None)):
                self.use_uniform('no_dynamic_record_within_budget')
                return question
            self.combined=VisualInputs(self.history,a) if a is not None else None
            source=dict(self.window.provenance)
            if 'object_center_estimate_current_camera' in fields.get('historical_landmark',{}):
                source['object_position']=self.object_position[1]
            if a is None:source.pop('anchor',None)
            elif self.anchor_object is not None:source['anchor_object']=self.anchor_object
            self.emit('DynamicContextCompiled',snapshot_id=self.history.snapshot_id,model_fields=fields,
                source=source,attachment_frame=a.slot.frame_uid if a else None,
                model_suffix=suffix,native_slots=self.history.budget,attachment_slots=int(a is not None))
            return question+suffix
        if self.settings['evidence_policy'] in ('landmark_attachment','evo_event_attachment'):
            from .host_input_compiler import VisualInputs,attachment_suffix
            a=self.attachment
            if a is None:
                self.use_uniform('no_historical_attachment');return question
            if self.evidence_card is None:raise IntegrityError('Image lacks structured landmark evidence')
            suffix=self.evidence_card.suffix()
            if self.settings['evidence_policy']=='evo_event_attachment':
                suffix=suffix.replace('Historical source photograph:',self.anchor_caption+' (historical source photograph):',1)
            ids=tokenize_prompt(prompt_fn(question+suffix)).reshape(-1)
            total=self.history.budget+1
            if len(tokenizer.encode(suffix,add_special_tokens=False))>self.settings['max_fact_tokens'] or len(ids)+total*(per_image-1)+256>limit:
                self.use_uniform('attachment_exceeds_context');return question
            self.combined=VisualInputs(self.history,a)
            self.emit('MemoryAttachmentCompiled',snapshot_id=self.history.snapshot_id,
                native_slots=self.history.budget,attachment_slots=1,attachment_step=a.slot.env_step,
                attachment_frame=a.slot.frame_uid,source_refs=a.record.source_refs,text=a.record.text,
                source_image_hash=a.slot.source_image_hash,additional_projected_tokens=per_image,
                model_fields=self.evidence_card.fields(),model_suffix=suffix)
            return question+suffix
        if self.settings['evidence_policy'] in ('additive_text','context_text'):
            from .evidence import append_evidence
            enriched,used=append_evidence(question,self.facts,lambda text:len(tokenizer.encode(text,add_special_tokens=False)),
                fits,self.settings['max_fact_tokens'])
            if not used:
                self.use_uniform('no_supplement_within_budget')
            else:
                self.used_context=used if self.settings['evidence_policy']=='context_text' else ()
                if self.settings.get('suppress_same_frame_repeat'):
                    self.used_frame_records=used
                self.emit('AdditionalEvidenceCompiled',snapshot_id=self.history.snapshot_id,
                    records=[dict(text=f.text,source_refs=f.source_refs,steps=f.steps) for f in used])
            return enriched
        compiled = compile_question(question, self.history,
            token_count=lambda text: len(tokenizer.encode(text, add_special_tokens=False)),
            context_fits=fits, facts=self.facts,
            include_facts=self.mode in ("graph_image_facts","facts_only"),
            mode=self.mode, max_fact_tokens=self.settings["max_fact_tokens"])
        if compiled.fallback_reason:
            self.use_uniform(compiled.fallback_reason)
        return compiled.question


def vision_budget(model):
    config = model.config
    tower = model.get_vision_tower()
    vision = tower.vision_tower.config
    projector = model.get_mm_projector()
    if (vision.model_type != "siglip_vision_model" or config.s2
            or tower.select_feature != "cls_patch"
            or projector.layers[0].__class__.__name__ != "DownSampleBlock"):
        raise ReadUnavailable("unverified_vision_expansion")
    grid = vision.image_size // vision.patch_size
    return ((grid + 1) // 2) ** 2, model.llm.config.tokenizer_model_max_length


def _native_reply_slots(reply,query,observation_count,budget):
    if observation_count!=query['current_capture_seq']:
        raise IntegrityError("Host observations differ from current capture sequence")
    indices=native_slot_indices(observation_count,budget)
    refs=tuple(_view(v) for v in reply['native_views'])
    real=[i for i in indices if i is not None]
    if len(refs)!=len(real) or len({v.frame_uid for v in refs})!=len(real):
        raise IntegrityError("Incomplete or repeated native sample")
    for i,v in zip(real,refs):
        if (v.capture_seq!=i+1 or v.env_step!=i or v.episode_uid!=query['episode_uid']
                or v.snapshot_id!=query['snapshot_id']):
            raise IntegrityError("Native sample differs from host ordinal or snapshot")
        if i!=observation_count-1 and (v.source_snapshot_id!=query['snapshot_id']
                or v.capture_seq>query['cutoff_capture_seq'] or v.event_seq>query['cutoff_event_seq']):
            raise IntegrityError("Historical sample outside pinned evidence")
    return refs,(None,)*(len(indices)-len(real))+tuple(v.frame_uid for v in refs)


def check_delivered_reasoning(hook,packet,text,event):
    previous=getattr(hook,'last_generated_reasoning',None)
    scope=(packet.episode_uid,packet.pose_record['episode_instance'])
    if previous is not None and previous[:2]!=scope:previous=None
    if text or event is not None:
        if type(event)is not int or previous!=(*scope,event,text):
            raise IntegrityError('Query reasoning differs from the last native REASON result')
    elif previous is not None:
        raise IntegrityError('Query omitted the last native REASON result')


def landmark_vocabulary(hook):
    from .contracts import CategoryVocabulary
    if not hasattr(hook,'retrieval_vocabulary'):
        project=Path(__file__).resolve().parents[4]
        hook.retrieval_vocabulary=CategoryVocabulary.from_file(project/'vendor_sources/EvoMemNav/data/scannet200_classes.txt')
    return hook.retrieval_vocabulary


def validate_evo_read_header(reader,reply,query):
    """Bind the received public header to the opened historical revision before recording candidates."""
    if (reader.identity['episode_uid']!=query['episode_uid'] or reader.snapshot_id!=query['snapshot_id']
            or reply['snapshot_id']!=reader.snapshot_id):
        raise IntegrityError('Evo read belongs to a different publication')
    for field,expected in [('cutoff',reader.cutoff),('versions',reader.versions)]:
        actual=reply.get(field)
        if (not isinstance(actual,dict) or actual.keys()!=expected.keys()
                or any(type(actual[k]) is not type(v) or actual[k]!=v for k,v in expected.items())):
            raise IntegrityError('Evo read differs from published '+field)
    if (query['cutoff_capture_seq']!=reader.cutoff['capture_seq']
            or query['cutoff_event_seq']!=reader.cutoff['event_seq']):
        raise IntegrityError('Evo request and publication cutoff differ')


def start_decision(hook, *, instruction, reasoning, reasoning_event, host_images, budget, sampler):
    settings = retrieval_settings(hook.profile["map_memory"])
    if settings is None:
        raise ValueError("Explicit retrieval profile required")
    started=time.monotonic()
    deadline=started+settings['read_timeout_seconds']
    packet=hook.latest_packet
    if packet is not None:
        check_delivered_reasoning(hook,packet,reasoning,reasoning_event)
    skip='budget_le_two' if budget<=2 else None
    scope=None
    if skip is None and settings.get('context_admission')=='native_plan_photo':
        from .evidence import landmark_query_cues
        if packet is None or reasoning_event is None:
            skip='no_native_plan'
        elif not landmark_query_cues(instruction,reasoning,landmark_vocabulary(hook).labels):
            skip='no_landmark_in_native_plan'
    if skip is None and packet is not None and settings['evidence_policy']=='historical_approach':
        from .semantic_topology import requested_exit_room
        scope=(packet.episode_uid,packet.pose_record['episode_instance'],reasoning_event)
        if reasoning_event is None or not requested_exit_room(instruction,reasoning):
            skip='no_explicit_return_need'
        elif getattr(hook,'delivered_approach_scope',None)==scope:
            skip='approach_already_shown'
    handle=hook.prepare_memory_read(read_deadline=deadline,poll_only=skip is not None)
    event=hook.coordinator.decision()
    decision=HostDecision(hook,event,settings['mode'],settings,approach_scope=scope,started_monotonic=started)
    if handle['snapshot_id'] is None:
        decision.use_uniform('no_published_snapshot' if handle['fresh_enough'] else skip or 'visibility_deadline')
        return decision
    if skip is not None:
        decision.use_uniform(skip)
        return decision
    if settings['evidence_policy']=='evo_event_attachment':
        from .dynamic_context import DecisionGate
        if not hasattr(hook,'evo_gate'):hook.evo_gate=DecisionGate()
        session=(handle['episode_uid'],packet.pose_record['episode_instance'])
        trigger=hook.evo_gate.trigger(session,packet.frame_uid,packet.action,reasoning_event)
        if not hook.evo_gate.consume_event(trigger):
            decision.use_uniform('no_new_memory_read_event')
            return decision
        decision.emit('EvoReadTrigger',trigger=trigger,snapshot_id=handle['snapshot_id'])
    request_id = uuid.uuid4().hex
    decision.request_id = request_id
    query = dict(episode_uid=handle["episode_uid"], snapshot_id=handle["snapshot_id"],
        current_frame_uid=handle["current_frame_uid"], current_capture_seq=handle["current_capture_seq"],
        cutoff_capture_seq=handle["cutoff"]["capture_seq"], cutoff_event_seq=handle["cutoff"]["event_seq"],
        decision_id=event['decision_id'],decision_event_seq=event["event_seq"], instruction=instruction,
        last_reasoning=reasoning or None,last_reasoning_event_seq=reasoning_event if reasoning else None)
    request = dict(protocol_version=3, request_id=request_id,
        episode_instance=packet.pose_record["episode_instance"], mode=decision.mode, budget=budget, query=query)
    decision.emit("MemoryReadRequested",snapshot_id=handle["snapshot_id"],cutoff=dict(handle["cutoff"]),
                  protocol_version=3,decision_event_seq=event['event_seq'],reasoning_event=query['last_reasoning_event_seq'])
    try:
        channel = hook.memory_stream.channel
        if time.monotonic()>=deadline:
            raise ReadDeadlineExpired('read_deadline_before_admission')
        future=channel.submit_read(request)
        try:
            if hasattr(channel,'wait_read_until'):
                reply=channel.wait_read_until(future,round(deadline*1e9))
            else:reply=channel.wait_read(future,max(0.,deadline-time.monotonic()))
        except ReadDeadlineExpired:
            receipt=getattr(future,'expiry_receipt',None)
            if receipt is not None:hook.memory_stream.track_expired_read(request,receipt)
            raise
        finally:
            if hasattr(channel,'read_timing'):
                decision.emit('MemoryReadTiming',snapshot_id=handle['snapshot_id'],
                              decision_started_ns=round(started*1e9),deadline_ns=round(deadline*1e9),
                              **channel.read_timing(future))
        # The root is independently derived by the host when beginning this episode.
        expected_root = hook.memory.active_read_root
        if Path(reply["episode_root"]).resolve() != expected_root or reply["mode"] != decision.mode:
            raise IntegrityError("Read reply returned an unbound root or mode")
        if reply.get('unavailable_reason') in ('native_sample_unavailable','missing_material','undecodable_image','undecodable_features','undecodable_depth'):
            if (reply.get('read_only') is not True or reply.get('cutoff')!=dict(handle['cutoff'])
                    or reply.get('current_capture_seq')!=query['current_capture_seq']
                    or reply.get('current_frame_uid')!=query['current_frame_uid']):
                raise IntegrityError('Unbound unavailable native sample')
            raise ReadUnavailable(reply['unavailable_reason'])
        if 'unavailable_reason' in reply:
            if (settings['evidence_policy']!='historical_approach' or reply.get('evidence_policy')!='historical_approach'
                    or reply['unavailable_reason']!='no_connected_approach' or reply.get('read_only') is not True
                    or reply.get('current_frame_uid')!=query['current_frame_uid']
                    or reply.get('current_capture_seq')!=query['current_capture_seq']
                    or reply.get('cutoff')!=dict(handle['cutoff'])):
                raise IntegrityError('Invalid negative retrieval receipt')
            # Independently verify the absence at the same historical pin. No image materialization is needed.
            from .semantic_topology import historical_approach,requested_exit_room
            with closing(load_episode(expected_root,revision=query['snapshot_id'])) as reader:
                room=requested_exit_room(instruction,reasoning)
                if (reader.identity['episode_uid']!=query['episode_uid'] or dict(reader.cutoff)!=reply['cutoff']
                        or room is None or historical_approach(reader,query['current_capture_seq'],room) is not None):
                    raise IntegrityError('Negative retrieval receipt differs from pinned map')
            raise ReadUnavailable('no_connected_approach')
        if settings['evidence_policy']=='evo_topology':
            if reply.get('evidence_policy')!='evo_topology':
                raise IntegrityError('Evo read omitted its selected policy')
            if 'channels' not in reply:raise IntegrityError('Missing Evo anchor channel')
            source_pin=reply.get('current_source_snapshot_id')
            if not isinstance(source_pin,str) or len(source_pin)!=64 or any(c not in '0123456789abcdef' for c in source_pin):
                raise IntegrityError('Evo read lacks a concrete current observation revision')
        native_views,native_ids=_native_reply_slots(reply,query,len(host_images),budget)
        current = native_views[-1]
        if (current.frame_uid != query["current_frame_uid"] or current.episode_uid != query["episode_uid"]
                or current.source_snapshot_id != reply["current_source_snapshot_id"]):
            raise IntegrityError("Current source differs from decision frame")
        if reply.get('evidence_policy') is not None and reply['evidence_policy']!=settings['evidence_policy']:
            raise IntegrityError('Worker and host memory policies differ')
        graph_selection = _selection(reply["selection"]) if reply["selection"] is not None else None
        uniform_mode = decision.mode in ("uniform_original", "uniform_tagged", "facts_only", "native_plus_attachment")
        if uniform_mode:
            selected = Selection(native_views, (), (), (), None, budget)
        else:
            if graph_selection is None or graph_selection.fallback_reason:
                raise ReadUnavailable(graph_selection.fallback_reason if graph_selection else "no_selection")
            selected = graph_selection
        image_cache=None;page_cache=None
        if settings['evidence_policy']=='evo_topology':
            from ..storage.pages import EpisodeImageCache,HistoryPageCache
            from ..storage.store import DEFAULT_SNAPSHOT_CACHE_BYTES
            page_cache=getattr(hook,'retrieval_page_cache',None)
            if page_cache is None:
                page_cache=HistoryPageCache(expected_root,DEFAULT_SNAPSHOT_CACHE_BYTES//2,episode=query['episode_uid'])
                hook.retrieval_page_cache=page_cache
            image_cache=getattr(hook,'retrieval_image_cache',None)
            if image_cache is None:
                image_cache=EpisodeImageCache(expected_root,DEFAULT_SNAPSHOT_CACHE_BYTES//4,episode=query['episode_uid'])
                hook.retrieval_image_cache=image_cache
        reader = load_episode(expected_root, revision=query["snapshot_id"],image_cache=image_cache,_history_cache=page_cache)
        try:
            if settings['evidence_policy']=='evo_topology':
                validate_evo_read_header(reader,reply,query)
            lazy_photo=settings.get('context_admission')=='native_plan_photo'
            history=None if lazy_photo else materialize_history(selected, reader, host_images[-1], current=current, sampler=sampler)
            if settings['evidence_policy']=='evo_topology':
                from .evo_host import verify_evo_reply
                decision.evo_evidence=verify_evo_reply(reader,reply,query,current,landmark_vocabulary(hook),
                    include_relations=settings.get('topology_relations',False),include_context=settings.get('context_bundle',False))
                decision.evo_cutoff_step=reader.cutoff['capture_seq']-1
            decision.emit("MemoryCandidates", snapshot_id=reply["snapshot_id"], channels=reply["channels"],
                **({'semantic_score_cache':reply['semantic_score_cache']} if 'semantic_score_cache' in reply else {}),
                **({'context_channels':reply['evo_context']['channels'],'context_counts':reply['evo_context']['counts']}
                   if 'evo_context' in reply else {}),
                candidates=[dict(frame_uid=row["view"]["frame_uid"], ranks=row["ranks"], score=row["score"],
                            matched_categories=row["matched_categories"]) for row in reply.get("candidates",())])
            if settings['evidence_policy']=='historical_approach':
                from .semantic_topology import requested_exit_room,historical_approach
                expected=historical_approach(reader,current.capture_seq,requested_exit_room(instruction,reasoning))
                if expected!=reply.get('approach'):raise IntegrityError('Worker approach differs from pinned host evidence')
                if not expected:raise ReadUnavailable('no_connected_approach')
                decision.approach=expected
                if decision.mode=='native_plus_attachment':
                    from .evidence import ExtraRecord
                    from .host_input_compiler import make_view_attachment
                    uid=expected['before']
                    record=ExtraRecord('Earlier source view',(uid,),(expected['before_step'],))
                    if settings.get('approach_photo_support')=='shared_depth' and uid not in {s.frame_uid for s in history.slots}:
                        from .semantic_topology import approach_photo_support
                        current_pin=(nullcontext(reader) if current.source_snapshot_id==reader.snapshot_id
                                     else closing(load_episode(expected_root,revision=current.source_snapshot_id)))
                        with current_pin as live_reader:
                            decision.photo_support=approach_photo_support(reader,live_reader,uid,current)
                    if decision.photo_support is None or decision.photo_support['shared_samples']>0:
                        decision.attachment=make_view_attachment(history,reader,uid,record)
            if reply.get('evidence_policy') in ('additive_text','context_text','landmark_attachment','evo_event_attachment','dynamic_evo_context'):
                from .evidence import resolve
                landmark_vocabulary(hook)
                proposals=reply['additional_evidence']
                if reply['evidence_policy'] in ('evo_event_attachment','dynamic_evo_context'):
                    decision.anchor_object=verify_anchor_proposal(reader,reply)
                if settings.get('landmark_query')=='current_plan':
                    from .evidence import landmark_query_cues
                    cues=landmark_query_cues(instruction,reasoning,hook.retrieval_vocabulary.labels)
                    if (reply.get('landmark_query_cues')!=list(cues)
                            or reply.get('landmark_reasoning_event')!=query['last_reasoning_event_seq']
                            or any(row.get('kind')!='landmark' or row.get('label') not in cues for row in reply['additional_evidence'])):
                        raise IntegrityError('Landmark proposal differs from the bound navigation plan')
                    ranked=checked_landmark_ranks(reader,reply,hook.retrieval_vocabulary,
                        set(native_ids)-{None},query['current_capture_seq'])
                    decision.emit('LandmarkQuery',snapshot_id=query['snapshot_id'],categories=list(cues),
                                  ranked_sources=ranked,object_epoch=reader._graph['scene_state']['epoch'] if ranked else None,
                                  reasoning_event=query['last_reasoning_event_seq'],candidates=len(reply['additional_evidence']))
                    policy=settings.get('landmark_ambiguity')
                    if policy and ranked:
                        if policy=='check_historical_anchors':
                            from .semantic_topology import competing_anchor_member
                            check=competing_anchor_member(reader,ranked[0],ranked,hook.retrieval_vocabulary,
                                                          query['current_capture_seq'])
                            decision.emit('LandmarkInstanceCheck',snapshot_id=reader.snapshot_id,
                                          chosen=ranked[0],check=check,reasoning_event=query['last_reasoning_event_seq'])
                            unresolved=check['status']!='no_competitor'
                            competing={ranked[0]['object_id']}
                            if 'source' in check:competing.add(check['source']['object_id'])
                        else:
                            competing={r['object_id'] for r in ranked if r['label']==ranked[0]['label']}
                            unresolved=len(competing)>1
                        if unresolved:
                            decision.emit('LandmarkAmbiguous',snapshot_id=reader.snapshot_id,
                                          source_class=ranked[0]['label'],object_ids=sorted(competing),
                                          reasoning_event=query['last_reasoning_event_seq'])
                            proposals=[]
                            decision.anchor_object=None
                if reply['evidence_policy']=='context_text':
                    from .evidence import resolve_context,fresh_records
                    identity=(handle['episode_uid'],packet.pose_record['episode_instance'])
                    if getattr(hook,'context_delivery_identity',None)!=identity:
                        hook.context_delivery_identity=identity
                        hook.context_delivered=set()
                    verified=resolve_context(reply['additional_evidence'],reader,hook.retrieval_vocabulary,current.capture_seq,instruction)
                    decision.facts=fresh_records(verified,hook.context_delivered)
                    if verified and not decision.facts:raise ReadUnavailable('context_already_delivered')
                else:
                    decision.facts=resolve(proposals,reader,hook.retrieval_vocabulary,current.capture_seq,instruction)
                if reply['evidence_policy'] in ('landmark_attachment','evo_event_attachment','dynamic_evo_context'):
                    from .host_input_compiler import make_attachment
                    if settings.get('landmark_repeat') is not None:
                        from .dynamic_context import LandmarkDelivery
                        decision.landmark_delivery=LandmarkDelivery.for_decision(
                            getattr(hook,'landmark_delivery',None),query['episode_uid'],
                            request['episode_instance'],reasoning_event)
                        hook.landmark_delivery=decision.landmark_delivery
                    for record in decision.facts:
                        if decision.landmark_delivery is not None:
                            proposal,=reply['additional_evidence']
                            key=decision.landmark_delivery.evidence_key(settings['landmark_repeat'],record.source_refs,
                                                                      decision.anchor_object,proposal['label'])
                            if key in decision.landmark_delivery.sources:
                                if settings['landmark_repeat']=='object_once_per_reasoning':
                                    decision.emit('LandmarkObjectAlreadyShown',source=decision.anchor_object,
                                                  source_class=proposal['label'],reasoning_event=reasoning_event)
                                continue
                            decision.landmark_delivery_key=key
                        if reply['evidence_policy']=='evo_event_attachment' and record.source_refs in hook.evo_gate.delivered:
                            continue
                        if settings.get('native_object')=='skip_present':
                            from .semantic_topology import native_object_slot
                            proposal,=reply['additional_evidence']
                            if lazy_photo:
                                from .semantic_topology import preflight_native_object
                                present=preflight_native_object(reader,native_views,native_ids,host_images,
                                    decision.anchor_object,proposal['label'],hook.retrieval_vocabulary)
                            else:
                                present=native_object_slot(reader,history,decision.anchor_object,proposal['label'],hook.retrieval_vocabulary)
                            if present is not None:
                                decision.emit('LandmarkInNativeSlot',snapshot_id=reader.snapshot_id,
                                              source=decision.anchor_object,source_class=proposal['label'],native=present)
                                continue
                        if history is None:
                            history=materialize_history(selected,reader,host_images[-1],current=current,sampler=sampler)
                        decision.attachment=make_attachment(history,reader,record)
                        if decision.attachment is not None:break
                    if decision.attachment is None:
                        if reply['evidence_policy']!='dynamic_evo_context':raise ReadUnavailable('no_distinct_landmark_photograph')
                        decision.facts=()
                    else:
                        decision.facts=(decision.attachment.record,)
                        from .host_input_compiler import from_source
                        decision.evidence_card=from_source(decision.attachment,reader,history,instruction,hook.retrieval_vocabulary)
                        if settings.get('landmark_position')=='fused_center':
                            from .semantic_topology import selected_object_position
                            current_pin=(nullcontext(reader) if reader.snapshot_id==current.source_snapshot_id
                                         else closing(load_episode(expected_root,revision=current.source_snapshot_id)))
                            with current_pin as live_reader:
                                decision.object_position=selected_object_position(reader,live_reader,current,
                                    decision.attachment,decision.evidence_card,hook.retrieval_vocabulary)
                        if reply['evidence_policy']=='evo_event_attachment':
                            uid=decision.attachment.slot.frame_uid
                            node=reader.get_retrieval_index()['anchors'].get(uid)
                            if node is None:raise IntegrityError('Attachment is not a pinned anchor')
                            room=node.get('room_type_hint') or 'unknown'
                            import re
                            if not re.fullmatch(r'[a-zA-Z][a-zA-Z -]{0,50}',room) or reply['anchor_prompt_label']!=f'Anchor View 0 (room: {room})':
                                raise IntegrityError('Unverified upstream anchor caption')
                            decision.anchor_caption=reply['anchor_prompt_label']
                if settings.get('suppress_same_frame_repeat') and decision.facts:
                    identity=(handle['episode_uid'],packet.pose_record['episode_instance'],current.frame_uid)
                    if getattr(hook,'frame_delivery_identity',None)!=identity:
                        hook.frame_delivery_identity=identity
                        hook.frame_delivered=set()
                    decision.facts=tuple(f for f in decision.facts if (f.source_refs,f.text) not in hook.frame_delivered)
                    if not decision.facts:raise ReadUnavailable('same_frame_evidence_already_delivered')
                if reply['evidence_policy']=='dynamic_evo_context':
                    from .dynamic_context import WindowCursor,build_window
                    if settings.get('context_admission')=='native_plan_photo':
                        if decision.attachment is None:
                            raise ReadUnavailable('no_eligible_plan_photo')
                        start=reader.cutoff['capture_seq']
                    else:
                        if not hasattr(hook,'graph_window_cursor'):hook.graph_window_cursor=WindowCursor()
                        cursor=hook.graph_window_cursor
                        start=cursor.bind(query['episode_uid'],request['episode_instance'],current.frame_uid,reader.snapshot_id,reader.cutoff['capture_seq'])
                    decision.window=build_window(reader,current,start,decision.attachment)
                elif not decision.facts:raise ReadUnavailable('no_supported_extra_evidence')

            if reply.get('evidence_policy') in ('instruction_grounded','grounded_single_slot') and decision.mode in ('graph_image_facts','facts_only'):
                landmark_vocabulary(hook)
                decision.facts=grounded_fact_lines(history,reply['instruction_detections'],reader,hook.retrieval_vocabulary)
            if (reply.get('evidence_policy') not in ('instruction_grounded','grounded_single_slot')
                    and graph_selection and decision.mode in ('facts_only','graph_image_facts')):
                decision.facts=verified_relation_facts(reader,history,graph_selection,reply['relations'])
        finally:
            reader.close()
        if uniform_mode:
            native = sampler(host_images, num_frames=budget)
            if [pixel_hash(x) for x in native] != [slot.host_pixel_hash for slot in history.slots]:
                raise IntegrityError("Uniform control differs from original host sampler")
            history=replace(history,images=tuple(native))
        decision.history = history
        final_ids = tuple(s.frame_uid for s in history.slots)
        if len(native_ids)!=len(final_ids) or final_ids[-1]!=native_ids[-1]:
            raise IntegrityError('Memory selection changed the host image budget or current slot')
        changed = [i for i,(before,after) in enumerate(zip(native_ids,final_ids),1) if before!=after]
        policy = reply.get('evidence_policy','ranked')
        if uniform_mode and changed:
            raise IntegrityError('Uniform diagnostic changed original slot identities')
        if policy in ('grounded_single_slot','linked_history_single_slot','linked_view_gain') and len(changed)>1:
            raise IntegrityError('Single-slot profile displaced multiple original host observations')
        decision.emit("MemoryMaterialized", snapshot_id=history.snapshot_id,
            selected=list(final_ids),native_slots=list(native_ids),replaced_slots=changed,checkpoint_budget=budget, current_source_snapshot_id=current.source_snapshot_id,
            original_image_hashes=[s.source_image_hash for s in history.slots],
            evidence_policy=reply.get("evidence_policy","ranked"),
            groups=[dict(seed_ref=g.seed_ref,view_refs=[v.frame_uid for v in g.views],edge_types=g.edge_types,execution_refs=g.execution_refs,reason=g.selection_reason) for g in selected.groups], fact_sources=[ref for f in decision.facts for ref in (f.source_refs if hasattr(f,'source_refs') else (f.source_ref,))])
    except UnavailableMaterial as error:
        decision.use_uniform(error.reason)
    except FileNotFoundError as error:
        # Revision pruning can race opening the reader. Missing code or model dependencies are errors.
        if (hook.memory_stream.channel.status()['failure'] is not None or error.filename is None
                or not Path(error.filename).resolve().is_relative_to(hook.memory.active_read_root)):
            decision.emit('MemoryReadRejected',error_type=type(error).__name__,reason=str(error))
            raise
        decision.use_uniform('missing_material')
    except (ReadUnavailable, ReadAdmissionFull, ReadDeadlineExpired) as error:
        decision.use_uniform(str(error))
    except Exception as error:
        decision.emit("MemoryReadRejected", error_type=getattr(error,"remote_error_type",type(error).__name__), reason=str(error))
        raise
    return decision


@contextmanager
def observe_projector(model, decision, report, call_id, images_tensor=None):
    """Validate actual native projector output before the language model consumes it."""
    if report is None:
        yield
        return
    expected = report["expanded_input_tokens"] - report["text_and_placeholder_tokens"] + report["logical_image_slots"]
    observations = []
    attachments=report.get('memory_attachment_slots',0)
    native=report.get('native_image_slots',report['logical_image_slots'])
    batches=[native]+[1]*attachments
    if type(attachments)is not int or attachments<0:raise IntegrityError('Invalid attachment count')
    def verify(module,args,output):
        n=len(observations)
        if output.ndim!=3 or n>=len(batches) or output.shape[0]!=batches[n] or output.shape[1]*sum(batches)!=expected:
            raise IntegrityError('Visual expansion differs from the audited grouped budget')
        observations.append(tuple(output.shape))
    from .input_audit import separate_attachment_encoding
    cache=None;kwargs={}
    if attachments and decision.settings.get('attachment_feature_cache_bytes',0)>0:
        from .input_audit import AttachmentFeatureCache
        packet=decision.hook.latest_packet
        scope=(packet.episode_uid,packet.pose_record['episode_instance'])
        cache=getattr(decision.hook,'attachment_feature_cache',None)
        if cache is None:
            cache=AttachmentFeatureCache(decision.settings['attachment_feature_cache_bytes'])
            decision.hook.attachment_feature_cache=cache
        before=(cache.hits,cache.encodes)
        kwargs=dict(cache=cache,scope=scope,receipt_keys=[row['tensor_sha256'] for row in report['slots'][native:]],
                    expected_tensor=images_tensor)
    grouping=separate_attachment_encoding(model,native,attachments,**kwargs) if attachments else nullcontext()
    registration=model.get_mm_projector().register_forward_hook(verify)
    try:
        with grouping:yield
        if len(observations)!=len(batches):raise IntegrityError('Incomplete visual consumption')
        shape=(sum(batches),*observations[0][1:])
        if cache is not None:
            decision.emit('AttachmentFeatureReuse',call_id=call_id,snapshot_id=report['snapshot_id'],
                          hits=cache.hits-before[0],encodes=cache.encodes-before[1],resident_bytes=cache.bytes,
                          bypassed=attachments-(cache.hits-before[0])-(cache.encodes-before[1]))
        decision.emit('MemoryGenerateReturned',call_id=call_id,projector_shape=shape,projector_batches=observations,
                      snapshot_id=report['snapshot_id'])
        if decision.approach is not None:
            decision.hook.delivered_approach_scope=decision.approach_scope
        if attachments and decision.landmark_delivery is not None:
            decision.landmark_delivery.sources.add(decision.landmark_delivery_key)
        if attachments and decision.settings['evidence_policy']=='evo_event_attachment':
            decision.hook.evo_gate.delivered.add(decision.attachment.record.source_refs)
        if decision.used_frame_records:
            decision.hook.frame_delivered.update((f.source_refs,f.text) for f in decision.used_frame_records)
        if decision.used_context:
            from .evidence import delivery_key
            decision.hook.context_delivered.update(delivery_key(record) for record in decision.used_context)
    finally:
        registration.remove()


class HostInjection:
    """One decision. Materialize, compile, process and audit before original generate."""

    def __init__(self, decision, host_images, budget, sampler):
        self.decision = decision
        self.materialized_ns=time.monotonic_ns()
        self.host_images = host_images
        self.budget = budget
        self.sampler = sampler
        self.images = (list(decision.history.images) if decision.history is not None
                       else sampler(host_images, num_frames=budget))
        self.receipt = None
        self.original_question = None
        self.expected_prompt = None
        self.fallback_tensor = None
        self.fallback_version = None
        self.cast_at_preprocess = False

    @classmethod
    def begin(cls, hook, *, instruction, reasoning, reasoning_event, host_images, budget, sampler):
        decision = start_decision(hook, instruction=instruction, reasoning=reasoning,
                                  reasoning_event=reasoning_event, host_images=host_images,
                                  budget=budget, sampler=sampler)
        return cls(decision, host_images, budget, sampler)

    def compile(self, question, prompt_fn, tokenizer, tokenize_prompt, model):
        self.original_question = question
        self.receipt = None
        self.fallback_tensor = None
        self.expected_prompt = None
        if self.decision.history is not None:
            try:
                question = self.decision.compile(question, prompt_fn, tokenizer, tokenize_prompt, model)
            except ReadUnavailable as error:
                self.decision.use_uniform(str(error))
            if self.decision.history is None:
                self.images = self.sampler(self.host_images, num_frames=self.budget)
            else:
                self.images = list(self.decision.model_visuals.images)
        if self.decision.settings.get('evidence_policy')=='evo_topology':
            if not question.startswith(self.original_question):
                raise IntegrityError('Evo material changed the native navigation question')
            suffix=question[len(self.original_question):]
            if self.decision.history is None and suffix:
                raise IntegrityError('Fallback retained stale graph material')
        self.expected_prompt = prompt_fn(question)
        self.compiled_ns=time.monotonic_ns()
        return question

    def preprocess(self, image_processor, model_config, process_images, *, cast_to_model=None):
        if self.expected_prompt is None:
            raise IntegrityError('Compile this decision before preprocessing')
        if self.decision.history is None:
            tensor=process_images(self.images,image_processor,model_config)
        else:
            tensor,self.receipt=observe_process_images(self.decision.model_visuals,image_processor,
                                                       model_config,process_images=process_images)
        self.cast_at_preprocess = cast_to_model is not None
        if cast_to_model is not None:
            tensor=cast_to_model(tensor)
        if self.decision.history is None:
            self.fallback_tensor=tensor
            try:
                self.fallback_version=tensor._version
            except RuntimeError:
                # Inference tensors have no mutation counter. Keep an independent exact witness.
                self.fallback_tensor=tensor.detach().clone()
                self.fallback_version=None
        self.preprocessed_ns=time.monotonic_ns()
        return tensor

    def generation(self, *, model, call_id, images_tensor, prompt, input_ids,
                   tokenize_prompt, image_token_id, generation_config):
        if self.expected_prompt is None or prompt!=self.expected_prompt:
            raise IntegrityError('Final prompt differs from the compiled decision')
        if self.decision.history is None:
            import torch
            verified_prompt_tokens(prompt,input_ids,tokenize_prompt,image_token_id,self.budget)
            expected=self.fallback_tensor
            if expected is None or not isinstance(images_tensor,torch.Tensor):
                raise IntegrityError('Missing native fallback preprocessing result')
            if self.fallback_version is not None and expected._version!=self.fallback_version:
                raise IntegrityError('Native fallback tensor mutated after preprocessing')
            if self.cast_at_preprocess and (images_tensor.dtype!=expected.dtype or images_tensor.device!=expected.device):
                raise IntegrityError('Final fallback tensor changed model dtype or device')
            if images_tensor is not expected and (images_tensor.shape!=expected.shape or
                    not torch.equal(images_tensor,expected.to(images_tensor.device,dtype=images_tensor.dtype))):
                raise IntegrityError('Final fallback tensor differs from native preprocessing')
        elif self.receipt is None:
            raise IntegrityError('Missing memory preprocessing receipt')
        report = None
        if self.receipt is not None:
            per_image, limit = vision_budget(model)
            report = audit_final_inputs(history=self.decision.model_visuals, receipt=self.receipt,
                images_tensor=images_tensor, prompt=prompt, input_ids=input_ids, tokenize_prompt=tokenize_prompt,
                original_question=self.original_question, image_token_id=image_token_id,
                generation_config=generation_config, vision_tokens_per_slot=[per_image]*len(self.images),
                context_limit=limit)
            report.update(native_image_slots=self.budget, memory_attachment_slots=len(self.images)-self.budget,
                          current_native_image_index=self.budget)
            self.decision.emit('HostInputAudit', call_id=call_id, **report)
        if self.decision.request_id is not None:
            self.decision.emit('HostReadInputReady',call_id=call_id,
                materialized_ns=self.materialized_ns,compiled_ns=self.compiled_ns,
                preprocessed_ns=self.preprocessed_ns,ready_ns=time.monotonic_ns(),
                used_memory=report is not None)
        return observe_projector(model, self.decision, report, call_id,images_tensor)

    def record_reasoning(self,call_id,text):
        import hashlib
        hook=self.decision.hook;packet=hook.latest_packet
        if (not isinstance(text,str) or type(call_id)is not int or call_id!=self.decision.event['decision_id']
                or packet.frame_uid!=self.decision.event['frame_uid'] or hook.coordinator.decision_id!=call_id):
            raise IntegrityError('Native reasoning receipt differs from current host decision')
        if getattr(self,'reasoning_recorded',False):
            raise IntegrityError('Duplicate native reasoning receipt')
        receipt=self.decision.emit('MemoryReasoningAvailable',call_id=call_id,
                                   reasoning_sha256=hashlib.sha256(text.encode()).hexdigest())
        self.reasoning_recorded=True
        if not text.strip():
            hook.last_generated_reasoning=None
            return None
        event=receipt['event_seq']
        hook.last_generated_reasoning=(packet.episode_uid,packet.pose_record['episode_instance'],event,text)
        return event

