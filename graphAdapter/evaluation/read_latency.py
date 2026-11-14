"""Audit host monotonic read times separately from native model execution."""
from .retrieval_audit_utils import index


def audit_read_latency(flow):
    ready = index(flow, 'HostReadInputReady', 'request_id')
    if not ready:
        return {'status': 'host_input_timing_not_recorded'}
    requests = index(flow, 'MemoryReadRequested', 'request_id')
    waited = index(flow, 'MemoryReadTiming', 'request_id')
    models = index(flow, 'HostModelInterval', 'call_id')
    material = index(flow, 'HostInputAudit', 'request_id')
    fallbacks = index([r for r in flow if r.get('request_id')], 'MemoryReadFallback', 'request_id')
    if ready.keys() != requests.keys() or not waited.keys() <= requests.keys():
        raise ValueError('Host input timing coverage differs from read requests')
    terminals=index(flow,'MemoryExpiredReadFinished','request_id')
    expected={rid for rid,t in waited.items() if t.get('expired_read') is True}
    if terminals.keys()!=expected:
        raise ValueError('Missing or unexpected expired-read terminal receipt')
    for rid,t in terminals.items():
        timing=waited[rid];request=requests[rid]
        if (rid not in fallbacks or rid in material or t['event_seq']<=request['event_seq']
                or any(t[k]!=request[k] for k in ('decision_id','frame_uid','episode_uid','snapshot_id'))
                or t['submitted_ns']!=timing['submitted_ns'] or t['started_ns']!=timing['started_ns']
                or type(t['terminal_ns']) is not int or t['terminal_ns']<t['submitted_ns']):
            raise ValueError('Expired read terminal belongs to another request or was consumed')
        if t['outcome']=='cancelled_before_start':
            if (not timing['cancelled'] or t['started_ns'] is not None or t['finished_ns'] is not None
                    or t['error_type'] is not None):
                raise ValueError('Cancelled read claimed worker execution')
        elif (t['outcome'] not in ('late_reply','late_error','transport_failure') or timing['cancelled']
                or type(t['started_ns']) is not int or t['finished_ns']!=t['terminal_ns']
                or not t['submitted_ns']<=t['started_ns']<=t['terminal_ns']
                or ((t['error_type'] is None)!=(t['outcome']=='late_reply'))):
            raise ValueError('Invalid expired worker outcome or clock')
    max_elapsed = None
    late = []
    late_backend = []
    for rid, end in ready.items():
        request = requests[rid]
        call = end['call_id']
        model = models[call]
        accepted = rid in material
        if (type(end['used_memory']) is not bool or end['used_memory'] != accepted
                or accepted == (rid in fallbacks) or end['decision_id'] != call
                or model['frame_uid'] != end['frame_uid']
                or any(end[k] != request[k] for k in ('decision_id','frame_uid','episode_uid'))):
            raise ValueError('Host input timing belongs to another decision or material path')
        chosen = material[rid] if accepted else fallbacks[rid]
        stamps = [end[k] for k in ('materialized_ns','compiled_ns','preprocessed_ns','ready_ns')]
        stamps.append(model['started_monotonic_ns'])
        if not request['event_seq'] < chosen['event_seq'] < end['event_seq'] < model['event_seq']:
            raise ValueError('Host readiness event order is invalid')
        if rid in waited:
            t = waited[rid]
            if (any(t[k] != request[k] for k in ('decision_id','frame_uid','episode_uid','snapshot_id'))
                    or not request['event_seq'] < t['event_seq'] < chosen['event_seq']):
                raise ValueError('Backend timing belongs to another request')
            stamps = [t['decision_started_ns'],t['submitted_ns'],t['observed_ns']] + stamps
            if type(t['deadline_ns']) is not int or t['deadline_ns'] <= stamps[0]:
                raise ValueError('Invalid configured read deadline')
            elapsed = (end['ready_ns']-stamps[0])/1e9
            max_elapsed = elapsed if max_elapsed is None else max(max_elapsed,elapsed)
            if end['ready_ns'] > t['deadline_ns']:late.append(call)
            if t['observed_ns'] > t['deadline_ns']:late_backend.append(call)
        if any(type(n) is not int for n in stamps) or stamps != sorted(stamps):
            raise ValueError('Read, compile, preprocess and model clocks are out of order')
    return dict(status='verified',requested=len(requests),host_input_ready=len(ready),timed_backend=len(waited),
                above_backend_budget_at_reply=sorted(late_backend),above_backend_budget_at_host_input=sorted(late),
                max_decision_to_host_input_s=max_elapsed,expired_terminal_receipts=len(terminals))
