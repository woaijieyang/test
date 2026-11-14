from dataclasses import asdict
import numpy as np
import pytest
from graphAdapter.map_memory.storage.store import EpisodeStore,canonical,digest,IntegrityError,load_episode
from graphAdapter.map_memory.tests.test_storage import capture,graph,arrays,EP
from graphAdapter.map_memory.retrieval.contracts import CategoryVocabulary,MemoryQuery,EncodedQuery
from graphAdapter.map_memory.retrieval.session import MemoryRetrievalSession

VOCAB=CategoryVocabulary.from_bytes(b'other\nchair\nwall\ndoor\n')
MODEL={'weights':{'clip':'fixed'},'preprocess_hash':'p','vocabulary_sha256':VOCAB.source_sha256}
class Encoder:
    model_batches=0;cache_hits=0;cache_bytes=0
    def encode(self,q):
        self.model_batches+=1
        return EncodedQuery(q.instruction_hash,digest(canonical(MODEL)),'t',np.array([[1.,0.,0.]]))

def recorded(tmp_path):
    store=EpisodeStore(tmp_path/'map',EP,dataset='r2r');records={};ids=[]
    for n in range(1,6):
        rgb,raw,aligned,mask=arrays();rgb[:]=n
        raw_record=store.archive_frame(capture(n),rgb,raw,aligned,mask,host_view=rgb,host_transform={'kind':'identity'})
        uid=capture(n)['frame_uid']
        detections={'xyxy':np.array([[1,1,4,4]],np.float32),'mask':np.ones((1,8,8),bool),'confidence':np.array([.8],np.float32),
            'class_id':np.array([3]),'image_feats':np.array([[1.,0.,0.]],np.float32),'full_clip':np.array([1.,0.,0.],np.float32)}
        records[uid]=store.save_detections(uid,detections,{'count':1,'image_hw':[8,8],'has_full_clip':True,
            'raw_signature':raw_record['raw_signature'],'model_identity_hash':digest(canonical(MODEL))})
        g=graph(list(range(1,n+1)));g['model_identity']=MODEL
        for key in g['views']:g['views'][key]['detection_record']=records[key]
        ids.append(store.publish(g,{'pose_map_version':0},{'capture_seq':n,'event_seq':10*n})['snapshot_id'])
    store.close();return tmp_path/'map',ids[-2:]

def request(ids,mode='graph_image_only'):
    q=MemoryQuery(EP,ids[0],capture(5)['frame_uid'],5,4,40,'Pass the door.')
    return {'protocol_version':1,'request_id':'test-read','episode_instance':'session','mode':mode,'budget':8,'query':asdict(q)}

def test_pinned_history_and_newer_current_have_separate_source_identities(tmp_path):
    root,ids=recorded(tmp_path);session=MemoryRetrievalSession(root,EP,'session',Encoder(),VOCAB)
    try:
        reply=session.read(request(ids),current_snapshot_id=ids[1])
        assert reply['snapshot_id']==ids[0]and reply['current_source_snapshot_id']==ids[1]
        assert reply['selection']['slots'][-1]['capture_seq']==5
        assert reply['selection']['slots'][-1]['source_snapshot_id']==ids[1]
        assert [v['capture_seq']for v in reply['candidate_views']]==[1,2,3,4]
        assert reply['channels']['V']==[capture(n)['frame_uid']for n in range(1,5)]
        assert reply['read_only']is True
    finally:session.close()
    assert session.feature_cache.closed and session.feature_cache.bytes==0


def test_uniform_metadata_does_not_run_query_encoder(tmp_path):
    root,ids=recorded(tmp_path);encoder=Encoder();session=MemoryRetrievalSession(root,EP,'session',encoder,VOCAB)
    try:
        reply=session.read(request(ids,'uniform_tagged'),current_snapshot_id=ids[1])
        assert encoder.model_batches==0 and len(reply['uniform_views'])==5
        assert reply['selection']is None
    finally:session.close()


def test_wrong_session_future_current_and_released_session_fail_closed(tmp_path):
    root,ids=recorded(tmp_path);session=MemoryRetrievalSession(root,EP,'session',Encoder(),VOCAB)
    bad=request(ids);bad['episode_instance']='another'
    with pytest.raises(IntegrityError):session.read(bad,current_snapshot_id=ids[1])
    with pytest.raises(IntegrityError):session.read(request(ids),current_snapshot_id=ids[0])
    session.close()
    with pytest.raises(RuntimeError):session.read(request(ids),current_snapshot_id=ids[1])


def test_current_materialization_verifies_separate_newer_source_without_advancing_history(tmp_path):
    from dataclasses import replace
    from graphAdapter.map_memory.retrieval.contracts import ViewRef,Selection,EvidenceBundle
    from graphAdapter.map_memory.retrieval.host_input_compiler import materialize_history
    from graphAdapter.map_memory.retrieval.tests.test_host_input_compiler import native_sampler
    root,ids=recorded(tmp_path);session=MemoryRetrievalSession(root,EP,'session',Encoder(),VOCAB)
    try:
        response=session.read(request(ids),current_snapshot_id=ids[1]);raw=response['selection']
        def view(row):
            value=dict(row);value['entity_refs']=tuple(tuple(x)for x in value['entity_refs'])
            value['position']=None if value['position']is None else tuple(value['position'])
            return ViewRef(**value)
        slots=tuple(view(v)for v in raw['slots'])
        selection=Selection(slots,(),tuple(raw['protected_recent']),(),None,raw['budget'])
        reader=load_episode(root,revision=ids[0])
        try:
            current_rgb=np.full((8,8,3),5,np.uint8)
            materials=materialize_history(selection,reader,current_rgb,current=slots[-1],sampler=native_sampler(),width=8,height=8)
            assert reader.snapshot_id==ids[0]
            for bad in (replace(slots[-1],position=(999.,0.,0.)),replace(slots[-1],pose_map_version=True),
                        replace(slots[-1],event_seq=1000)):
                with pytest.raises(IntegrityError,match='Current geometry or clock'):
                    materialize_history(replace(selection,slots=slots[:-1]+(bad,)),reader,current_rgb,current=bad,
                                        sampler=native_sampler(),width=8,height=8)
            assert materials.slots[-1].source_snapshot_id==ids[1]
            assert materials.slots[-1].raw_pixel_hash is not None
            with pytest.raises(IntegrityError):materialize_history(selection,reader,np.full((8,8,3),99,np.uint8),current=slots[-1],sampler=native_sampler(),width=8,height=8)
        finally:reader.close()
    finally:session.close()


def test_grounded_policy_selects_real_label_and_abstains_on_unsupported_surface(tmp_path):
    from dataclasses import replace
    from types import SimpleNamespace
    from graphAdapter.map_memory.retrieval.host_input_compiler import grounded_fact_lines
    root,ids=recorded(tmp_path)
    session=MemoryRetrievalSession(root,EP,'session',Encoder(),VOCAB,evidence_policy='instruction_grounded')
    try:
        req=request(ids,mode='graph_image_facts')
        reply=session.read(req,current_snapshot_id=ids[1]);labels=reply['instruction_detections'];assert labels
        fact=labels[0];reader=load_episode(root,revision=ids[0]);slot=SimpleNamespace(index=2,frame_uid=fact['frame_uid'],is_current=False)
        hist=SimpleNamespace(snapshot_id=ids[0],slots=(slot,))
        try:
            facts=grounded_fact_lines(hist,labels,reader,VOCAB)
            assert facts[0].render()=='Image 2: possible door in this historical view.'
            with pytest.raises(IntegrityError):grounded_fact_lines(hist,[dict(fact,label='chair')],reader,VOCAB)
        finally:reader.close()
        req['query']['instruction']='Follow the wooden floor around the bend.'
        reply=session.read(req,current_snapshot_id=ids[1]);assert reply['channels']['Q']
        assert reply['selection']['fallback_reason']=='no_instruction_grounded_seed'
        assert not reply['selection']['slots'] and not reply['instruction_detections']
    finally:session.close()



def test_absent_approach_validates_current_but_never_loads_whole_visual_history(tmp_path,monkeypatch):
    from graphAdapter.map_memory.retrieval import semantic_topology
    from graphAdapter.map_memory.storage.store import SnapshotReader
    root,ids=recorded(tmp_path)
    req=request(ids,mode="native_plus_attachment")
    req["query"].update(instruction="Exit the bedroom.",last_reasoning="The next plan is to exit the bedroom.",
                        last_reasoning_event_seq=39,decision_event_seq=45)
    reads=[]
    old=SnapshotReader.get_retrieval_view
    def observe(reader,uid):
        reads.append(uid)
        return old(reader,uid)
    monkeypatch.setattr(SnapshotReader,"get_retrieval_view",observe)
    def absent(reader,seq,room):
        assert room=="bedroom" and reader.snapshot_id==ids[0] and seq==5
        return None
    monkeypatch.setattr(semantic_topology,"historical_approach",absent)
    session=MemoryRetrievalSession(root,EP,"session",Encoder(),VOCAB,evidence_policy="historical_approach")
    try:
        reply=session.read(req,current_snapshot_id=ids[1])
        assert reads==[capture(5)["frame_uid"]]
        assert reply["unavailable_reason"]=="no_connected_approach" and "uniform_views" not in reply
        assert reply["snapshot_id"]==ids[0] and reply["current_source_snapshot_id"]==ids[1]
    finally:session.close()

def test_compact_native_contract_pins_only_sampled_views(tmp_path,monkeypatch):
    from graphAdapter.map_memory.retrieval.host_decision import _native_reply_slots
    from graphAdapter.map_memory.storage.store import SnapshotReader
    root,ids=recorded(tmp_path)
    session=MemoryRetrievalSession(root,EP,'session',Encoder(),VOCAB)
    try:
        req=request(ids,'uniform_original')
        req['budget']=3
        legacy=session.read(req,current_snapshot_id=ids[1])
        req['protocol_version']=2
        fetched=[]
        original=SnapshotReader.get_retrieval_view
        def read(view,uid):
            fetched.append(uid)
            return original(view,uid)
        monkeypatch.setattr(SnapshotReader,'get_retrieval_view',read)
        reply=session.read(req,current_snapshot_id=ids[1])
        chosen,slot_ids=_native_reply_slots(reply,req['query'],5,3)
        assert reply['native_views']==[legacy['uniform_views'][i] for i in (0,2,4)]
        assert len(fetched)==3 and [v.capture_seq for v in chosen]==[1,3,5]
        assert chosen[-1].source_snapshot_id==ids[1] and chosen[0].source_snapshot_id==ids[0]
        assert slot_ids==tuple(capture(s)['frame_uid'] for s in [1,3,5])
        with pytest.raises(IntegrityError):
            _native_reply_slots(dict(reply,native_views=list(reversed(reply['native_views']))),req['query'],5,3)
        req['budget']=8
        padded=session.read(req,current_snapshot_id=ids[1])
        _,slots=_native_reply_slots(padded,req['query'],5,8)
        assert slots[:3]==(None,None,None) and slots[3:]==tuple(capture(i)['frame_uid'] for i in range(1,6))

        def missing(view,uid):
            if uid==capture(3)['frame_uid']:return None
            return original(view,uid)
        monkeypatch.setattr(SnapshotReader,'get_retrieval_view',missing)
        rejected=session.read(req,current_snapshot_id=ids[1])
        assert rejected['unavailable_reason']=='native_sample_unavailable' and 'native_views' not in rejected
    finally:session.close()

def test_v3_geometry_stays_in_reader_and_replies_cannot_cross_decisions(tmp_path):
    from graphAdapter.map_memory.retrieval.protocol import FrozenMemoryRead
    root,ids=recorded(tmp_path);sess=MemoryRetrievalSession(root,EP,'session',Encoder(),VOCAB)
    msg=request(ids,'uniform_original');msg['protocol_version']=3
    q=msg['query'];q.pop('current_position');q.pop('pose_map_version')
    q.update(decision_id=2,decision_event_seq=52,last_reasoning='Find the door.',last_reasoning_event_seq=51)
    try:
        wire=FrozenMemoryRead.create(msg);reply=sess.read(msg,current_snapshot_id=ids[1])
        assert wire.validate_reply(reply)['decision_id']==2
        assert reply['native_views'][-1]['position'] is not None
        for override in [dict(decision_id=1),dict(decision_event_seq=50),dict(read_only=1),dict(current_capture_seq=True)]:
            with pytest.raises(ValueError):wire.validate_reply(dict(reply,**override))
        for override in [dict(current_position=[1,2,3]),dict(current_position=None),dict(pose_map_version=0),
                         dict(last_reasoning={'goal':'fixture'}),dict(last_reasoning_event_seq=52),
                         dict(last_reasoning=None,last_reasoning_event_seq=51),dict(decision_id=True)]:
            with pytest.raises(ValueError):FrozenMemoryRead.create(dict(msg,query=dict(q,**override)))
    finally:sess.close()


def test_reasoning_is_bound_to_text_generation_frame_and_episode_instance():
    from graphAdapter.map_memory.retrieval.host_decision import HostInjection,check_delivered_reasoning
    from types import SimpleNamespace as NS
    events=[]
    def emit(kind,**kw):
        events.append((kind,kw));return {'event_seq':20+len(events)}
    packet=NS(frame_uid='ep:0',episode_uid='ep',pose_record={'episode_instance':'one'})
    hook=NS(latest_packet=packet,coordinator=NS(decision_id=1))
    dec=NS(hook=hook,event={'frame_uid':'ep:0','decision_id':1},emit=emit,history=None)
    api=HostInjection(dec,[],8,lambda *args,**kw:[])
    with pytest.raises(IntegrityError):api.record_reasoning(2,'A')
    msg='Look left.'
    event=api.record_reasoning(1,msg);check_delivered_reasoning(hook,packet,msg,event)
    import hashlib
    assert events[-1][1]['reasoning_sha256']==hashlib.sha256(msg.encode()).hexdigest()
    with pytest.raises(IntegrityError):api.record_reasoning(1,msg)
    for text,when in [('Other',event),(msg,event+1),('',None)]:
        with pytest.raises(IntegrityError):check_delivered_reasoning(hook,packet,text,when)
    packet.pose_record['episode_instance']='two'
    with pytest.raises(IntegrityError):check_delivered_reasoning(hook,packet,msg,event)
    check_delivered_reasoning(hook,packet,None,None)

def test_repeat_read_scores_are_session_scoped_and_still_verify_blob_on_hit(tmp_path):
    root,pins=recorded(tmp_path)
    matrix=Encoder().encode(MemoryQuery(EP,pins[0],capture(5)['frame_uid'],5,4,40,'Pass the door.')).windows
    class FixedEncoder(Encoder):
        def encode(self,q):
            return EncodedQuery(q.instruction_hash,digest(canonical(MODEL)),'t',matrix)
    session=MemoryRetrievalSession(root,EP,'session',FixedEncoder(),VOCAB)
    try:
        req=request(pins)
        one=session.read(req,current_snapshot_id=pins[1])
        two=session.read(req,current_snapshot_id=pins[1])
        assert one['selection']==two['selection'] and one['channels']==two['channels']
        before=one['semantic_score_cache'];after=two['semantic_score_cache']
        assert after['instruction_misses']==before['instruction_misses']
        assert after['instruction_hits']-before['instruction_hits']==4
        from contextlib import closing
        with closing(load_episode(root,revision=pins[0])) as reader:
            ref=reader.get_view_feature_reference(capture(1)['frame_uid'])['source_ref']
        path=root/ref['path'];payload=path.read_bytes();path.write_bytes(bytes([payload[0]^1])+payload[1:])
        with pytest.raises(IntegrityError,match='checksum'):session.read(req,current_snapshot_id=pins[1])
    finally:session.close()
    assert not session.instruction_scores.rows and session.instruction_scores.embedding is None
