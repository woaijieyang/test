"""Source-aware deterministic preparation BEFORE semantic review.
Commit returns the exact frozen bytes; no cleanup or re-render occurs after approval.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, asdict
import json
from typing import Any, Sequence
from adapter.source import SourceRecord
from adapter.alignment import align_stages
from adapter.provenance import boundary_partition, assembled_stage_maps, explicit_fragment
from contracts.common import canonical_json, sha_text, sha_obj, require, ProvenanceError
from contracts.validate import candidate as validate_candidate, review as validate_review

POLICY={'version':'source-aware-lf-2','stage_separator':'\n','source_outer_whitespace':'preserve',
        'source_internal_whitespace':'preserve_exact_spans_or_unique_exact_token_runs_before_review','new_edit_word_seam':'U+0020-single',
        'native_newline':'retain_if_copied_not_inferred_as_stage','post_review_mutation':'forbidden',
        'ambiguous_alignment':'ordinary_EDIT_or_technical_provenance_error_never_choose_first'}
POLICY_SHA=sha_obj(POLICY)

@dataclass(frozen=True)
class FrozenCandidate:
    task_identity_sha256: str
    source_sha256: str
    input_candidate_sha256: str
    candidate_json: str
    candidate_sha256: str
    instruction: str
    instruction_sha256: str
    mode: str
    policy_sha256: str
    plan_json: str
    freeze_sha256: str

    def _body(self) -> dict[str,Any]:
        d=asdict(self);d.pop('freeze_sha256');return d
    def verify(self) -> None:
        require(sha_obj(self._body())==self.freeze_sha256,'frozen record changed after preparation')
        require(sha_text(self.instruction)==self.instruction_sha256,'instruction bytes changed')
        require(sha_obj(json.loads(self.candidate_json))==self.candidate_sha256,'candidate text changed')
        require(self.policy_sha256==POLICY_SHA,'renderer policy changed')
        c=json.loads(self.candidate_json);p=json.loads(self.plan_json)
        require(p.get('mode')==self.mode and p.get('policy')==POLICY,'frozen plan policy/mode mismatch')
        spans=p.get('stage_spans',[])
        require(len(spans)==len(c['subtasks']),'frozen stage count mismatch')
        last_end=None
        for i,(text,sp) in enumerate(zip(c['subtasks'],spans)):
            a,b=sp.get('char_start'),sp.get('char_end')
            require(type(a) is int and type(b) is int and 0<=a<b<=len(self.instruction),'invalid frozen source offsets')
            require(sp.get('index')==i and self.instruction[a:b]==text,'frozen stage text disagrees with instruction')
            require(sp.get('utf8_start')==len(self.instruction[:a].encode()) and sp.get('utf8_end')==len(self.instruction[:b].encode()),'frozen UTF-8 offsets mismatch')
            if last_end is not None:require(self.instruction[last_end:a]=='\n','stage separator is not the frozen LF policy')
            last_end=b
        if c['status']=='ok' and self.mode=='SOURCE_EXACT':
            require(c['subtasks']==[self.instruction],'source exact must have one identical stage')
        elif c['status']=='ok':
            require(p['source_prefix']+'\n'.join(c['subtasks'])+p['source_suffix']==self.instruction,'frozen outer envelope mismatch')

    def candidate(self) -> dict[str,Any]:return json.loads(self.candidate_json)
    def plan(self) -> dict[str,Any]:return json.loads(self.plan_json)
    def review_payload(self, source: SourceRecord) -> dict[str,Any]:
        self.verify();_source_matches(source,self)
        return {'original_instruction':source.original_instruction,'candidate':self.candidate(),
                'frozen_render':{'freeze_sha256':self.freeze_sha256,'instruction':self.instruction,
                                 'instruction_sha256':self.instruction_sha256,'mode':self.mode,
                                 'stage_spans':self.plan()['stage_spans'],
                                 'note':'Prepared exact text and host-generated offsets; not observed navigation state.'}}

def _source_matches(source: SourceRecord, frozen: FrozenCandidate) -> None:
    require(source.source_sha256==frozen.source_sha256 and source.record_identity_sha256==frozen.task_identity_sha256,
            'source/record does not match frozen candidate')

def _edit_text(text: str, source: SourceRecord, kind: str) -> None:
    require(isinstance(text,str) and bool(text), 'empty EDIT/SEAM text')
    if kind=='SEAM':
        require(text in {' '},'new fragment seams must be one explicit U+0020');return
    if text!=text.strip() or '  ' in text or any(c.isspace() and c!=' ' for c in text):
        raise ProvenanceError('EDIT has nonstandard whitespace without verified COPY/MOVE provenance; supply a verified fragment map before review, do not normalize it')
    for c in ['\u2018','\u2019','\u201c','\u201d']:
        if c in text and c not in source.original_instruction:
            raise ProvenanceError('new decorative quotation mark in EDIT; no Unicode normalization authorized')
    if '\\n' in text and '\\n' not in source.original_instruction:
        raise ProvenanceError('literal backslash-n introduced in EDIT')

def _validate_maps(source: SourceRecord, texts: list[str], stages: list[list[dict]]) -> list[list[dict]]:
    require(len(stages)==len(texts),'provenance stage count differs')
    result=[]
    for text,ops in zip(texts,stages):
        require(bool(ops),'empty stage provenance')
        validated=[]
        for op in ops:
            op=deepcopy(op);kind=op.get('kind')
            if kind in {'COPY','MOVE'}:
                span=op.get('source_span');require(isinstance(span,list) and len(span)==2,'copy span missing')
                fragment=explicit_fragment(source,span[0],span[1],op.get('text'),kind=kind)
                op['text']=fragment['text']
            elif kind in {'EDIT','SEAM'}:_edit_text(op.get('text'),source,kind)
            else:raise ProvenanceError('unknown source-map operation')
            validated.append(op)
        require(''.join(x['text'] for x in validated)==text,'mapping would alter generator text; only generator authors text')
        require(text==text.strip(),'edited stage has unauthorized outer whitespace; do not trim silently')
        result.append(validated)
    return result

def prepare(source: SourceRecord, proposed: dict[str,Any], *,
            explicit_maps: list[list[dict]] | None=None) -> FrozenCandidate:
    validate_candidate(source.original_instruction,proposed)
    inp=deepcopy(proposed);c=deepcopy(proposed);ledger=[];boundaries=[];maps=[];stage_spans=[]
    # Relocate only the verified source suffix, with complete ordered body coverage.
    # The raw proposal remains in inp and the reviewer receives the frozen result.
    if len(c.get('subtasks', [])) > 1 and source.suffix and c['subtasks'][-1].endswith(source.suffix):
        body_stages = list(c['subtasks'])
        body_stages[-1] = body_stages[-1][:-len(source.suffix)]
        if boundary_partition(source, body_stages) is not None:
            c['subtasks'] = body_stages
            ledger.append({'kind': 'VERIFIED_SOURCE_SUFFIX_RELOCATED_BEFORE_REVIEW',
                           'suffix': source.suffix, 'basis': 'complete_ordered_source_body_coverage'})
    mode='SOURCE_EXACT'
    if c['status']=='needs_review':
        instruction=source.original_instruction
        ledger.append({'kind':'PROVISIONAL_SOURCE_FALLBACK','reason':'Review the refusal, not a fabricated executable plan'})
    elif len(c['subtasks'])==1 and c['subtasks'][0] in {source.original_instruction,source.body}:
        instruction=source.original_instruction
        if c['subtasks'][0]!=instruction:
            c['subtasks']=[instruction]
            ledger.append({'kind':'SOURCE_ENVELOPE_RESTORED_BEFORE_REVIEW','not_a_semantic_edit':True})
        maps=[[{'kind':'COPY_SOURCE_EXACT','source_span':[0,len(instruction)],'text':instruction}]]
    else:
        texts=c['subtasks']
        part=boundary_partition(source,texts)
        if part is not None:
            maps,boundaries=part
            if explicit_maps is not None:_validate_maps(source,texts,explicit_maps)
        elif explicit_maps is not None:
            maps=_validate_maps(source,texts,explicit_maps)
        else:
            texts,maps,extra=align_stages(source,texts)
            ledger.extend(extra)
            c['subtasks']=texts
        # Source whitespace is restored only before review and only from exact
        # correspondences. No route tokens are added or removed by this step.
        if texts==[source.body] or texts==[source.original_instruction]:
            mode='SOURCE_EXACT';instruction=source.original_instruction;c['subtasks']=[instruction]
            maps=[[{'kind':'COPY_SOURCE_EXACT','source_span':[0,len(instruction)],'text':instruction}]]
            ledger.append({'kind':'SURFACE_IDENTITY_RECOVERED_BEFORE_REVIEW','not_a_semantic_edit':True})
        else:
            maps=_validate_maps(source,texts,maps)
            part=boundary_partition(source,texts)
            if part is not None and len(texts)>1:
                mode='BOUNDARY_ONLY';maps,boundaries=part
            else:
                mode='ASSEMBLED_SINGLE' if len(texts)==1 else 'ASSEMBLED_MULTI'
            if not boundaries:
                boundaries=[{'after_stage':i,'source_span':None,'old_text':None,'new_text':'\n','origin':'new_assembly_boundary'} for i in range(len(texts)-1)]
            instruction=source.prefix+'\n'.join(texts)+source.suffix
    if c['status']=='ok':
        cursor=0 if mode=='SOURCE_EXACT' else len(source.prefix)
        for i,t in enumerate(c['subtasks']):
            end=cursor+len(t)
            stage_spans.append({'index':i,'char_start':cursor,'char_end':end,
                                'utf8_start':len(instruction[:cursor].encode()),'utf8_end':len(instruction[:end].encode())})
            cursor=end+(1 if i<len(c['subtasks'])-1 else 0)
    plan={'mode':mode,'source_sha256':source.source_sha256,'source_prefix':source.prefix,'source_suffix':source.suffix,
          'source_body_span':[source.body_start,source.body_end],'stage_maps':maps,'stage_boundaries':boundaries,
          'stage_spans':stage_spans,'ledger':ledger,'policy':POLICY,
          'unmapped_edit_regions':sum(op['kind']=='EDIT' for st in maps for op in st),
          'mapping_semantics':'Exact-span and unique-token-run mappings establish surface correspondence ONLY. Not author intent, event identity, route entailment or runtime completion.'}
    fields={'task_identity_sha256':source.record_identity_sha256,'source_sha256':source.source_sha256,
            'input_candidate_sha256':sha_obj(inp),'candidate_json':canonical_json(c),'candidate_sha256':sha_obj(c),
            'instruction':instruction,'instruction_sha256':sha_text(instruction),'mode':mode,
            'policy_sha256':POLICY_SHA,'plan_json':canonical_json(plan)}
    frozen=FrozenCandidate(**fields,freeze_sha256=sha_obj(fields));frozen.verify();return frozen

def bind_review(source: SourceRecord, frozen: FrozenCandidate, report: dict[str,Any], *,
                request_id: str, review_prompt_sha256: str) -> dict[str,Any]:
    """Host binds an actually returned report; it does not generate that report."""
    frozen.verify();_source_matches(source,frozen);validate_review(source.original_instruction,frozen.candidate(),report)
    require(bool(request_id) and bool(review_prompt_sha256),'review request/prompt identity required')
    receipt={'task_identity_sha256':source.record_identity_sha256,'source_sha256':frozen.source_sha256,
             'candidate_sha256':frozen.candidate_sha256,'instruction_sha256':frozen.instruction_sha256,
             'freeze_sha256':frozen.freeze_sha256,'review_prompt_sha256':review_prompt_sha256,
             'request_id':request_id,'report':deepcopy(report),'report_sha256':sha_obj(report)}
    receipt['receipt_sha256']=sha_obj(receipt);return receipt

def commit(source: SourceRecord, frozen: FrozenCandidate, receipt: dict[str,Any], *,
           expected_review_prompt_sha256: str) -> dict[str,Any]:
    frozen.verify();_source_matches(source,frozen)
    r=deepcopy(receipt);signature=r.pop('receipt_sha256',None)
    require(signature==sha_obj(r),'review receipt altered')
    for k,val in [('task_identity_sha256',source.record_identity_sha256),('source_sha256',frozen.source_sha256),('candidate_sha256',frozen.candidate_sha256),('instruction_sha256',frozen.instruction_sha256),('freeze_sha256',frozen.freeze_sha256)]:
        require(r.get(k)==val,'stale or cross-record review receipt: '+k)
    require(r['review_prompt_sha256']==expected_review_prompt_sha256,'review prompt version mismatch')
    require(sha_obj(r['report'])==r['report_sha256'],'review report modified')
    validate_review(source.original_instruction,frozen.candidate(),r['report'])
    require(r['report']['verdict']=='pass' and frozen.candidate()['status']=='ok','only passed candidate can be committed')
    return {'state':'accepted_source_exact' if frozen.mode=='SOURCE_EXACT' else 'accepted_candidate',
            'mode':frozen.mode,'instruction':frozen.instruction,'instruction_sha256':frozen.instruction_sha256,
            'source_sha256':source.source_sha256,'candidate_sha256':frozen.candidate_sha256,'freeze_sha256':frozen.freeze_sha256,
            'review_receipt_sha256':signature,'semantic_correctness_verified':False,'navigation_evaluated':False}

def fallback(source: SourceRecord, reason: str) -> dict[str,Any]:
    require(bool(reason),'fallback reason must distinguish technical vs source vs final-review failures')
    return {'state':'fallback_'+reason,'mode':'SOURCE_EXACT','instruction':source.original_instruction,
            'instruction_sha256':source.source_sha256,'source_sha256':source.source_sha256,
            'reason':reason,'semantic_correctness_verified':False,'navigation_evaluated':False}
