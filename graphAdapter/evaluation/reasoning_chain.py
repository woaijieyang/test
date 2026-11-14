"""Follow actual memory-bearing generations through native same-frame calls to the first executor event."""
from .native_control_audit import _question_builder
from .retrieval_audit_utils import index
from .retrieval_behavior import parse_host_output


def audit_material_chains(trace,flow):
    calls=index(trace,'model_call','call_id')
    audited=index(flow,'HostInputAudit','call_id')
    returned=index(flow,'MemoryGenerateReturned','call_id')
    decisions=index(flow,'decision','decision_id')
    reasons=index(flow,'MemoryReasoningAvailable','call_id')
    if audited.keys()!=returned.keys() or not audited.keys()<=calls.keys():
        raise ValueError('Incomplete generate return for memory-bearing input')
    _,extract=_question_builder()
    # Each contiguous run of model records is followed by its actual first primitive;
    # later queued primitives belong to the same macro and do not start new chains.
    groups=[]
    pending=[]
    for row in trace:
        if row['kind']=='model_call':
            pending.append(row)
        elif row['kind']=='primitive_action' and pending:
            groups.append((pending,row))
            pending=[]
    if pending:
        groups.append((pending,None))
    result=[]
    for group,executed in groups:
        for pos,call in enumerate(group):
            cid=call['call_id']
            if cid not in audited:continue
            audit=audited[cid];ret=returned[cid];dec=decisions[cid]
            if (not dec['event_seq']<audit['event_seq']<ret['event_seq'] or
                    any(ret[k]!=audit[k] for k in ('request_id','episode_uid','frame_uid','decision_id','snapshot_id'))
                    or dec['frame_uid']!=audit['frame_uid'] or dec['episode_uid']!=audit['episode_uid']
                    or dec['env_step']!=call['frame'] or audit['decision_id']!=cid):
                raise ValueError('Generated response is not bound to its memory input')
            chain=group[pos:]
            for prev,nxt in zip(chain,chain[1:]):
                pid=prev['call_id'];nid=nxt['call_id']
                text=prev['normalized_output']
                if not text.startswith('<BEGIN_OF_REASONING>') or nid!=pid+1 or prev['frame']!=nxt['frame']:
                    raise ValueError('Unexecuted same-frame predecessor differs from native REASON')
                reason=reasons[pid]
                if (reason['frame_uid']!=decisions[nid]['frame_uid'] or reason['episode_uid']!=decisions[nid]['episode_uid']
                        or not decisions[pid]['event_seq']<reason['event_seq']<decisions[nid]['event_seq']
                        or (pid in returned and reason['event_seq']<=returned[pid]['event_seq'])):
                    raise ValueError('Reasoning receipt crossed decision or observation')
                extracted=extract(text)
                if extracted and f'The reasoning from 0 steps ago was: "{extracted}". ' not in nxt['prompt']:
                    raise ValueError('Native next input did not carry its predecessor reasoning')
            mode=('reason' if call['normalized_output'].startswith('<BEGIN_OF_REASONING>') else
                  'act' if call['normalized_output'].startswith('<BEGIN_OF_ACTION>') else 'unrecognized')
            final=chain[-1]['call_id']
            if executed and executed['last_call_id']!=final:
                raise ValueError('Executed primitive did not follow the final call in the group')
            parsed=parse_host_output(chain[-1]['normalized_output'])
            if executed:
                if parsed['mode']=='reason':
                    if executed['stop_source']!='reason_stuck' or executed['action']!=0:
                        raise ValueError('Native REASON unexpectedly produced a primitive')
                elif parsed['selected_action']!=executed['action']:
                    raise ValueError('Native action parser and first executed primitive differ')
            result.append(dict(call=cid,frame=call['frame'],request=audit['request_id'],snapshot=audit['snapshot_id'],
                               first_mode=mode,final_parser=parsed,same_frame_followup_calls=[v['call_id'] for v in chain[1:]],
                               followups_with_memory=[v['call_id'] for v in chain[1:] if v['call_id'] in audited],
                               first_primitive=({k:executed[k] for k in ('step','last_call_id','action','done','stop_source')} if executed else None)))
    return result
