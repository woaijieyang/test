"""Bounded offline two-role workflow. Callback receives an immutable request copy.
No provider SDK, no navigation, no third semantic role, no unbounded repair loop.
"""
from __future__ import annotations
from copy import deepcopy
from typing import Callable,Any,Mapping
from adapter import ingest,SourceRecord
from contracts.common import ROOT,ContractError,require,sha_obj,sha_text,read_json
from contracts.validate import candidate as validate_candidate,review as validate_review,repair as validate_repair
from renderer import prepare,bind_review,commit,fallback
from .requests import RuntimeConfig,build_request,verify_request
from .compile import compile_all
Call=Callable[[dict[str,Any]],dict[str,Any]]
MapProvider=Callable[[SourceRecord,dict[str,Any]],list[list[dict]]|None]
Journal=Callable[[dict[str,Any]],None]

class TechnicalCallFailure(RuntimeError):pass

def experiment_identity(config: RuntimeConfig) -> dict:
    config.validate();compile_all(check=True)
    manifest=read_json(ROOT/'orchestrator/COMPILED_MANIFEST.json')
    prompts={r:manifest[r]['sha256'] for r in ['generator','reviewer','repair']}
    schemas={r:sha_obj(read_json(ROOT/p)) for r,p in [('generator','generator/output.schema.json'),('reviewer','reviewer/output.schema.json'),('repair','generator/repair.schema.json')]}
    runtime_files={str(p.relative_to(ROOT)):sha_text(p.read_bytes().decode('utf-8')) for folder in ['adapter','renderer','contracts','orchestrator'] for p in sorted((ROOT/folder).glob('*.py'))}
    identity={'version':'v1.3-static.2','runtime_component_sha256':runtime_files,'config_sha256':config.digest(),'prompts':prompts,'schemas':schemas,'compiled_manifest_sha256':sha_obj(manifest)}
    identity['experiment_sha256']=sha_obj(identity)
    return identity

def run_record(record: Mapping[str,Any],call: Call,config: RuntimeConfig, *,maps: MapProvider|None=None,journal: Journal|None=None) -> dict[str,Any]:
    source=ingest(record);lock=experiment_identity(config)
    events=[];prepared=[];review_receipts=[];phase='G0';used_receipt_ids=set()
    def log(payload):
        if journal is not None:journal(deepcopy(payload))
    def invoke(role,payload,validator):
        error=None
        for attempt in range(config.max_technical_retries+1):
            req=build_request(role,payload,config,technical_error=error)
            event={'phase':phase,'role':role,'semantic_role':'reviewer' if role=='reviewer' else 'generator','attempt':attempt,
                   'request':deepcopy(req),'request_sha256':req['request_sha256']}
            try:
                verify_request(req)
                require(req['system_sha256']==lock['prompts'][role], 'prompt changed after this record began')
                require(req['schema_sha256']==lock['schemas'][role], 'schema changed after this record began')
                # Persist requested identity BEFORE calling the possibly external transport.
                log({'event':'call_started','task_key':source.task_key,'phase':phase,'attempt':attempt,'request':req})
                answer=call(deepcopy(req));event['response']=deepcopy(answer)
                require(isinstance(answer,dict) and isinstance(answer.get('receipt'),dict),'Malformed transport envelope')
                receipt=answer['receipt'];out=answer['output']
                require(isinstance(receipt.get('request_id'),str) and bool(receipt['request_id'].strip()),'Provider request ID missing')
                require(receipt['request_id'] not in used_receipt_ids,'Replayed provider request ID')
                require(receipt.get('client_request_id')==req['client_request_id'] and receipt.get('request_sha256')==req['request_sha256'],'Response not bound to this exact request')
                require(receipt.get('execution_kind')==config.run_kind,'Fixture/model receipt mismatch')
                spec=config.reviewer if role=='reviewer' else config.generator
                require(spec.accepts(receipt.get('model')) and receipt.get('effort')==req['effort'],'Reported model/effort differs from locked config')
                require(receipt.get('truncated') is not True and receipt.get('finish_reason') not in {'length','max_tokens','incomplete'},'Truncated model response is a technical failure')
                used_receipt_ids.add(receipt['request_id'])
                validator(out);event['technical_validation']='passed';events.append(event)
                log({'event':'call_completed','task_key':source.task_key,'detail':event})
                return deepcopy(out),deepcopy(receipt),req
            except (ContractError,KeyError,TypeError,ValueError,OSError,TimeoutError,RuntimeError) as exc:
                error=f'{type(exc).__name__}: {exc}';event['technical_validation']='failed';event['error']=error;events.append(event)
                log({'event':'call_failed','task_key':source.task_key,'detail':event})
        raise TechnicalCallFailure(error or 'Unknown technical failure')
    def freeze(candidate):
        plan=maps(source,deepcopy(candidate)) if maps else None
        f=prepare(source,candidate,explicit_maps=plan)
        item={'freeze_sha256':f.freeze_sha256,'candidate':f.candidate(),'instruction':f.instruction,'plan':f.plan(),'input_candidate_sha256':f.input_candidate_sha256}
        prepared.append(item);log({'event':'candidate_frozen','task_key':source.task_key,'phase':phase,'detail':item});return f
    try:
        g0,_,_=invoke('generator',source.model_input(),lambda o:(validate_candidate(source.original_instruction,o),prepare(source,o,explicit_maps=maps(source,o) if maps else None)));f=freeze(g0)
        phase='R0';r0,rr,request=invoke('reviewer',f.review_payload(source),lambda o:validate_review(source.original_instruction,f.candidate(),o))
        bound=bind_review(source,f,r0,request_id=rr['request_id'],review_prompt_sha256=request['system_sha256']);review_receipts.append(deepcopy(bound))
        if r0['verdict']=='pass':
            result=commit(source,f,bound,expected_review_prompt_sha256=request['system_sha256'])
        elif g0['status']=='needs_review' and r0['verdict']=='unresolved':
            result=fallback(source,'source_limited')
        else:
            phase='G1';payload={'original_instruction':source.original_instruction,'candidate':f.candidate(),'reviewer_feedback':r0}
            g1,_,_=invoke('repair',payload,lambda o:(validate_repair(source.original_instruction,r0,o),prepare(source,o['candidate'],explicit_maps=maps(source,o['candidate']) if maps else None)));f=freeze(g1['candidate'])
            phase='R1';r1,rr,request=invoke('reviewer',f.review_payload(source),lambda o:validate_review(source.original_instruction,f.candidate(),o))
            bound=bind_review(source,f,r1,request_id=rr['request_id'],review_prompt_sha256=request['system_sha256']);review_receipts.append(deepcopy(bound))
            result=commit(source,f,bound,expected_review_prompt_sha256=request['system_sha256']) if r1['verdict']=='pass' else fallback(source,'unresolved_after_one_repair')
    except (TechnicalCallFailure,ContractError,KeyError,TypeError,ValueError,OSError,TimeoutError,RuntimeError) as exc:
        result=fallback(source,'technical_failure');result['technical_error']=f'{type(exc).__name__}: {exc}';result['failed_phase']=phase
    result['run_kind']=config.run_kind
    result['semantic_call_count']=len({x['phase'] for x in events})
    result['transport_attempt_count']=len([x for x in events if 'response' in x or 'error' in x])
    output={'version':'v1.3-static.2','task_key':source.task_key,'record_identity_sha256':source.record_identity_sha256,
            'source_profile':source.profile(),'config_sha256':config.digest(),'prompt_lock':lock['prompts'],
            'experiment_lock':lock,'experiment_lock_sha256':lock['experiment_sha256'],'result':result,'events':events,
            'prepared_candidates':prepared,'review_receipts':review_receipts,'runtime_changed':False}
    log({'event':'record_completed','task_key':source.task_key,'result':result})
    return output
