"""Authored audit policy for the existing eight verified training lessons.

These are offline teaching annotations, not new route facts. Expected stationary
end placement is distinguished from a narrated intermediate state. A missing
specification fails rather than defaulting every ending to no stop.
"""
from __future__ import annotations
import copy
from tools.rxr_diagnostic_repairs import mapped_quote
from tools.rxr_positive_repairs import evidence,field

STOP_SCOPES={
    'correction':('none','none'),
    'repetition':('none','none'),
    'paired-choice':('terminal',),
    'ordinal-origin':('none',),
    'bounded-placement':('none','terminal'),
    'return-history':('none','none','terminal'),
    'conditional-viewpoint':('none','terminal'),
    'late-description':('none','none'),
}


def build_diagnostic(case,reviewer):
    diagnostic=copy.deepcopy(reviewer)
    diagnostic['template_id']='RxR-DIAG-TRAIN-'+case['id']
    diagnostic['pair_id']=None
    diagnostic['provenance']['kind']='authored_single_defect_training_diagnostic'
    diagnostic['provenance']['candidate_corruption_is_authored_not_model_output']=True
    mutation=case['mutation'];i=mutation['stage'];old=mutation['old'];new=mutation['new']
    stages=diagnostic['review_input']['candidate']['subtasks'];before=stages[i]
    if before.count(old)!=1 or old==new: raise ValueError('A training mutation must change exactly one declared span')
    start=before.index(old);stages[i]=before.replace(old,new,1);after=stages[i]
    audit=diagnostic['expected_review'];changed=[]
    for c in audit['source_coverage']:
        hit=False
        for ev in c['candidate_evidence']:
            if ev['subtask_index']!=i: continue
            q,touched,_=mapped_quote(before,after,ev['quote'],start,old,new)
            if not q: raise ValueError('Authored training mutation unexpectedly removes complete evidence')
            ev['quote']=q;hit |= touched
        if hit:
            c['status']='altered_or_missing';changed.append(c['requirement_id'])
    expected_id=audit['source_coverage'][mutation['requirement']]['requirement_id']
    if expected_id not in changed: raise ValueError('The declared training requirement did not change')
    check=audit['stage_checks'][i];check['status']='gap'
    check['source_requirement_ids']=list(dict.fromkeys(check['source_requirement_ids']+changed))
    for key in ('entry','target','process','ending','conditions'):
        obj=check[key];mapped=[];hit=False
        for q in obj['candidate_quotes']:
            nq,touched,_=mapped_quote(before,after,q,start,old,new)
            mapped.append(nq);hit |= touched
        obj['candidate_quotes']=mapped
        if hit:
            obj['text']='Source requires '+old+'; candidate instead states '+new+'. '+mutation['problem']
    check['process']=field('The actual candidate retains the other ordered actions but contains this source-relative defect: '+mutation['problem'],after)
    affected=[i];cross_gap=False
    for handoff in audit['handoffs']:
        for key,index_key in (('preceding_exit','from_subtask_index'),('next_entry','to_subtask_index')):
            if handoff[index_key]!=i: continue
            q,touched,_=mapped_quote(before,after,handoff[key]['candidate_quote'],start,old,new)
            handoff[key]['candidate_quote']=q
            if touched:
                handoff[key]['text']='The candidate now says '+new+' rather than the source-supported '+old+'.'
        if case['id']=='return-history' and handoff['from_subtask_index']==i:
            cross_gap=True
            # The mutation also changes the identity of the bedroom being
            # inherited, not the literal existence of every later movement.
            bedroom=audit['source_coverage'][3]
            bedroom['status']='altered_or_missing'
            changed.append(bedroom['requirement_id'])
            handoff['status']='gap'
            handoff['source_requirement_ids']=list(dict.fromkeys(handoff['source_requirement_ids']+changed))
            handoff['shared_context']=[dict(kind='inherited_context',text='The source requires return through the identified original doorway. The candidate chooses another doorway; it cannot certify the same bedroom entry for the next leg.')]
            handoff['handoff_rationale']='Restore the identified return event; generic bedroom wording is not proof of the required route-history identity.'
            successor=audit['stage_checks'][i+1]
            successor['status']='gap'
            successor['entry']['text']='The following leg expects the bedroom established by the original return. That identity is unsupported after the candidate chooses another doorway.'
            successor['source_requirement_ids']=list(dict.fromkeys(successor['source_requirement_ids']+changed))
            affected.append(i+1)
    for h in audit['handoffs']:
        if h['status']=='supported':
            h['handoff_rationale']='This boundary retains its source-supported exit and entry. The local diagnostic defect does not erase unrelated continuity or cancel any explicit source stop.'
    cc={'UNSUPPORTED_ADDITION':'C02','WRONG_REFERENCE_FRAME':'C06','WRONG_RELATION':'C06','COUNT_SCOPE_DRIFT':'C07','WRONG_TARGET':'C05'}
    if case['id']=='correction': cc['WRONG_REFERENCE_FRAME']='C03'
    if case['id']=='return-history': cc['WRONG_TARGET']='C07'
    related=['closure_handoff'] if cross_gap else []
    finding=dict(code=mutation['code'],failed_layer='L2_dependencies',c_check=cc[mutation['code']],
        dimension='source_fidelity',related_dimensions=related,affected_subtask_indices=affected,
        source_requirement_ids=list(dict.fromkeys(changed)),source_quote=case['coverage'][mutation['requirement']][0],
        candidate_evidence=[evidence(stages,i,new)],evidence_level='S1',problem=mutation['problem'],
        execution_consequence=mutation['consequence'],repair=dict(operation='restore',affected_subtask_indices=[i],
            instruction=f'Restore {old!r} in place of {new!r}; preserve unaffected route text and rebuild only the affected evidence and dependencies.',
            protected_requirements=['Preserve unaffected actions, relations, quantities and event order.',case['lesson']]))
    audit['verdict']='revise'
    audit['dimensions']={d:'issue' if d=='source_fidelity' or d in related else 'pass' for d in ('source_fidelity','closure_handoff','segmentation_adequacy')}
    audit['findings']=[finding]
    for layer in audit['layer_checks']:
        if layer['layer'] in ('L1_source_coverage','L2_dependencies','L3_stage_checks','L6_route_readback') or (cross_gap and layer['layer']=='L4_handoffs'):
            layer.update(status='issue',finding_indices=[0],conclusion=mutation['problem']+(' The changed return identity also affects the next entry.' if cross_gap and layer['layer']=='L4_handoffs' else ''))
        else: layer['finding_indices']=[]
    diagnostic['teaching_notes']=dict(review_pattern=case['pattern'],review_principle=mutation['problem'],
        case_specific_focus=mutation['problem']+' '+mutation['consequence'],
        anti_pattern='Do not keep old correct-state explanations after replacing their evidence. Diagnose the actual changed event and preserve unrelated coverage and handoffs.')
    return diagnostic
