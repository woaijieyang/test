from __future__ import annotations
from typing import Any
from jsonschema import Draft202012Validator
from .common import ROOT, ContractError, read_json, require, quote_in

def schema(value: Any, relative: str) -> None:
    validator = Draft202012Validator(read_json(ROOT / relative))
    errors = list(validator.iter_errors(value))
    if errors:
        raise ContractError('; '.join(f'{list(e.absolute_path)}: {e.message}' for e in errors[:5]))

def candidate(source: str, value: dict[str, Any]) -> None:
    schema(value, 'generator/output.schema.json')
    subs = value['subtasks']
    if value['status'] == 'ok':
        require(bool(subs) and not value['issues'], 'ok requires nonempty subtasks and empty issues')
        require(all(isinstance(s, str) and bool(s.strip()) for s in subs), 'all subtasks must be nonblank')
        # Source-native newlines and multiple spaces are handled by provenance, not rejected here.
    else:
        require(not subs and bool(value['issues']), 'needs_review requires no speculative subtasks and nonempty issues')
    for item in value['issues']:
        quote_in(item['source_quote'], source, 'generator issue')
        require(bool(item['problem'].strip()), 'empty source issue')

def review(source: str, proposed: dict[str, Any], value: dict[str, Any]) -> None:
    candidate(source, proposed)
    schema(value, 'reviewer/output.schema.json')
    texts = proposed['subtasks']; n = len(texts)
    require([s['subtask_index'] for s in value['stage_checks']] == list(range(n)), 'stage checks must cover every actual candidate stage once')
    for s in value['stage_checks']:
        i=s['subtask_index']
        require(bool(s['source_quotes']) and bool(s['candidate_quotes']), 'stage checks need source AND actual candidate evidence')
        for q in s['source_quotes']:quote_in(q,source,'stage source')
        for q in s['candidate_quotes']:quote_in(q,texts[i],'stage candidate')
        if s['completion_basis']=='source_unspecified':
            require(s['completion_condition'] is None, 'source_unspecified may not invent a completion')
        if s['status']=='supported':
            require(isinstance(s['entry_context'],str) and bool(s['entry_context'].strip()), 'supported stage needs a meaningful entry context')
            require(s['completion_condition'] is not None and bool(s['completion_condition'].strip()),'supported stage has no ending')
            require(s['completion_basis'] not in {'source_unspecified','not_supported_by_source'},'unsupported ending marked supported')
            require(bool(s['required_history']), 'supported stage lacks its prescribed process')
    require([(b['previous_index'],b['next_index']) for b in value['boundary_checks']] == [(i,i+1) for i in range(max(0,n-1))], 'all adjacent handoffs must be checked once')
    for b in value['boundary_checks']:
        require(bool(b['completion_evidence']) and bool(b['previous_candidate_quotes']) and bool(b['next_candidate_quotes']), 'handoff requires source and both candidate sides')
        for q in b['completion_evidence']:quote_in(q,source,'boundary source')
        for q in b['previous_candidate_quotes']:quote_in(q,texts[b['previous_index']],'boundary previous')
        for q in b['next_candidate_quotes']:quote_in(q,texts[b['next_index']],'boundary next')
        if b['status']=='supported':require(bool(b['previous_exit']) and bool(b['next_required_entry']), 'supported handoff needs exit and next entry')
    findings=value['findings']; ids=[f['finding_id'] for f in findings]
    require(len(ids)==len(set(ids)), 'duplicate finding IDs')
    for f in findings:
        ii=f['subtask_indices'];require(len(ii)==len(set(ii)) and all(0<=i<n for i in ii),'invalid finding indices')
        require(bool(f['source_quotes']), 'findings need exact source evidence')
        for q in f['source_quotes']:quote_in(q,source,'finding source')
        for q in f['candidate_quotes']:
            i=q['subtask_index'];require(0<=i<n and i in ii,'candidate quote not in affected stage')
            quote_in(q['quote'],texts[i],'finding candidate')
        require(f['check_id'] not in f['related_check_ids'] and f['dimension'] not in f['related_dimensions'], 'duplicate primary/related evidence fields')
        if f['severity']=='material':
            for cid in [f['check_id']]+f['related_check_ids']:
                require(value['checklist'][cid] in {'issue','source_limited'},'material finding not reflected in checklist')
    material=[f for f in findings if f['severity']=='material']
    q=value['quality']
    if value['verdict']=='pass':
        require(proposed['status']=='ok' and not material,'pass contains unresolved material findings or empty source-limited candidate')
        require(q=={'fidelity':'supported','closure_handoff':'supported','segmentation_adequacy':'adequate'},'pass conflicts with quality dimensions')
        require(all(s['status']=='supported' for s in value['stage_checks']),'pass conflicts with stage status')
        require(all(b['status']=='supported' for b in value['boundary_checks']),'pass conflicts with boundary status')
        require(all(x in {'pass','not_applicable'} for x in value['checklist'].values()),'pass conflicts with checklist')
    else:
        require(bool(material),'non-pass requires material finding')
        if value['verdict']=='unresolved':
            require(any('source_limit' in [f['dimension']]+f['related_dimensions'] for f in material),'unresolved must identify ORIGINAL source limitation')
            require('source_limited' in q.values(),'unresolved contradicts quality summary')
        if value['verdict']=='revise':
            require(any(f['dimension']!='source_limit' for f in material),'revise requires a repairable candidate problem, not only a source limitation')
    for dim in ['fidelity','closure_handoff','segmentation_adequacy']:
        bad=q[dim] in {'issue','undersegmented','oversegmented'}
        if bad:require(any(dim in [f['dimension']]+f['related_dimensions'] and f['severity']=='material' for f in findings),'failed dimension missing material evidence')

    for cid,result in value['checklist'].items():
        if result in {'issue','source_limited'}:
            require(any(cid in [f['check_id']]+f['related_check_ids'] for f in material), 'checklist issue has no material evidence')
    for st in value['stage_checks']:
        if st['status']!='supported':
            require(any(st['subtask_index'] in f['subtask_indices'] or f['dimension']=='source_limit' for f in material), 'unsupported stage lacks located finding')
    for boundary in value['boundary_checks']:
        if boundary['status']!='supported':
            require(any(set(f['subtask_indices']) & {boundary['previous_index'],boundary['next_index']} or f['dimension']=='source_limit' for f in material), 'broken handoff lacks located finding')

def repair(source: str, feedback: dict[str, Any], value: dict[str, Any]) -> None:
    schema(value,'generator/repair.schema.json');candidate(source,value['candidate'])
    want={f['finding_id'] for f in feedback['findings']}; got=[x['finding_id'] for x in value['feedback_response']]
    require(len(got)==len(set(got)) and set(got)==want,'each finding needs exactly one independent decision')
    for d in value['feedback_response']:
        require(bool(d['source_quotes']),'feedback decision lacks evidence')
        for q in d['source_quotes']:quote_in(q,source,'repair decision')
