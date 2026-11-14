import pytest
from types import SimpleNamespace
from graphAdapter.map_memory.storage.archive import IntegrityError
from graphAdapter.map_memory.retrieval.evidence import motion_after, requested_turns, fresh_records, delivery_key
from graphAdapter.map_memory.retrieval.evidence import ExtraRecord

def run(actions,cutoff):
    trace={}
    for i,(action,index,count,macro,collision,measured) in enumerate(actions,1):
        src,dst=str(i),str(i+1)
        edge=lambda kind:dict(src=src,dst=dst,type=kind,id=f'{kind}-{src}')
        trace[src]=dict(pre=src,post=dst,action=dict(action_id=action,primitive_index=index,primitive_count=count,macro_id=macro,collision=collision),
            motion=dict(temporal=edge('temporal_next'),traversed=edge('traversed') if measured else None))
    view=lambda uid:SimpleNamespace(frame_uid=uid,capture_seq=int(uid),env_step=int(uid)-1)
    return motion_after('1',trace,cutoff,view,{'right'})

def test_completed_turn_after_actual_forward_requires_all_endpoints():
    actions=[(1,1,1,2,False,True),(3,1,2,3,False,False),(3,2,2,3,False,False)]
    out=run(actions,4)
    assert out[0].frame_uid=='4' and out[1:] == ('right',('traversed-1','temporal_next-2','temporal_next-3'),3)
    assert run(actions,3) is None
    for broken in [[(1,1,1,2,False,False),*actions[1:]], [actions[0],(2,1,1,2,False,False),*actions[1:]],
                   [actions[0],actions[1],(3,2,2,4,False,False)], [actions[0],(3,2,2,3,False,False)]]:
        assert run(broken,6) is None

def test_side_of_object_does_not_imply_executed_turn():
    assert requested_turns('There are paintings on your left. Take a right.')=={'right'}

def test_adjacent_detections_of_same_landmark_and_turn_share_delivery_receipt():
    a=ExtraRecord('At step 3, the detector recorded a possible bed. A recorded right turn ended at step 7.',('detect3','edge','post'),(3,7))
    b=ExtraRecord(a.text.replace('step 3','step 4'),('detect4','edge','post'),(4,7))
    assert fresh_records((a,b),set())==(a,)
    assert fresh_records((b,),{delivery_key(a)})==()

