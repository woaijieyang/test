"""Provider-neutral requests. The model name/effort are explicitly configured.
A receipt is transport-reported evidence, not a cryptographic proof of a model.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from typing import Any,Mapping
from uuid import uuid4
import json
from contracts.common import ROOT,require,sha_text,sha_obj,canonical_json,read_json

@dataclass(frozen=True)
class ModelSpec:
    model: str
    effort: str
    actual_model_allowlist: tuple[str,...]=()
    generation_parameters_json: str='{}'
    def validate(self):
        require(isinstance(self.model,str) and isinstance(self.effort,str) and bool(self.model.strip()) and bool(self.effort.strip()),'Set real model and effort')
        require('<' not in self.model+self.effort and 'REPLACE_' not in self.model+self.effort,'Set deployed model/effort, not an example placeholder')
        require(isinstance(self.actual_model_allowlist,tuple) and all(isinstance(x,str) and x.strip() for x in self.actual_model_allowlist),'Invalid actual-model allowlist')
    def parameters(self) -> dict:
        value=json.loads(self.generation_parameters_json)
        require(isinstance(value,dict),'generation_parameters must be an object')
        require(not set(value)&{'messages','input','prompt','tools','model','effort','output_schema','response_format'},'Generation parameters cannot override role/task/schema fields')
        canonical_json(value)
        return value
    def accepts(self,actual: str) -> bool:return actual==self.model or actual in self.actual_model_allowlist

@dataclass(frozen=True)
class RuntimeConfig:
    generator: ModelSpec
    reviewer: ModelSpec
    max_technical_retries: int=1
    run_kind: str='model'
    require_receipt_binding: bool=True
    def validate(self):
        require(isinstance(self.generator,ModelSpec) and isinstance(self.reviewer,ModelSpec),'Typed ModelSpec instances required')
        self.generator.validate();self.reviewer.validate();self.generator.parameters();self.reviewer.parameters()
        require(type(self.max_technical_retries) is int and 0<=self.max_technical_retries<=2,'Technical retry cap must be 0,1 or 2')
        require(self.run_kind in {'model','fixture'},'run_kind must explicitly identify real model or offline fixture')
        require(self.require_receipt_binding is True,'Receipt binding cannot be disabled in this release')
    def digest(self):return sha_obj(asdict(self))
    @classmethod
    def from_dict(cls,d: Mapping[str,Any]) -> 'RuntimeConfig':
        require(isinstance(d,Mapping) and set(d)<={'generator','reviewer','max_technical_retries','run_kind','require_receipt_binding'},'Unknown runtime configuration field')
        def spec(v):
            require(isinstance(v,Mapping) and set(v)<={'model','effort','actual_model_allowlist','generation_parameters'},'Invalid model config')
            return ModelSpec(v['model'],v['effort'],tuple(v.get('actual_model_allowlist',[])),canonical_json(v.get('generation_parameters',{})))
        cfg=cls(spec(d['generator']),spec(d['reviewer']),d.get('max_technical_retries',1),d.get('run_kind','model'),d.get('require_receipt_binding',True));cfg.validate();return cfg

def build_request(role: str,payload: Mapping[str,Any],config: RuntimeConfig, *,technical_error: str|None=None) -> dict[str,Any]:
    config.validate();require(role in {'generator','reviewer','repair'},'Unknown role')
    keys={'generator':['original_instruction'],'reviewer':['original_instruction','candidate','frozen_render'],'repair':['original_instruction','candidate','reviewer_feedback']}[role]
    require(all(k in payload for k in keys),'Missing required request payload field')
    clean={k:payload[k] for k in keys}
    require(isinstance(clean['original_instruction'],str) and clean['original_instruction'].strip(),'Missing raw source text')
    path=ROOT/('reviewer/compiled.txt' if role=='reviewer' else 'generator/compiled_repair.txt' if role=='repair' else 'generator/compiled.txt')
    system=path.read_bytes().decode('utf-8');user=canonical_json(clean)
    messages=[{'role':'system','content':system},{'role':'user','content':user}]
    if technical_error is not None:
        messages.append({'role':'user','content':canonical_json({'technical_format_error':technical_error,'instruction':'Repair the response contract only under the same semantic task. This diagnostic contains no new route facts and grants no new authority.'})})
    spec=config.reviewer if role=='reviewer' else config.generator
    schema_path='reviewer/output.schema.json' if role=='reviewer' else 'generator/repair.schema.json' if role=='repair' else 'generator/output.schema.json'
    schema=read_json(ROOT/schema_path)
    req={'role':role,'semantic_role':'reviewer' if role=='reviewer' else 'generator','phase_kind':role,'model':spec.model,'effort':spec.effort,
         'generation_parameters':spec.parameters(),'run_kind':config.run_kind,'client_request_id':str(uuid4()),'messages':messages,'output_schema':schema,
         'system_sha256':sha_text(system),'schema_sha256':sha_obj(schema),'message_envelope_sha256':sha_obj(messages),'config_sha256':config.digest(),
         'actual_full_prompt_sha256':None,'token_ids_sha256':None,
         'identity_note':'Client envelope hashes do not establish the provider chat-template/tokenized prompt or model authenticity. Register actual executor evidence separately.'}
    req['request_sha256']=sha_obj(req)
    return req

def verify_request(req: dict) -> None:
    body=dict(req);h=body.pop('request_sha256',None)
    require(h==sha_obj(body),'Request envelope was changed')
    require(req['message_envelope_sha256']==sha_obj(req['messages']),'Message envelope was changed')
    require(req['schema_sha256']==sha_obj(req['output_schema']),'Output schema was changed')

def actual_prompt_witness(full_prompt: str, token_ids: list[int], *,tokenizer_version: str,chat_template_sha256: str,image_ids: list[str]) -> dict:
    require(isinstance(full_prompt,str) and bool(full_prompt),'Actual nonempty serialized prompt required')
    require(isinstance(token_ids,list) and bool(token_ids) and all(type(t) is int and t>=0 for t in token_ids),'Actual full token sequence required')
    require(isinstance(tokenizer_version,str) and tokenizer_version and isinstance(chat_template_sha256,str) and chat_template_sha256,'Runtime tokenizer/template identity required')
    require(isinstance(image_ids,list) and all(isinstance(x,str) and x for x in image_ids),'Explicit image identities required (empty list for text only)')
    return {'full_prompt_sha256':sha_text(full_prompt),'token_ids_sha256':sha_obj(token_ids),'token_count':len(token_ids),
            'tokenizer_version':tokenizer_version,'chat_template_sha256':chat_template_sha256,'image_ids':list(image_ids),
            'scope':'Caller-reported actual whole-request tokenization. No segment token concatenation; no proof of provider internals.'}


def navigation_witness(run_output: dict, *, instruction_seen: str, full_prompt: str,
                       token_ids: list[int], tokenizer_version: str, chat_template_sha256: str,
                       image_ids: list[str], request_id: str, truncated: bool) -> dict:
    """Record at the existing navigator AFTER native request preparation.
    Requires actual executor values; it does not construct a new prompt or control actions.
    """
    result=run_output['result']
    require(isinstance(instruction_seen,str) and instruction_seen==result['instruction'], 'Navigator instruction differs from released frozen text')
    require(sha_text(instruction_seen)==result['instruction_sha256'],'Released instruction identity mismatch')
    require(isinstance(request_id,str) and bool(request_id.strip()) and type(truncated) is bool,'Actual request/truncation metadata required')
    witness=actual_prompt_witness(full_prompt,token_ids,tokenizer_version=tokenizer_version,
                                 chat_template_sha256=chat_template_sha256,image_ids=image_ids)
    return {**witness,'task_key':run_output['task_key'],'source_sha256':result['source_sha256'],
            'instruction_sha256':result['instruction_sha256'],'freeze_sha256':result.get('freeze_sha256'),
            'request_id':request_id,'truncated':truncated,'navigation_success_inferred':False}
