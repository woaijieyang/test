"""Bounded two-role offline workflow. Inject your current model transport; no default API."""
from __future__ import annotations
from typing import Callable
from subprocess import run as subprocess_run
import json,argparse,sys,shlex
from pathlib import Path
from adapter.source import Source,load_record
from renderer.freeze import freeze,unchanged
from host.compile import compile_prompt
from host.template_selector import select_examples,DEFAULT_EXAMPLES
from host import protocol
from shared.identity import need,canonical,obj_hash,text_hash,ContractError

Transport=Callable[[dict],dict]

def request(role,phase,payload,pin,profile,selected_ids):
    text,schema=compile_prompt(role,phase,profile=profile,selected_ids=selected_ids)
    return {'role':role,'phase':phase,'model':pin['model'],'effort':pin['effort'],'messages':[{'role':'system','content':text},{'role':'user','content':canonical(payload)}],'output_schema':schema,'selected_example_ids':list(selected_ids)}

VERSION = 'final-best-v1-roles-closed-loop-35-entry-diagnostics-1'


def run_record(src:Source,transport:Transport,*,pins:dict,separator='\n',example_count=DEFAULT_EXAMPLES,selection_mode='adaptive'):
    """Bounded original workflow; diagnostic context adds no calls or retries."""
    events=[]; snapshots=[]; selections={role:[] for role in ('generator','reviewer')}
    context={'step':'configuration_validation','role':None,'phase':None}

    def call(role,phase,payload,candidate_digest=None):
        context.update(step='request_construction',role=role,phase=phase)
        req=request(role,phase,payload,pins[role],src.profile,selections[role])
        system,user=req['messages']
        z={'role':role,'phase':phase,'request':req,'request_sha256':obj_hash(req),
           'system_sha256':text_hash(system['content']),'schema_sha256':obj_hash(req['output_schema']),
           'source_sha256':src.sha,'reviewed_snapshot':candidate_digest,
           'selected_example_ids':list(selections[role]),'call_state':'request_constructed'}
        events.append(z)
        context['step']='transport'
        z['call_state']='transport_entered'
        try:
            reply=transport(req)
        except Exception:
            z['call_state']='transport_failed_execution_unknown'
            raise
        z['call_state']='transport_returned'
        context['step']='receipt_validation'
        need(isinstance(reply,dict) and 'output' in reply,'Malformed transport reply',
             code='TRANSPORT_REPLY_INVALID',module='host.run',path='/output')
        z['raw_output']=reply['output'];m=reply.get('receipt',{})
        need(isinstance(m,dict),'Malformed provider receipt',code='MODEL_RECEIPT_INVALID',module='host.run',path='/receipt')
        z['receipt']={k:m.get(k) for k in ['model','effort','request_id','provider_request_sha256','input_tokens','output_tokens']}
        z['call_state']='receipt_received'
        valid=m.get('model')==req['model'] and m.get('effort')==req['effort'] and m.get('request_id')
        if not valid:z['call_state']='receipt_invalid'
        need(valid,'Missing or mismatched actual invocation metadata',code='MODEL_RECEIPT_MISMATCH',
             module='host.run',path='/receipt',expected={'model':req['model'],'effort':req['effort'],'request_id':'nonempty'})
        z['output_sha256']=obj_hash(reply['output']);z['call_state']='receipt_verified'
        return reply['output']

    def finish(reason,view,detail=None,diagnostic=None):
        return {'version':VERSION,'task_key':src.key,'profile':src.profile,'source_sha256':src.sha,
                'example_selection':{'mode':selection_mode,'configured_example_count':example_count,
                'actual_generator_examples':len(selections['generator']),'actual_reviewer_examples':len(selections['reviewer']),
                'generator':list(selections['generator']),'reviewer':list(selections['reviewer'])},
                'disposition':reason,'render_mode':view.mode,'instruction':view.rendered,
                'instruction_sha256':view.sha,'snapshot_sha256':view.snapshot,'separator_policy':repr(separator),
                'error':detail,'diagnostic':diagnostic,'semantic_correctness_verified':False,
                'navigation_evaluated':False,'snapshots':snapshots,'calls':events}
    try:
        need(isinstance(pins,dict) and set(pins)=={'generator','reviewer'} and
             all(isinstance(v,dict) and all(isinstance(v.get(k),str) and v[k] for k in ('model','effort')) for v in pins.values()),
             'Explicit model/effort pins required for both roles',code='CONFIGURATION_INVALID',module='host.run',path='/pins')
        context['step']='example_selection'
        selections={role:select_examples(role,src.profile,src.raw,count=example_count,mode=selection_mode)
                    for role in ('generator','reviewer')}
        orig={'original_instruction':src.raw};g=call('generator','initial',orig)
        for turn in range(2):
            context.update(step='generator_validation',role='generator',phase='initial' if turn==0 else 'repair')
            protocol.generator(src.raw,g);active=g['status']=='ok'
            context['step']='renderer_freeze'
            view=freeze(src,g['subtasks'],separator) if active else unchanged(src)
            c={'status':g['status'],'subtasks':list(view.stages) if active else [],'issues':g['issues']};frozen=canonical(c)
            snaps={'render_snapshot_sha256':view.snapshot if active else None,'candidate':json.loads(frozen),
                   'candidate_sha256':text_hash(frozen),'rendered_instruction':view.rendered if active else None,
                   'rendered_sha256':view.sha if active else None,'mode':view.mode if active else None,
                   'ledger':json.loads(view.ledger_json) if active else None};snapshots.append(snaps)
            binding=obj_hash([src.key,src.sha,text_hash(frozen),snaps['render_snapshot_sha256']]);snaps['bound_candidate']=binding
            phase='review' if turn==0 else 'recheck'
            rv=call('reviewer',phase,{**orig,'candidate':json.loads(frozen),'rendered_instruction':snaps['rendered_instruction']},binding)
            context.update(step='reviewer_validation',role='reviewer',phase=phase)
            protocol.reviewer(src.raw,c,rv)
            if rv['verdict']=='pass':
                context['step']='snapshot_commit'
                need(active and view.sha==snaps['rendered_sha256'] and view.snapshot==snaps['render_snapshot_sha256'] and binding==events[-1]['reviewed_snapshot'],
                     'Stale preview/review receipt',code='SNAPSHOT_BINDING_MISMATCH',module='host.run',path='/snapshots')
                return finish('accepted_source_exact' if view.mode=='SOURCE_EXACT' else 'accepted_candidate',view)
            if rv['verdict']=='unresolved' and (turn==1 or not active):return finish('fallback_unresolved',unchanged(src))
            if turn==1:return finish('fallback_unresolved_after_repair',unchanged(src))
            answer=call('generator','repair',{**orig,'candidate':json.loads(frozen),'review':rv})
            context.update(step='generator_repair_validation',role='generator',phase='repair')
            protocol.feedback(src.raw,rv,answer);g=answer['candidate']
    except (ContractError,KeyError,TypeError,ValueError,OSError,TimeoutError,RuntimeError) as ex:
        if isinstance(ex,ContractError):diagnostic=ex.to_dict()
        else:
            code='TRANSPORT_TIMEOUT' if isinstance(ex,TimeoutError) else 'HOST_EXECUTION_FAILED'
            diagnostic={'code':code,'module':'host.run','path':'','exception_type':type(ex).__name__,'message':str(ex)}
        reviewer_events=[e for e in events if e['role']=='reviewer']
        diagnostic.update(context)
        diagnostic['reviewer_status']=reviewer_events[-1]['call_state'] if reviewer_events else 'not_requested'
        diagnostic['interpretation_limit']=diagnostic.get('interpretation_limit','Technical diagnostic only; no semantic or navigation conclusion is established.')
        return finish('fallback_technical',unchanged(src),f'{type(ex).__name__}: {ex}',diagnostic)
    raise RuntimeError('Unreachable workflow state')


def receipt_for_navigation(result,*,instruction_seen,full_prompt_utf8:bytes,input_ids,tokenizer_id,template_id,image_ids,truncated,request_id):
    """Instrument the existing navigator *after* its native full-request preparation.
    This checks instruction identity, not that external IDs or images were computed correctly.
    Caller must supply actual full-sequence IDs, not concatenated per-stage tokenization.
    """
    import hashlib
    need(isinstance(instruction_seen,str) and text_hash(instruction_seen)==result['instruction_sha256'],'Navigation instruction not the released bytes')
    need(isinstance(full_prompt_utf8,bytes) and full_prompt_utf8 and isinstance(input_ids,list) and input_ids and all(type(i) is int for i in input_ids),'Actual native request/IDs required');need(all(isinstance(x,str) and x for x in (tokenizer_id,template_id,request_id)),'Missing native metadata');need(isinstance(image_ids,list) and type(truncated) is bool,'Missing image/truncation metadata')
    return {'request_id':request_id,'task_key':result['task_key'],'source_sha256':result['source_sha256'],'snapshot_sha256':result['snapshot_sha256'],'instruction_sha256':result['instruction_sha256'],'full_prompt_sha256':hashlib.sha256(full_prompt_utf8).hexdigest(),'tokenizer_id':tokenizer_id,'template_id':template_id,'input_ids':input_ids,'input_ids_sha256':obj_hash(input_ids),'image_ids_in_order':image_ids,'truncated':truncated}

def command_transport(argv,timeout=300):
    def send(req):
        import subprocess
        try:p=subprocess_run(argv,input=canonical(req).encode(),capture_output=True,timeout=timeout,check=False)
        except subprocess.TimeoutExpired as e:raise TimeoutError('existing transport timeout') from e
        if p.returncode:raise RuntimeError(f'existing transport exit {p.returncode}; inspect its own log')
        return json.loads(p.stdout.decode('utf-8'))
    return send

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--record',required=True);ap.add_argument('--pins',required=True);ap.add_argument('--output',required=True);ap.add_argument('--transport',nargs=argparse.REMAINDER,required=True,help='existing command: JSON request on stdin, reply on stdout; may incur cost');a=ap.parse_args()
    target=Path(a.output);need(not target.exists(),'Refuse to overwrite existing run')
    step='source_loading'
    try:
        need(a.transport,'Transport required, no built-in live endpoint',code='CONFIGURATION_INVALID',module='host.run',path='/transport')
        src=load_record(a.record)
        step='configuration_loading'
        pins=json.loads(Path(a.pins).read_bytes())
        r=run_record(src,command_transport(a.transport),pins=pins)
    except (ContractError,ValueError,TypeError,OSError) as ex:
        d=ex.to_dict() if isinstance(ex,ContractError) else {'code':'CONFIGURATION_LOAD_FAILED','module':'host.run','path':'/pins','message':type(ex).__name__}
        d.update(step=step,role=None,phase=None,reviewer_status='not_requested')
        r={'version':VERSION,'disposition':'input_failed','error':str(ex),'diagnostic':d,'calls':[],
           'navigation_evaluated':False,'semantic_correctness_verified':False}
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8',newline='') as f:json.dump(r,f,ensure_ascii=False,indent=2)
    print(r['disposition'],r.get('instruction_sha256','no-source-identity'));sys.exit(2 if r['disposition'] in ('fallback_technical','input_failed') else 0)
if __name__=='__main__':main()
