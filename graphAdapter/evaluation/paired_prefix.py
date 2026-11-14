"""Compare only a verified common trajectory prefix. Evaluator-only state never enters retrieval."""
import math
import re
from itertools import zip_longest

from .retrieval_behavior import parse_host_output


class PairEvidenceError(ValueError):
    """Keep the first broken physical-state or receipt binding visible in incomplete reports."""


def _same_state(left,right,step,phase):
    for key,size in (('position',3),('rotation_xyzw',4)):
        for state in (left,right):
            data=state[key]
            if len(data)!=size or not all(type(x) in (int,float) and math.isfinite(x) for x in data):
                raise PairEvidenceError(f'Invalid {key} at step {step}, {phase}')
    for state in (left,right):
        if type(state['elapsed_steps']) is not int or state['elapsed_steps']!=step:
            raise PairEvidenceError(f'Wrong elapsed_steps at step {step}, {phase}')
        for k in ('collided','episode_over'):
            if type(state[k]) is not bool:raise PairEvidenceError(f'Invalid {k} at step {step}, {phase}')
        for k in ('rgb_sha256','depth_sha256'):
            if not re.fullmatch('[0-9a-f]{64}',state['endpoint_sensor'][k]):
                raise PairEvidenceError(f'Invalid {k} at step {step}, {phase}')
    for k in ('position','rotation_xyzw','episode_over','collided'):
        if left[k]!=right[k]:raise PairEvidenceError(f'Paired {k} differs at step {step}, {phase}')
    for k in ('rgb_sha256','depth_sha256'):
        if left['endpoint_sensor'][k]!=right['endpoint_sensor'][k]:
            raise PairEvidenceError(f'Paired {k} differs at step {step}, {phase}')


def _frames(trace):
    calls=[];previous=trace[0]['state_evaluator_only']
    for row in trace:
        if row['kind']=='model_call':calls.append(row)
        if row['kind']=='primitive_action':
            n=row['step']-1
            _same_state(previous,row['before_evaluator_only'],n,'execution continuity')
            if any(r['frame']!=n for r in calls):
                raise PairEvidenceError(f'Call bound to wrong execution frame {n}')
            yield calls,row
            previous=row['after_evaluator_only'];calls=[]


def _input_diff(a,b):
    images=[[i['pixel_sha256'] for i in row['images']] for row in (a,b)]
    return dict(text_changed=a['prompt']!=b['prompt'],input_ids_changed=a['input_ids']!=b['input_ids'],
                changed_image_slots=[i for i,(x,y) in enumerate(zip_longest(*images),1) if x!=y],
                visual_tensor_changed=a['processed_image_sha256']!=b['processed_image_sha256'],
                visual_shape_changed=a['processed_image_shape']!=b['processed_image_shape'],
                generation_changed=any(a[k]!=b[k] for k in ('generation','stop_str','sep2')))


def _receipts(flow):
    by_call={};materials={}
    for row in flow:
        kind=row['kind']
        if kind in ('AdditionalEvidenceCompiled','ApproachCompiled','DynamicContextCompiled','MemoryAttachmentCompiled','EvoTopologyCompiled'):
            rid=row['request_id']
            if rid in materials:raise PairEvidenceError('Multiple compiled records for one request')
            materials[rid]=row
        if kind not in ('HostInputAudit','MemoryGenerateReturned','MemoryReadFallback'):continue
        k=row['decision_id'];events=by_call.setdefault(k,{})
        if kind in events:raise PairEvidenceError(f'Duplicate {kind} for decision {k}')
        events[kind]=row
    result={}
    for k,events in by_call.items():
        if 'MemoryReadFallback' in events:
            if len(events)!=1:raise PairEvidenceError(f'Conflicting fallback and model receipt for decision {k}')
            row=events['MemoryReadFallback']
            result[k]=dict(decision=k,frame=row['env_step'],route='native_fallback',reason=row['reason'])
            continue
        audit=events['HostInputAudit'];returned=events['MemoryGenerateReturned']
        if (audit['call_id']!=k or returned['call_id']!=k or audit['event_seq']>=returned['event_seq']
                or any(audit[key]!=returned[key] for key in ('request_id','snapshot_id','frame_uid','env_step'))):
            raise PairEvidenceError(f'Unbound model-input audit for decision {k}')
        slots=audit['slots']
        if len(slots)!=audit['logical_image_slots']:raise PairEvidenceError('Incomplete visual slot map')
        native=audit.get('native_image_slots');extra=audit.get('memory_attachment_slots')
        if native is None and extra is None and audit['mode']=='facts_only':
            # Legacy text-only receipts have an 8-slot map, a current slot and an actual visual shape.
            if not slots[-1]['is_current'] or any(s['source_kind']=='historical_attachment' for s in slots):
                raise PairEvidenceError('Invalid legacy text-only slot map')
            native=len(slots);extra=0
        if (type(native)is not int or type(extra)is not int or native<1 or extra<0
                or native+extra!=len(slots) or returned['projector_shape'][0]!=len(slots)
                or not slots[native-1]['is_current']):
            raise PairEvidenceError('Visual slot counts differ from generation receipt')
        result[k]=dict(decision=k,frame=audit['env_step'],route='materialized',request_id=audit['request_id'],
                       snapshot_id=audit['snapshot_id'],source_steps=[s['env_step']for s in audit['slots']],
                       native_slots=native,extra_slots=extra)
        compiled=materials.get(audit['request_id'])
        if compiled is not None:
            if compiled['decision_id']!=k or compiled['event_seq']>=audit['event_seq']:
                raise PairEvidenceError(f'Compiled material belongs to another decision at call {k}')
            details=compiled.get('model_fields',compiled.get('fields',compiled.get('records')))
            result[k]['compiled_kind']=compiled['kind'];result[k]['compiled_fields']=details
    return result


def compare_paired_prefix(original,candidate,flow):
    _same_state(original[0]['state_evaluator_only'],candidate[0]['state_evaluator_only'],0,'reset')
    receipts=_receipts(flow)
    cand_calls=[r for r in candidate if r['kind']=='model_call']
    if len(cand_calls)!=len(receipts) or any(receipts[r['call_id']]['frame']!=r['frame'] for r in cand_calls):
        raise PairEvidenceError('Candidate input path is not bound to each model call')
    result=dict(equal_action_prefix=0,paired_calls=0,first_input=None,first_output=None,
                first_call_count_change=None,first_execution=None,terminal=None)
    for (lc,l),(rc,r) in zip(_frames(original),_frames(candidate)):
        n=l['step']-1
        if r['step']!=n+1:raise PairEvidenceError('Nonmatching primitive step ordinal')
        _same_state(l['before_evaluator_only'],r['before_evaluator_only'],n,'before primitive')
        for j,(a,b) in enumerate(zip(lc,rc),1):
            result['paired_calls']+=1
            delta=_input_diff(a,b)
            bound=dict(frame=n,call_at_frame=j,original_call=a['call_id'],candidate_call=b['call_id'],
                       candidate_path=receipts[b['call_id']])
            if any(delta.values()) and result['first_input'] is None:
                result['first_input']=dict(bound,**delta)
            if a['output_ids']!=b['output_ids'] and result['first_output'] is None:
                result['first_output']=dict(bound,**delta,original_output=a['normalized_output'],
                    candidate_output=b['normalized_output'],parsed=[parse_host_output(x['normalized_output']) for x in (a,b)])
            if delta['generation_changed']:raise PairEvidenceError(f'Generation settings differ at frame {n}, call {j}')
        if len(lc)!=len(rc) and result['first_call_count_change'] is None:
            result['first_call_count_change']=dict(frame=n,original_calls=[v['call_id']for v in lc],
                                                    candidate_calls=[v['call_id']for v in rc])
        if l['action']!=r['action']:
            result['first_execution']=dict(step=n+1,actions=[l['action'],r['action']],
                last_calls=[l['last_call_id'],r['last_call_id']],stop_sources=[l['stop_source'],r['stop_source']])
            break
        _same_state(l['after_evaluator_only'],r['after_evaluator_only'],n+1,'after identical primitive')
        result['equal_action_prefix']+=1
    def tail(trace):
        actions=[r for r in trace if r['kind']=='primitive_action']
        return dict(steps=trace[-1]['steps'],reason=trace[-1]['termination_reason'],stop_source=trace[-1]['stop_source'],
                    last_call=actions[-1]['last_call_id'] if actions else None)
    result['terminal']=[tail(original),tail(candidate)]
    if result['first_execution'] is None and original[-1]['steps']!=candidate[-1]['steps']:
        n=result['equal_action_prefix']+1
        result['first_execution']=dict(step=n,kind='one_trajectory_ended',actions=[
            next((r['action'] for r in trace if r['kind']=='primitive_action' and r['step']==n),None)
            for trace in (original,candidate)])
    return result
