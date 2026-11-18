"""Bounded two-role offline workflow. Inject your current model transport; no default API."""
from __future__ import annotations
from typing import Callable
from subprocess import run as subprocess_run
import json,argparse,sys,shlex
from pathlib import Path
from adapter.source import Source,load_record
from renderer.freeze import freeze,unchanged
from host.compile import compile_prompt
from host import protocol
from shared.identity import need,canonical,obj_hash,text_hash,ContractError

Transport=Callable[[dict],dict]

def request(role,phase,payload,pin):
    text,schema=compile_prompt(role,phase)
    return {'role':role,'phase':phase,'model':pin['model'],'effort':pin['effort'],'messages':[{'role':'system','content':text},{'role':'user','content':canonical(payload)}],'output_schema':schema}

def run_record(src:Source,transport:Transport,*,pins:dict,separator='\n'):
    """Returns final instruction AND a technical trace. Score/GT never enter this API.
    Technical errors fail closed to the immutable source, separately labeled.
    A real transport must report actual model/effort, not just echo a requested alias.
    """
    need(set(pins)=={'generator','reviewer'} and all(all(isinstance(v.get(k),str) and v[k] for k in ('model','effort')) for v in pins.values()),'Explicit model/effort pins required for both roles')
    events=[]; snapshots=[]
    def call(role,phase,payload,candidate_digest=None):
        req=request(role,phase,payload,pins[role]);system,user=req['messages'];z={'role':role,'phase':phase,'request':req,'request_sha256':obj_hash(req),'system_sha256':text_hash(system['content']),'schema_sha256':obj_hash(req['output_schema']),'source_sha256':src.sha,'reviewed_snapshot':candidate_digest};events.append(z)
        reply=transport(req);need(isinstance(reply,dict) and 'output' in reply,'Malformed transport reply');m=reply.get('receipt',{});need(isinstance(m,dict),'Malformed provider receipt');z['raw_output']=reply['output'];z['receipt']={k:m.get(k) for k in ['model','effort','request_id','provider_request_sha256','input_tokens','output_tokens']};need(m.get('model')==req['model'] and m.get('effort')==req['effort'] and m.get('request_id'),'Missing or mismatched actual invocation metadata');z['output_sha256']=obj_hash(reply['output']);return reply['output']
    def finish(reason,view,detail=None):
        return {'version':'final-best-v1','task_key':src.key,'profile':src.profile,'source_sha256':src.sha,'disposition':reason,'render_mode':view.mode,'instruction':view.rendered,'instruction_sha256':view.sha,'snapshot_sha256':view.snapshot,'separator_policy':repr(separator),'error':detail,'semantic_correctness_verified':False,'navigation_evaluated':False,'snapshots':snapshots,'calls':events}
    try:
        orig={'original_instruction':src.raw};g=call('generator','initial',orig)
        for turn in range(2):
            protocol.generator(src.raw,g);active=g['status']=='ok'
            view=freeze(src,g['subtasks'],separator) if active else unchanged(src)
            # Review the frozen strings, never the raw draft if its source whitespace was restored.
            c={'status':g['status'],'subtasks':list(view.stages) if active else [],'issues':g['issues']};frozen=canonical(c)
            snaps={'render_snapshot_sha256':view.snapshot if active else None,'candidate':json.loads(frozen),'candidate_sha256':text_hash(frozen),'rendered_instruction':view.rendered if active else None,'rendered_sha256':view.sha if active else None,'mode':view.mode if active else None,'ledger':json.loads(view.ledger_json) if active else None}; snapshots.append(snaps)
            binding=obj_hash([src.key,src.sha,text_hash(frozen),snaps['render_snapshot_sha256']]);snaps['bound_candidate']=binding
            # Fresh R1 gets the same projection as R0, not review history or scores.
            rv=call('reviewer','review' if turn==0 else 'recheck',{**orig,'candidate':json.loads(frozen),'rendered_instruction':snaps['rendered_instruction']},binding);protocol.reviewer(src.raw,c,rv)
            if rv['verdict']=='pass':
                need(active and view.sha==snaps['rendered_sha256'] and view.snapshot==snaps['render_snapshot_sha256'] and binding==events[-1]['reviewed_snapshot'],'Stale preview/review receipt')
                return finish('accepted_source_exact' if view.mode=='SOURCE_EXACT' else 'accepted_candidate',view)
            if rv['verdict']=='unresolved' and (turn==1 or not active): return finish('fallback_unresolved',unchanged(src))
            if turn==1:return finish('fallback_unresolved_after_repair',unchanged(src))
            answer=call('generator','repair',{**orig,'candidate':json.loads(frozen),'review':rv});protocol.feedback(src.raw,rv,answer);g=answer['candidate']
    except (ContractError,KeyError,TypeError,ValueError,OSError,TimeoutError,RuntimeError) as ex:
        return finish('fallback_technical',unchanged(src),f'{type(ex).__name__}: {ex}')
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
    ap=argparse.ArgumentParser();ap.add_argument('--record',required=True);ap.add_argument('--pins',required=True);ap.add_argument('--output',required=True);ap.add_argument('--transport',nargs=argparse.REMAINDER,required=True,help='existing command: JSON request on stdin, reply on stdout; may incur cost');a=ap.parse_args();need(a.transport,'Transport required, no built-in live endpoint');target=Path(a.output);need(not target.exists(),'Refuse to overwrite existing run');src=load_record(a.record);r=run_record(src,command_transport(a.transport),pins=json.loads(Path(a.pins).read_bytes()));target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8',newline='') as f:json.dump(r,f,ensure_ascii=False,indent=2)
    print(r['disposition'],r['instruction_sha256']);sys.exit(2 if r['disposition']=='fallback_technical' else 0)
if __name__=='__main__':main()
