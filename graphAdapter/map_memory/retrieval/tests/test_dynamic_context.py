from types import SimpleNamespace as NS
from dataclasses import replace
import pytest
from graphAdapter.map_memory.retrieval.dynamic_context import build_window,WindowCursor
from graphAdapter.map_memory.storage.archive import IntegrityError
from graphAdapter.map_memory.retrieval.tests.test_bundles_selector import view

class Reader:
    snapshot_id='snap'
    identity={'episode_uid':'ep'}
    versions={'pose_map_version':0}
    def __init__(self,cap):
        self.cutoff={'capture_seq':cap}
    def get_retrieval_view(self,uid):
        n=int(uid[1:])
        return replace(view(n),position=(.25*n,0,0)) if n<=self.cutoff['capture_seq'] else None
    def get_trace(self,start,end):
        result=[]
        for i in range(start,end+1):
            src,dst=f'f{i-1}',f'f{i}'
            edge=lambda kind:dict(id=f'{kind}{i}',src=src,dst=dst,type=kind)
            moving=i%3!=0
            result.append(dict(pre=src,post=dst,action=dict(action_id=1 if moving else 2,collision=False),
                motion=dict(temporal=edge('temporal_next'),traversed=dict(edge('traversed'),estimated_translation_m=.25) if moving else None)))
        return result

def test_source_receipts_are_scoped_to_episode_instance_and_native_reasoning():
    from graphAdapter.map_memory.retrieval.dynamic_context import LandmarkDelivery
    source=('frame_1:det1',)
    delivery=LandmarkDelivery.for_decision(None,'ep','first',None)
    delivery.sources.add(source)
    assert LandmarkDelivery.for_decision(delivery,'ep','first',None) is delivery
    for scope in [('ep','first',17),('ep','retry',None),('other','first',None)]:
        assert source not in LandmarkDelivery.for_decision(delivery,*scope).sources


def test_changed_frontier_same_frame_and_session_reset():
    cur=WindowCursor()
    assert cur.bind('ep','instance','f4','a',3)==0
    assert cur.bind('ep','instance','f4','a',3)==0
    assert cur.bind('ep','instance','f4','b',4)==0
    assert cur.bind('ep','instance','f7','c',6)==4
    with pytest.raises(IntegrityError):cur.bind('ep','instance','f8','z',3)
    assert cur.bind('ep','new','f1','d',1)==0

def test_path_position_and_removal_are_fresh_at_each_cutoff():
    r=Reader(6);current=replace(view(7),position=(1.5,0.,0.),source_snapshot_id='live7')
    attach=NS(slot=NS(frame_uid='f2'))
    first=build_window(r,current,3,attach)
    assert first.fields['recent_path']==dict(from_step=2,to_step=5,recorded_forward_m=.5,executed_turn_primitives=['left'])
    assert first.fields['distance_to_historical_camera_m_estimate']==1.
    assert first.provenance['current_source_snapshot']=='live7'
    stale=build_window(r,replace(current,pose_map_version=8),3,attach)
    assert 'distance_to_historical_camera_m_estimate' not in stale.fields
    next_record=build_window(Reader(7),replace(view(8),position=(2,0,0)),6,None)
    assert next_record.fields['recent_path']['from_step']==5 and 'anchor' not in next_record.provenance
    with pytest.raises(IntegrityError):build_window(r,replace(current,episode_uid='other'),3,attach)
    with pytest.raises(IntegrityError):build_window(r,current,3,NS(slot=NS(frame_uid='f9')))



@pytest.mark.parametrize('path_available',[False,True])
def test_budget_eviction_removes_dependent_distance_and_keeps_native_video(monkeypatch,path_available):
    import numpy as np
    from graphAdapter.map_memory.retrieval import host_decision as host
    from graphAdapter.map_memory.retrieval.dynamic_context import ContextWindow
    monkeypatch.setattr(host,'vision_budget',lambda model:(196,4096))
    decision=host.HostDecision(None,{},'native_plus_attachment',
        {'evidence_policy':'dynamic_evo_context','max_fact_tokens':64})
    decision.history=NS(budget=8,snapshot_id='snap');decision.attachment=NS(slot=NS(frame_uid='old'))
    decision.evidence_card=NS(fields=lambda:{'instruction_landmark':'bed'})
    fields={'as_of_step':9,'distance_to_historical_camera_m_estimate':1.5}
    if path_available:fields['recent_path']={'from_step':6,'to_step':8,'recorded_forward_m':0.5}
    decision.window=ContextWindow(fields,{'anchor':'old','cutoff':9})
    events=[];decision.emit=lambda kind,**kw:events.append((kind,kw))
    # Original native context fits; supplementary image record exceeds text allocation.
    tokenizer=NS(encode=lambda text,**kw:list(range(65 if 'historical_landmark' in text else 12)))
    out=decision.compile('original question',lambda q:q,tokenizer,lambda _:np.arange(10),None)
    assert decision.combined is None and 'distance_to_historical_camera_m_estimate' not in out and '<image>' not in out
    if path_available:
        assert 'recent_path' in out and events[-1][1]['attachment_slots']==0 and 'anchor' not in events[-1][1]['source']
    else:assert out=='original question' and events[-1][0]=='MemoryReadFallback'


@pytest.mark.parametrize('admission,collisions,expected',[
    ('landmark_or_collision',0,False),('landmark_or_collision',1,True),('native_plan_photo',1,False)])
def test_only_inject_materialized_collision_or_landmark(monkeypatch,admission,collisions,expected):
    import numpy as np
    from graphAdapter.map_memory.retrieval import host_decision as host
    from graphAdapter.map_memory.retrieval.dynamic_context import ContextWindow
    monkeypatch.setattr(host,'vision_budget',lambda model:(196,4096))
    settings=dict(evidence_policy='dynamic_evo_context',max_fact_tokens=192,context_admission=admission)
    d=host.HostDecision(None,{},'native_plus_attachment',settings)
    d.history=NS(budget=8,snapshot_id='pinned');events=[]
    d.emit=lambda kind,**kwargs:events.append(kind)
    path={'from_step':12,'to_step':15,'recorded_forward_m':.5}
    if collisions:path['recorded_collisions']=collisions
    d.window=ContextWindow({'as_of_step':16,'recent_path':path},{'edges':['e']})
    prompt=d.compile('original',lambda q:q,NS(encode=lambda text,**kw:[0]*16),lambda _:np.arange(64),None)
    assert ('Graph memory for this decision' in prompt)==expected
    assert events==(['DynamicContextCompiled'] if expected else ['MemoryReadFallback'])
    if not expected:assert d.history is None and prompt=='original'



def test_depth_change_withholds_invalid_rays_and_binds_forward_motion():
    import numpy as np
    from graphAdapter.map_memory.retrieval.dynamic_context import side_depth_change
    def frame(n):
        T=np.eye(4);T[2,3]=n*.25
        packet=dict(episode_uid="ep",capture_seq=n+1,env_step=n,calibration_hash="c",
                    action=dict(action_id=1,collision=False),K=[[16,0,15.5],[0,16,15.5],[0,0,1]],
                    pose_record=dict(source="simulator_ground_truth",episode_instance="i",valid=True,map_version=0,T_map_camera_cv=T))
        return dict(packet=packet,depth=np.ones((32,32)),valid=np.ones((32,32),bool))
    a,b=frame(0),frame(1);b["depth"][:,26:30]=4
    read=lambda:side_depth_change(a,b,voxel_size_m=.1)
    assert read()["optical_depth_m"]=={"right":[1.0,4.0]}
    b["valid"][:,26:30]=False
    assert read() is None
    b["valid"][:]=True;b["packet"]["action"]["collision"]=True
    assert read() is None
    b["packet"]["action"]["collision"]=False;b["packet"]["pose_record"]["episode_instance"]="other"
    assert read() is None
    b["packet"]["capture_seq"]=4
    with pytest.raises(IntegrityError):read()

def test_object_delivery_distinguishes_epoch_source_class_and_reasoning():
    from graphAdapter.map_memory.retrieval.dynamic_context import LandmarkDelivery
    first=LandmarkDelivery.for_decision(None,'ep','instance',9)
    def key(member,epoch='a',label='couch'):
        return first.evidence_key('object_once_per_reasoning',(member,),dict(epoch=epoch,object_id=19,member=member),label)
    first.sources.add(key('old:d00001'))
    assert key('new:d00000') in first.sources
    assert key('new:d00000',epoch='b') not in first.sources
    assert key('new:d00000',label='chair') not in first.sources
    assert key('new:d00000') not in LandmarkDelivery.for_decision(first,'ep','instance',10).sources
