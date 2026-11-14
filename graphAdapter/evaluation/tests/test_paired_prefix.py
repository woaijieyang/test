from copy import deepcopy
import pytest
from graphAdapter.evaluation.paired_prefix import compare_paired_prefix,PairEvidenceError


def trace(reason=False):
    def state(n):
        return dict(position=[0.,0.,0.],rotation_xyzw=[0.,0.,0.,1.],elapsed_steps=n,
                    episode_over=False,collided=False,endpoint_sensor=dict(rgb_sha256='a'*64,depth_sha256='b'*64))
    def call(k,mode):
        return dict(kind='model_call',frame=0,call_id=k,normalized_output=mode,output_ids=[[k]],prompt='go',
                    input_ids=[[0]],images=[{'pixel_sha256':'a'*64}],processed_image_shape=[1,3,4,4],
                    processed_image_sha256='c'*64,generation={'max_new_tokens':256},stop_str='end',sep2='end')
    calls=([call(1,'<BEGIN_OF_REASONING> look')] if reason else [])
    calls.append(call(len(calls)+1,'<BEGIN_OF_ACTION> stop'))
    return [dict(kind='reset',state_evaluator_only=state(0)),*calls,dict(kind='primitive_action',step=1,
            before_evaluator_only=state(0),after_evaluator_only=state(1),action=0,last_call_id=len(calls),stop_source='model'),
            dict(kind='terminal',steps=1,termination_reason='stop',stop_source='model')]


def fallback(n):
    return [dict(kind='MemoryReadFallback',decision_id=k,env_step=0,reason='test')for k in range(1,n+1)]


def test_different_depth_or_after_state_rejects_same_action_claim():
    a=trace();b=deepcopy(a)
    b[-2]['after_evaluator_only']['endpoint_sensor']['depth_sha256']='e'*64
    with pytest.raises(PairEvidenceError,match='depth_sha256'):compare_paired_prefix(a,b,fallback(1))
    b=deepcopy(a);b[-2]['before_evaluator_only']['collided']=True
    with pytest.raises(PairEvidenceError,match='continuity'):compare_paired_prefix(a,b,fallback(1))


def test_two_decisions_in_one_frame_and_missing_return_can_be_distinguished():
    a=trace();b=trace(True)
    b[1]['output_ids']=[[3]]
    out=compare_paired_prefix(a,b,fallback(2))
    assert out['first_call_count_change']==dict(frame=0,original_calls=[1],candidate_calls=[1,2])
    assert out['first_output']['parsed'][1]['mode']=='reason' and out['first_execution'] is None
    with pytest.raises(PairEvidenceError,match='each model call'):compare_paired_prefix(a,b,fallback(1))

def test_identical_actions_can_end_at_different_lengths_without_claiming_a_new_turn():
    a=trace()
    a[1]=dict(a[1],normalized_output='<BEGIN_OF_ACTION> move forward 50 cm')
    a[-2]=dict(a[-2],action=1,stop_source=None)
    a[-1]=dict(a[-1],termination_reason='max_steps',stop_source=None)
    b=deepcopy(a)
    s=deepcopy(b[-2]);s.update(step=2)
    s['before_evaluator_only']=deepcopy(b[-2]['after_evaluator_only'])
    s['after_evaluator_only']['elapsed_steps']=2
    b.insert(-1,s);b[-1]['steps']=2
    report=compare_paired_prefix(a,b,fallback(1))
    assert report['equal_action_prefix']==1
    assert report['first_execution']==dict(step=2,kind='one_trajectory_ended',actions=[None,1])
