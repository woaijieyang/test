import pytest
from graphAdapter.evaluation.read_latency import audit_read_latency


def fixture():
    identity=dict(episode_uid='ep',frame_uid='f',decision_id=3,request_id='req')
    return [dict(identity,kind='MemoryReadRequested',event_seq=10,snapshot_id='map'),
            dict(identity,kind='MemoryReadTiming',event_seq=11,snapshot_id='map',decision_started_ns=10,
                 submitted_ns=11,observed_ns=23,deadline_ns=26),
            dict(identity,kind='MemoryReadFallback',event_seq=12),
            dict(identity,kind='HostReadInputReady',event_seq=13,call_id=3,materialized_ns=25,
                 compiled_ns=26,preprocessed_ns=28,ready_ns=30,used_memory=False),
            dict(identity,kind='HostModelInterval',event_seq=14,call_id=3,started_monotonic_ns=32)]


def test_on_time_backend_can_have_late_host_input():
    out=audit_read_latency(fixture())
    assert out['above_backend_budget_at_reply']==[] and out['above_backend_budget_at_host_input']==[3]
    assert audit_read_latency([])['status']=='host_input_timing_not_recorded'


@pytest.mark.parametrize('row,field,value',[(3,'decision_id',4),(3,'episode_uid','wrong'),
    (1,'snapshot_id','another'),(3,'used_memory',True),(3,'preprocessed_ns',24),(4,'started_monotonic_ns',29)])
def test_reject_inconsistent_host_latency(row,field,value):
    data=fixture();data[row][field]=value
    with pytest.raises(ValueError):audit_read_latency(data)


@pytest.mark.parametrize('fault',['missing','duplicate','wrong_request','wrong_frame','wrong_pin','before_start','false_error'])
def test_expired_read_terminal_is_unique_bound_and_diagnostic_only(fault):
    flow=fixture()
    flow[1].update(expired_read=True,started_ns=17,cancelled=False,deadline_ns=22)
    end=dict(flow[0],kind='MemoryExpiredReadFinished',event_seq=15,outcome='late_reply',
             submitted_ns=11,started_ns=17,finished_ns=35,terminal_ns=35,error_type=None)
    flow.append(end)
    assert audit_read_latency(flow)['expired_terminal_receipts']==1
    if fault=='missing':flow.pop()
    elif fault=='duplicate':flow.append(dict(end))
    elif fault=='wrong_request':end['request_id']='next'
    elif fault=='wrong_frame':end['frame_uid']='other'
    elif fault=='wrong_pin':end['snapshot_id']='other'
    elif fault=='before_start':end.update(finished_ns=16,terminal_ns=16)
    else:end['error_type']='ValueError'
    with pytest.raises(ValueError):audit_read_latency(flow)
