import pytest
from graphAdapter.evaluation.retrieval_behavior import summarize

def response(i,text):
    return dict(kind='model_call',call_id=i,normalized_output=text,output_ids=[[1,2,3]],generation={'max_new_tokens':256})
def action(i,k,a,source=None):return dict(kind='primitive_action',step=i,last_call_id=k,action=a,stop_source=source)
def end(n,k):return dict(kind='terminal',model_calls=k,steps=n,stop_source='model')
def test_unknown_response_and_execution_are_counted_separately():
    events=[response(1,'unrecognized'),action(1,1,1),response(2,'<BEGIN_OF_ACTION> STOP'),action(2,2,0,'model'),end(2,2)]
    v=summarize(events);assert v['unknown_mode']==v['parser_default_forward']==1
    events[1]['action']=2
    with pytest.raises(ValueError):summarize(events)
def test_forced_stop_after_reasoning_is_not_action_parser_failure():
    events=[response(i,'<BEGIN_OF_REASONING> turn right or stop?') for i in range(1,5)]
    result=summarize(events+[action(1,4,0,'reason_stuck'),dict(end(1,4),stop_source='reason_stuck')])
    assert result['max_reason_streak']==4 and result['forced_reason_stop']==1 and result['parser_default_forward']==0
def test_terminal_loss_is_visible():
    with pytest.raises(ValueError):summarize([response(1,'<BEGIN_OF_ACTION> move forward'),action(1,1,1)])



def test_missing_pairs_remain_in_denominator_with_unavailable_delta():
    from graphAdapter.evaluation.retrieval_report import domain_summary
    records=[dict(status='verified',metrics={'success':[0,1]}),dict(status='incomplete')]
    result=domain_summary(records)
    assert result['registered']==2 and result['verified']==1
    assert result['candidate_success_lower_bound']==.5 and result['paired_delta_sr'] is None
    result=domain_summary(records[:1])
    assert result['paired_delta_sr']==1 and result['win']==1 and result['loss']==0



def test_declared_distance_and_turn_must_match_the_real_queue():
    events=[response(1,"<BEGIN_OF_ACTION> move forward 75 cm."),action(1,1,1),
            response(2,"<BEGIN_OF_ACTION> stop"),action(2,2,0,"model"),end(2,2)]
    with pytest.raises(ValueError,match="queue"):summarize(events)
    early=events[:2]+[dict(end(1,1),termination_reason="max_steps",stop_source=None)]
    with pytest.raises(ValueError,match="truncation"):summarize(early)
    early[1]=dict(early[1],done=True)
    assert summarize(early)["terminal_cancelled_primitives"]==2
    with pytest.raises(ValueError,match="exceeds"):
        summarize([response(1,"<BEGIN_OF_ACTION> turn right 15 degree."),action(1,1,3),action(2,1,3),end(2,1)])
    assert summarize([response(1,"<BEGIN_OF_ACTION> turn right 90 degree.")] +
                     [action(i,1,3) for i in range(1,7)]+[end(6,1)])["steps"]==6


def test_cannot_report_hook_on_as_true_control():
    from graphAdapter.evaluation.retrieval_report import verify_runtime_side
    manifest=dict(method="baseline")
    hook=dict(completed=True,requested_mode="off",profile_requested=False,hook_enabled=False,
              memory_broker_supplied=False,memory_worker_started=False,broker_supplied=False,
              native_initialization_attempts=0,reset_attempts=0,packet_count=0,memory_packet_count=0,hook_class=None)
    verify_runtime_side("control",manifest,hook)
    for field,value in dict(hook_enabled=True,requested_mode="on",memory_packet_count=1,native_initialization_attempts=1).items():
        with pytest.raises(ValueError):verify_runtime_side("control",manifest,dict(hook,**{field:value}))

def test_paired_modes_detect_skipped_reason_even_with_same_primitives():
    from graphAdapter.evaluation.retrieval_behavior import compare_decision_modes
    reason=dict(response(1,'<BEGIN_OF_REASONING>'),frame=0)
    move=dict(response(2,'<BEGIN_OF_ACTION> move forward 50 cm'),frame=0)
    left=[reason,move,action(1,2,1),action(2,2,1),dict(reason,call_id=3,frame=2),action(3,3,2)]
    right=[dict(move,call_id=1),action(1,1,1),action(2,1,3),dict(move,frame=2),action(3,2,1)]
    res=compare_decision_modes(left,right)
    assert res['examined_primitives']==res['first_different_primitive']==2
    assert res['mode_changes']==[dict(frame=0,original=[(1,'reason'),(2,'act')],candidate=[(1,'act')],actions=[1,1])]

def test_later_stop_in_a_plan_has_priority_only_on_action_path():
    from graphAdapter.evaluation.retrieval_behavior import parse_host_output
    content='The next plan is to turn right after the couch, then turn left after the table and stop in front of the stools.'
    parsed=parse_host_output('<BEGIN_OF_ACTION> '+content)
    assert parsed['matched_in_text']==[3,2,0] and parsed['selected_action']==0 and parsed['primitive_count']==1
    assert parse_host_output('<BEGIN_OF_REASONING> '+content)['selected_action'] is None
    rows=[response(1,'<BEGIN_OF_ACTION> '+content),action(1,1,0,'model'),end(1,1)]
    summary=summarize(rows)
    assert summary['multiple_action_types']==summary['stop_after_other_action_text']==1
