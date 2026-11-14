"""Summarize recorded host behavior, preserving reasoning/forced-stop semantics."""
from collections import Counter
import re

PATTERNS=(r'\bstop\b','move forward','turn left','turn right')

def primitive_count(action,output):
    """Mirror the frozen host's magnitude extraction, rounding and one initial primitive."""
    if action==0:return 1
    unit=25 if action==1 else 15
    phrase={1:"move forward",2:"turn left",3:"turn right"}[action]
    suffix="cm" if action==1 else "degree"
    match=re.search(phrase+r" (\d+) "+suffix,output)
    try:
        amount=int(match.group(1)) if match else unit
    except ValueError:
        amount=unit
    if amount%unit:amount=min((unit,2*unit,3*unit),key=lambda value:abs(value-amount))
    return max(1,amount//unit)


def parse_host_output(output):
    """Mirror original priority; retain all matched action types in textual order for auditing."""
    if output.startswith('<BEGIN_OF_REASONING>'):
        return dict(mode='reason',matched_in_text=[],selected_action=None,primitive_count=0)
    acting=output.startswith('<BEGIN_OF_ACTION>')
    content=output[len('<BEGIN_OF_ACTION>'):].strip() if acting else output
    hits=[]
    for action,pattern in enumerate(PATTERNS):
        match=re.search(pattern,content,re.I)
        if match is not None:hits.append((match.start(),action))
    actions=[action for _,action in sorted(hits)]
    selected=min(actions) if actions else 1
    return dict(mode='act' if acting else 'unknown',matched_in_text=actions,
                selected_action=selected,primitive_count=primitive_count(selected,content))


def audit_reasoning_requests(trace,flow):
    """Recover native REASON text from completed model outputs and check each subsequent query clock."""
    import hashlib
    from .native_control_audit import _question_builder
    events=[r for r in flow if r['kind']=='MemoryReasoningAvailable']
    requests=[r for r in flow if r['kind']=='MemoryReadRequested']
    if not any('reasoning_sha256' in r for r in events) and not any(r.get('protocol_version')==3 for r in requests):
        return dict(status='not_recorded')
    _,extract=_question_builder()
    model={r['call_id']:r for r in trace if r['kind']=='model_call'}
    decisions={r['decision_id']:r for r in flow if r['kind']=='decision'}
    expected={k for k,r in model.items() if r['normalized_output'].startswith('<BEGIN_OF_REASONING>')}
    seen=set();last=None;bound=0
    for row in flow:
        kind=row['kind']
        if kind=='MemoryReasoningAvailable':
            k=row['call_id'];dec=decisions[k];x=model[k]
            assert k in expected and k not in seen and row['decision_id']==k
            assert row['episode_uid']==dec['episode_uid'] and row['frame_uid']==dec['frame_uid'] and row['env_step']==x['frame']
            assert dec['event_seq']<row['event_seq']
            text=extract(x['normalized_output']);assert hashlib.sha256(text.encode()).hexdigest()==row['reasoning_sha256']
            last=row['event_seq'] if text.strip() else None
            seen.add(k)
        elif kind=='MemoryReadRequested':
            dec=decisions[row['decision_id']]
            assert row['protocol_version']==3 and row['decision_event_seq']==dec['event_seq']<row['event_seq']
            assert row['episode_uid']==dec['episode_uid'] and row['frame_uid']==dec['frame_uid']
            assert row['reasoning_event']==last and (last is None or last<dec['event_seq'])
            bound+=int(last is not None)
    assert seen==expected
    return dict(status='verified',native_reason_events=len(events),read_requests=len(requests),reason_bound_requests=bound)


def compare_decision_modes(original,candidate):
    """Compare the calls preceding each primitive while the executed action prefix matches."""
    def groups(trace):
        pending=[]
        for row in trace:
            if row['kind']=='model_call':
                text=row['normalized_output']
                mode=('reason' if text.startswith('<BEGIN_OF_REASONING>') else
                      'act' if text.startswith('<BEGIN_OF_ACTION>') else 'unknown')
                pending.append((row['frame'],row['call_id'],mode))
            elif row['kind']=='primitive_action':
                if any(frame!=row['step']-1 for frame,_,_ in pending):
                    raise ValueError('Generated decision and primitive refer to different frames')
                yield row,pending
                pending=[]
    examined=0;changes=[];first_action=None
    for (a,left),(b,right) in zip(groups(original),groups(candidate)):
        if a['step']!=b['step']:raise ValueError('Paired primitive ordinals differ')
        examined+=1
        if [v[2] for v in left]!=[v[2] for v in right]:
            changes.append(dict(frame=a['step']-1,original=[v[1:] for v in left],
                                candidate=[v[1:] for v in right],actions=[a['action'],b['action']]))
        if a['action']!=b['action']:
            first_action=a['step']
            break
    return dict(examined_primitives=examined,first_different_primitive=first_action,mode_changes=changes)


def summarize(rows):
    calls={}; measures=Counter(); streak=0; max_streak=0; steps=0; first={}; terminal=None
    last_call=None;remaining=0;ended=False
    for row in rows:
        kind=row['kind']
        if terminal is not None:raise ValueError('Events after terminal')
        if ended and kind!='terminal':raise ValueError('Event after environment terminated')
        if kind=='model_call':
            if remaining:raise ValueError('New model call before primitive queue was exhausted')
            key=row['call_id']
            if key in calls:raise ValueError('Duplicate model return')
            output=row['normalized_output']
            reasoning=output.startswith('<BEGIN_OF_REASONING>')
            acting=output.startswith('<BEGIN_OF_ACTION>')
            measures['unknown_mode']+=int(not acting and not reasoning)
            measures['reason_calls']+=int(reasoning)
            streak=streak+1 if reasoning else 0;max_streak=max(max_streak,streak)
            parsed=parse_host_output(output)
            matches=parsed['matched_in_text']
            if not reasoning and not matches:measures['parser_default_forward']+=1
            if len(matches)>1:measures['multiple_action_types']+=1
            if matches and matches[0]!=0 and parsed['selected_action']==0:
                measures['stop_after_other_action_text']+=1
            calls[key]=parsed['selected_action']
            last_call=key;remaining=parsed['primitive_count']
            ids=row['output_ids']
            if len(ids)!=1 or not isinstance(ids[0],list):raise ValueError('Missing single-batch generation IDs')
            # Reaching the configured limit is observable. The exact finish reason is not recorded.
            measures['output_id_count_at_least_budget']+=int(len(ids[0])>=row['generation']['max_new_tokens'])
        elif kind=='primitive_action':
            steps+=1
            if row['step']!=steps:raise ValueError('Nonconsecutive executed step')
            key=row['last_call_id']
            if key!=last_call or key not in calls:raise ValueError('Action not bound to most recent model return')
            ended=row.get('done') is True
            if row['stop_source']=='reason_stuck':
                if row['action']!=0 or calls[key] is not None or streak<4:raise ValueError('Invalid reason-stuck stop')
                measures['forced_reason_stop']+=1
            else:
                if calls[key]!=row['action']:raise ValueError('Executed action differs from recorded parser mode')
                if remaining<=0:raise ValueError('Execution exceeds parsed macro length')
                remaining-=1
                first[key]=True
                if row['action']==0 and row['stop_source']!='model':raise ValueError('Parsed STOP has inconsistent source')
        elif kind=='terminal':
            if row['steps']!=steps or row['model_calls']!=len(calls):raise ValueError('Terminal counts disagree')
            if remaining:
                if not ended or row.get('termination_reason')!='max_steps':
                    raise ValueError('Incomplete macro without recorded environment truncation')
                measures['terminal_cancelled_primitives']=remaining
            terminal=row
    if terminal is None:raise ValueError('Terminal missing')
    if any(parsed is not None and k not in first for k,parsed in calls.items()):raise ValueError('Action response without execution')
    return dict(model_calls=len(calls),steps=steps,max_reason_streak=max_streak,stop_source=terminal['stop_source'],
        **{k:measures[k] for k in ('reason_calls','unknown_mode','multiple_action_types','stop_after_other_action_text','parser_default_forward','forced_reason_stop','output_id_count_at_least_budget','terminal_cancelled_primitives')})

