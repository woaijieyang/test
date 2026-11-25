"""Small explicitly synthetic contrast set; no benchmark instructions or IDs.

These examples teach branching and route-history semantics, NOT measured
navigation performance. Source text is immutable under the addition manifest.
"""
from copy import deepcopy
from r2r_authoring.positive import field
from r2r_authoring.review import levels, make_finding, AXES

BRANCH='If the doorway on your left is open, enter it and stop just inside. Otherwise, go to the doorway on your right and stop in its threshold.'
RETURN='Leave the doorway, walk around the table, then return to the same doorway and wait there.'
BRANCH_NEG='If the hallway on your left is open, go through it and stop at its end. Otherwise, enter the room on your right and wait just inside.'
RETURN_NEG='Walk away from the doorway to the bench. Return to the same doorway and wait.'


def identity(name):
    return dict(split='authored_synthetic',role='teaching',record_id=name,
                episode_id=None,instruction_id=None,scene_id=None,trajectory_id=None,
                source_key='R2R|authored_synthetic|'+name)


def envelope(role,tid,name,lesson,skills):
    return dict(schema_version=role+'-v1.5.1-template',template_id=tid,role=role,
        dataset_scope='R2R',language='en',source=identity(name),
        provenance=dict(source_type='authored_synthetic',is_official_dataset_record=False,
            derivation='Hand-authored semantic contrast, not copied from an evaluation episode.',
            navigation_ground_truth=False),
        teaching_notes=dict(case_rationale=lesson,case_specific_focus=lesson,decision_reason=lesson,
            reusable_rule=lesson,transfer_rule=lesson,review_principle=lesson,
            primary_skills=skills,counter_example_boundary='A source prescribing unconditional sequential visits is different; compare the actual source relations.',
            why_this_case_matters=lesson),retrieval_tags=skills)


def stage(text,target,ending,conditions,source):
    return dict(subtask_index=0,entry=dict(mode='episode_start',text='Start at the source episode position; no observed completion is assumed.',candidate_quotes=[]),
        target=field(*target),process=field('Execute only the ordered or conditional process explicitly stated in this source.',text),
        ending=dict(kind='explicit_event',text=ending[0],candidate_quotes=list(ending[1:]),stop_scope='terminal'),
        conditions=field(conditions[0],*conditions[1:]),source_quotes=[source],carryover=[])


def review(source,candidate,audit,requirements):
    cov=[dict(requirement_id=f'SRC-{i+1:02d}',source_quote=sq,requirement=req,
        candidate_evidence=[dict(subtask_index=0,quote=q) for q in quotes],status=status)
        for i,(sq,req,quotes,status) in enumerate(requirements)]
    audit=deepcopy(audit);audit.update(status='supported',source_requirement_ids=[c['requirement_id'] for c in cov],source_quotes=[c['source_quote'] for c in cov])
    out=dict(verdict='pass',dimensions={d:'pass' for d in AXES},source_coverage=cov,
        layer_checks=[],findings=[],stage_checks=[audit],handoffs=[],prior_finding_reviews=[])
    levels(out,{},1)
    return out


def examples():
    rows={}
    specs=[(36,'conditional-door',BRANCH,['branch','attribute','entry','terminal'],
        'Keep executable alternatives mutually exclusive. Each branch includes its own source-specified stop; the closed-door case does not authorize opening or entering the left doorway.',
        ('The selected doorway and branch-specific final position.','the doorway on your left','the doorway on your right'),
        ('The selected branch ends at its own explicitly stated stopping position.','stop just inside','stop in its threshold'),
        ('Openness selects the left branch; otherwise selects the right branch.','If the doorway on your left is open','Otherwise'),
        [(BRANCH.split(' Otherwise')[0],'Execute the left-doorway branch only when that doorway is open.',[BRANCH.split(' Otherwise')[0]],'covered'),('Otherwise, go to the doorway on your right and stop in its threshold.','Use the right doorway and its threshold only in the alternative branch.',['Otherwise, go to the doorway on your right and stop in its threshold.'],'covered')]),
      (37,'return-loop',RETURN,['return','scope','terminal'],
        'Returning to the same doorway requires the departure and intervening table circuit; matching the initial and final place does not execute the excursion.',
        ('The original doorway revisited after the table circuit.','return to the same doorway'),
        ('Wait at the original doorway only after the departure, table circuit and return.','return to the same doorway and wait there'),
        ('Preserve the intervening travel and the identity of the revisited doorway.','Leave the doorway','walk around the table','then return to the same doorway'),
        [('Leave the doorway, walk around the table','Perform the departure and table circuit before returning.',['Leave the doorway, walk around the table'],'covered'),('then return to the same doorway and wait there.','Revisit the original doorway after the excursion and wait.',['then return to the same doorway and wait there.'],'covered')])]
    for n,name,source,skills,lesson,target,end,conds,requirements in specs:
        g=envelope('generator',f'R2R-GEN-{n:03d}',name,lesson,skills)
        a=stage(source,target,end,conds,source)
        g.update(input=dict(original_instruction=source),decision=dict(status='ok',mode='keep',rationale=lesson),
            output=dict(status='ok',subtasks=[source],stage_audit=[a],handoffs=[],issues=[]))
        # Reviewer uses its own event inventory and source-supported target/ending.
        r=envelope('reviewer',f'R2R-REV-{n:03d}',name,lesson,skills)
        r.update(pair_id=g['template_id'],review_input=dict(original_instruction=source,candidate=dict(status='ok',subtasks=[source])),
                 expected_review=review(source,[source],stage(source,target,end,conds,source),requirements))
        rows[f'generator/templates/R2R/authored/{n:03d}_{g["template_id"]}.json']=g
        rows[f'reviewer/templates/R2R/authored/{n:03d}_{r["template_id"]}.json']=r
    source=BRANCH_NEG;candidate='Go through the hallway on your left and stop at its end. Then enter the room on your right and wait just inside.'
    lesson='Removing if/otherwise converts mutually exclusive alternatives into two mandatory routes and an extra intermediate stop.'
    r=envelope('reviewer','R2R-DIAG-30','conditional-hall-contrast',lesson,['branch','entry','terminal'])
    audit=stage(candidate,('The candidate wrongly requests both regions.','the hallway on your left','the room on your right'),
        ('The candidate retains the final right-room wait but also executes a stop from a mutually exclusive branch.','wait just inside'),
        ('The candidate unconditionally sequences both branches.','Then enter the room on your right'),source)
    a=review(source,[candidate],audit,[(source.split(' Otherwise')[0],'Condition the left-hall traversal and its stop on openness.',['Go through the hallway on your left and stop at its end.'],'altered_or_missing'),
        ('Otherwise, enter the room on your right and wait just inside.','Execute the right-room branch only otherwise.',['Then enter the room on your right and wait just inside.'],'altered_or_missing')])
    f=make_finding('DETACHED_CONDITION','L2_dependencies','C04','source_fidelity',['SRC-01','SRC-02'],source,
        [dict(subtask_index=0,quote=candidate)],lesson,
        'Restore the original if/otherwise scope so only the applicable route and its own final stop are executed. Do not add a door-opening action.',[0],['closure_handoff'],protected=['Preserve each branch destination and its stated stop/wait location.'])
    a.update(verdict='revise',dimensions=dict(source_fidelity='issue',closure_handoff='issue',segmentation_adequacy='pass'),findings=[f]);a['stage_checks'][0]['status']='gap'
    levels(a,{l:(lesson,[0]) for l in ('L1_source_coverage','L2_dependencies','L3_stage_checks','L6_route_readback')},1)
    r.update(pair_id=None,review_input=dict(original_instruction=source,candidate=dict(status='ok',subtasks=[candidate])),expected_review=a)
    rows['reviewer/templates/R2R/authored/030_R2R-DIAG-30.json']=r
    source=RETURN_NEG;candidate='Wait at the doorway.'
    lesson='The same final doorway does not justify deleting the trip to the bench and the return event.'
    r=envelope('reviewer','R2R-DIAG-31','return-bench-contrast',lesson,['return','lost_action','terminal'])
    audit=stage(candidate,('The doorway as a waiting position; the required revisit has not been executed.','the doorway'),
        ('The candidate waits but has omitted the excursion and return.','Wait at the doorway.'),
        ('The retained placement does not imply completion of the omitted travel.','at the doorway'),source)
    a=review(source,[candidate],audit,[('Walk away from the doorway to the bench.','Visit the bench after leaving the doorway.',[],'altered_or_missing'),
        ('Return to the same doorway','Return after that departure, retaining doorway identity.',[],'altered_or_missing'),
        ('and wait.','Wait at the returned-to doorway.',['Wait at the doorway.'],'covered')])
    f=make_finding('OMISSION','L2_dependencies','C01','source_fidelity',['SRC-01','SRC-02'],source,[],lesson,
        'Restore departure from the doorway to the bench and return to the same doorway before the retained wait.',[0],['closure_handoff'],protected=['Preserve the final doorway identity and wait; add no extra destination.'])
    a.update(verdict='revise',dimensions=dict(source_fidelity='issue',closure_handoff='issue',segmentation_adequacy='pass'),findings=[f]);a['stage_checks'][0]['status']='gap'
    levels(a,{l:(lesson,[0]) for l in ('L1_source_coverage','L2_dependencies','L3_stage_checks','L6_route_readback')},1)
    r.update(pair_id=None,review_input=dict(original_instruction=source,candidate=dict(status='ok',subtasks=[candidate])),expected_review=a)
    rows['reviewer/templates/R2R/authored/031_R2R-DIAG-31.json']=r
    return rows
