"""Reviewed negative-case specifications and mechanical evidence alignment.

The changes below are authored semantic contrasts, not a keyword-based judge.
The aligner maps exact unchanged bytes and the declared changed span only. It
cannot infer a verdict, a target, or an event from lexical similarity.
"""
from __future__ import annotations
import copy
from tools.rxr_positive_repairs import evidence, field

# number: (old source span, replacement, active code, checklist, explanation,
#          possible consequence, final source evidence, final kind, stop scope)
LOCAL = {
1: ('first row of stairs','second row of stairs','COUNT_SCOPE_DRIFT','C07',
    'The explicit first-row selection is changed to the second row.',
    'This changes the ordinal constraint; it does not prove which physical row a navigator will choose.',
    'take a step into the little crawlspace next to the painting. Stop.','explicit_event','terminal'),
2: ('see a staircase to your right','see a staircase to your left','WRONG_REFERENCE_FRAME','C06',
    'The staircase observation is moved from the right to the left. The later rightward hop and other right-side cues are unchanged.',
    'The altered observation can identify the wrong staircase or viewpoint.',
    'stop once you have reached the spot with the navy curtains on your right','explicit_event','terminal'),
3: ('enter into the bedroom','approach the bedroom without entering it','WRONG_RELATION','C06',
    'The required bedroom entry is replaced by an approach that explicitly excludes entry.',
    'This contradicts the required traversal and the subsequent bedroom-relative route.',
    'Stand in front of that shredder and you are done.','explicit_event','terminal'),
4: ('on the right side of the pool table','on the right side of the pool','WRONG_TARGET','C05',
    'The expected reference is a pool table, not a pool. This is an entity change, not an omitted decorative word.',
    'The next bounded step can be interpreted from a different reference object.',
    "Take another step forward towards the railing and you're done.",'bounded_action','none'),
5: ("We're facing towards a wooden door and in the opposite side of it there are some switches of some sort, turn slightly to the left, and walk towards the hallway that's in front of you... ",'','OMISSION','C01',
    'The initial facing context, slight left turn and hallway approach have been removed.',
    'The remaining route starts at later landmarks without prescribing the initial transition.',
    'once you\'re facing that shelf, you have reached your destination.','explicit_event','none'),
6: ("After you reach an open door, walk into the bathroom that's in front of you","Before you reach an open door, walk into the bathroom that's in front of you",'WRONG_ORDER','C03',
    'Bathroom entry is moved before reaching the open door instead of after it. A real dependency is reversed; a connective is not merely omitted.',
    'The candidate requires the dependent entry before its source-supported trigger.',
    "take one step towards the window, and that's your destination.",'bounded_action','none'),
7: ('And this is where we will stop.','Continue past this position.','UNSUPPORTED_ADDITION','C11',
    'An explicit final stop is replaced by an instruction to continue past that position.',
    'The candidate no longer preserves the stated stopping position.',
    'And this is where we will stop.','explicit_event','terminal'),
8: ("Don't pass the couch.",'Pass the couch.','DETACHED_CONDITION','C04',
    'The prohibition on passing the identified red couch is reversed into a command to pass it.',
    'The prescribed left turn can be taken from beyond the source-permitted location.',
    "You'll actually be standing right in front of the double doors, next to the TV.",'explicit_event','terminal'),
9: ('Facing straight down the hardwood floor hallway','Facing back along the hardwood floor hallway','WRONG_REFERENCE_FRAME','C06',
    'The viewpoint before the left turn to the stairs is reversed along the hallway.',
    'The same left-turn words now use a different source-specified heading.',
    'Walk just past the American flag and stand next to the clock on your left.','explicit_event','terminal'),
10: ('Exit that door.','Exit another door.','WRONG_TARGET','C07',
     'The exit is changed from the previously identified left-hand door by the shelf to another door.',
     'The antecedent identity is lost even though the sentence remains grammatical.',
     'just step inside that bathroom next to the grey door and you are done.','bounded_action','none'),
11: ('first door opening','second door opening','COUNT_SCOPE_DRIFT','C07',
     'The first door-opening selection is changed to the second; the later next-opening clause is unchanged.',
     'The stated ordinal selection is no longer preserved.',
     'This will be your stopping point.','explicit_event','terminal'),
12: ('enter the first door to your right','enter the first door to your left','WRONG_REFERENCE_FRAME','C06',
     'The side of the first door selected at the gallery entrance is reversed. Right in front of earlier double doors remains unchanged and is an intensifier.',
     'The candidate selects a door on the opposite side from the required viewpoint.',
     "once you're halfway up the staircase, and staring directly in front of a white wall.",'bounded_action','none'),
13: ('go through it.','go past it without entering.','WRONG_RELATION','C06',
     'The identified open door must be traversed, not passed without entering.',
     'The required hallway entry is contradicted by the replacement transition.',
     'stand at the thresh hole of that doorway.','explicit_event','terminal'),
14: ('In the hallway with the black leather chair with metal arms','In the bedroom with the black leather chair with metal arms','WRONG_RELATION','C06',
     'The source initial hallway context is changed into a bedroom while the chair description is retained.',
     'The bathroom selection is now referenced to an unsupported starting region.',
     'Step in front of the toilet with the sink to your left.','explicit_event','none'),
15: ('Turn around and take a right into the bathroom, and take another right into a hallway that leads to the toilet. ','','OMISSION','C01',
     'The turn-around, bathroom entry and subsequent hallway turn are omitted.',
     'Preserving the final bidet placement does not preserve the required intermediate route.',
     "Stand in front of the bidet, and you're done.",'explicit_event','terminal'),
16: ("Once you're on the hallway and facing the arched opening. Turn left","Before you're on the hallway and facing the arched opening, turn left",'WRONG_ORDER','C03',
     'The left turn is commanded before rather than after the established hallway-facing state.',
     'The dependent turn no longer uses the source-supported entry state.',
     "Once you're standing in front of the sink then you're done.",'explicit_event','terminal'),
17: ('This is where you will stop.','Continue past this bathtub.','UNSUPPORTED_ADDITION','C11',
     'The explicit stop at the pink bathtub is replaced by additional movement past it.',
     'The terminal stop is no longer preserved; earlier handoffs are not implicated.',
     'This is where you will stop.','explicit_event','terminal'),
18: ('Oh, that is not a bathroom, that is an area behind a bar, excuse me.',
     'Oh, that is a bathroom, not an area behind a bar.','WRONG_TARGET','C03',
     'The local correction of bathroom to behind-bar area is reversed. The aesthetic not great to look upon phrase is unchanged and is not a movement prohibition.',
     'The candidate contradicts the corrected destination identity and its following behind-bar context.',
     "Continue until you are behind the right-most bar stool, and you're done.",'explicit_event','none'),
19: ("We're facing the living room area.","We're facing away from the living room area.",'WRONG_REFERENCE_FRAME','C06',
     'The initial facing relation is reversed, not merely restyled or left implicit.',
     'Subsequent right-side chair selection uses an unsupported initial frame.',
     "Let's get closer to the right one and we can just stop here.",'explicit_event','terminal'),
20: ('Go inside that door from here.','Go inside another door from here.','WRONG_TARGET','C07',
     'The late bedroom-entry command replaces the door identified through the wooden sliding door with another door. The earlier island antecedent remains intact.',
     'The candidate abandons the source-supported referent at this particular later entry event.',
     "And you should end up next to a Campbell's tomato soup painting, and a dog bed. If you're in that corner you're done.",'explicit_event','none'),
}


def mapped_quote(source, candidate, quote, start, old, new, *, after=0):
    """Map a source occurrence through one explicitly authored span edit."""
    positions=[]; pos=source.find(quote,after)
    while pos>=0:
        positions.append(pos); pos=source.find(quote,pos+1)
    if not positions:
        raise ValueError(f'Cannot locate source occurrence: {quote!r}')
    pos=positions[0]; end=pos+len(quote); cut_end=start+len(old); shift=len(new)-len(old)
    changed=pos<cut_end and end>start
    left=pos if pos<=start else (pos+shift if pos>=cut_end else start)
    right=end if end<=start else (end+shift if end>=cut_end else start+len(new))
    projected=candidate[left:right]
    if not changed and projected!=quote:
        raise ValueError('Unchanged source mapping drifted')
    return projected,changed,pos


def single_diagnostic(row, number):
    old,new,code,cc,problem,consequence,endpoint,kind,stop=LOCAL[number]
    src=row['review_input']['original_instruction']
    if src.count(old)!=1: raise ValueError(f'{number}: authored mutation not unique: {old!r}')
    start=src.index(old); cand=src.replace(old,new,1)
    if cand==src: raise ValueError('Diagnostic mutation must change the candidate')
    if endpoint not in src: raise ValueError(f'{number}: ending evidence absent')
    previous=row['expected_review']['source_coverage']
    coverage=[]; changed_ids=[]; cursor=0
    for item in previous:
        q=item['source_quote']
        # Existing rows may overlap (a trigger followed by the containing event).
        # Their full quotes are retained; ordered lookup disambiguates repeats.
        projected,changed,pos=mapped_quote(src,cand,q,start,old,new,after=cursor)
        cursor=pos
        rid=item['requirement_id']
        coverage.append(dict(requirement_id=rid,source_quote=q,
            requirement=(problem if changed else 'Preserve the cited source event or context, with its local referent, order and qualifiers unchanged.'),
            candidate_evidence=([evidence([cand],0,projected)] if projected else []),
            status=('altered_or_missing' if changed and projected else 'omitted' if changed else 'covered')))
        if changed: changed_ids.append(rid)
    # A full contextual mutation quote is explicit even when old coverage had
    # only a short word or omitted the relevant event.
    rid='SRC-CHANGE'
    coverage.append(dict(requirement_id=rid,source_quote=old,requirement=problem,
        candidate_evidence=([evidence([cand],0,new)] if new else []),
        status='altered_or_missing' if new else 'omitted'))
    changed_ids.append(rid)
    end_quote,end_changed,_=mapped_quote(src,cand,endpoint,start,old,new)
    endtext=('Source ending: '+endpoint+' Candidate instead states: '+new if end_changed else
             'The candidate retains the source ending: '+endpoint)
    ending=dict(kind='unspecified' if end_changed else kind,text=endtext,
                candidate_quotes=[end_quote] if end_quote else [],stop_scope='none' if end_changed else stop)
    process='The actual candidate preserves the surrounding source sequence except for this identified defect: '+problem
    affected_field=field('Source requires '+old+'; candidate '+('instead states '+new if new else 'omits that span')+'.',new) if new else field('The source span is absent from the candidate: '+old)
    # The defect is local. Completion can remain valid even with a process,
    # context or frame defect; no nonexistent inter-stage gap is fabricated.
    stage=dict(subtask_index=0,status='gap',
        entry=dict(mode='episode_start',text='Start in the source-described episode context; any altered initial cue is identified below, not silently repaired.',candidate_quotes=[]),
        target=field(endtext, *ending['candidate_quotes']),
        process=field(process,cand),ending=ending,conditions=affected_field,
        source_requirement_ids=[c['requirement_id'] for c in coverage],
        source_quotes=list(dict.fromkeys(c['source_quote'] for c in coverage)),carryover=[])
    from host.protocol import LAYERS
    layer_checks=[]
    for layer in LAYERS:
        issue=layer in ('L1_source_coverage','L2_dependencies','L3_stage_checks','L6_route_readback')
        notapp=layer in ('L0_integrity','L4_handoffs')
        conclusion=(problem if issue else 'No rendered artifact is supplied.' if layer=='L0_integrity' else
                    'There is one candidate stage, so there is no inter-stage handoff.' if layer=='L4_handoffs' else
                    'No additional grouping defect is asserted merely from length or the diagnostic label.')
        layer_checks.append(dict(layer=layer,status='not_applicable' if notapp else 'issue' if issue else 'pass',finding_indices=[0] if issue else [],conclusion=conclusion))
    finding=dict(code=code,failed_layer='L2_dependencies',c_check=cc,dimension='source_fidelity',related_dimensions=[],
        affected_subtask_indices=[0],source_requirement_ids=list(dict.fromkeys(changed_ids)),source_quote=old,
        candidate_evidence=[evidence([cand],0,new)] if new else [],evidence_level='S1',problem=problem,
        execution_consequence=consequence,repair=dict(operation='restore',affected_subtask_indices=[0],
        instruction='Restore the cited source meaning at this occurrence; preserve all unaffected route text and do not add STOP or a new endpoint.',
        protected_requirements=['Keep all unaffected source actions, conditions, approximate quantities and event identities.','Do not reject an equivalent phrasing or another valid grouping.']))
    row['review_input']['candidate']=dict(status='ok',subtasks=[cand])
    row['expected_review']=dict(verdict='revise',dimensions=dict(source_fidelity='issue',closure_handoff='pass',segmentation_adequacy='pass'),
        source_coverage=coverage,layer_checks=layer_checks,findings=[finding],stage_checks=[stage],handoffs=[],prior_finding_reviews=[])
    row['teaching_notes']['case_specific_focus']=problem+' '+consequence
    row['teaching_notes']['anti_pattern']='Diagnose this actual local change only. A related noun, repeated word, absent connective or diagnostic label is not evidence of another error.'
    return dict(template_id=row['template_id'],basis='source_exact_except_authored_span',source_quote=old,
                replacement=new,changed_stage=0,code=code,unaffected_text_preserved=True)


# Parent-based diagnostics: preserve a reviewed positive everywhere except the
# one declared relation. The parent keeps the same original source and stages.
PARENT = {
21: (11,1,'Stop at the entrance of it.','Stop beside the fire extinguisher.',
     'Stop at the entrance of it','WRONG_TARGET','C05','L3_stage_checks',
     'The extinguisher is a nearby reference, not the prescribed restroom-entrance stopping target.',
     'The final placement changes, while the prior room-to-hallway handoff is unaffected.'),
22: (23,2,'Stop when you are at the edge of the pool.','Stop beside the potted plant.',
     'You will stop when you are at the edge of the pool.','WRONG_TARGET','C05','L3_stage_checks',
     'The pool-edge stop is replaced by stopping beside the reference plant.',
     'The plant relation does not by itself establish the required pool-edge placement.'),
23: (17,0,'stopping before we exit','going through the glass doors to the outside',
     'stopping before we exit','UNSUPPORTED_ADDITION','C11','L3_stage_checks',
     'The candidate commands crossing outside where the source requires stopping before exiting and staying indoors.',
     'It contradicts the pre-exit indoor endpoint; a single local crossing error does not imply an earlier handoff gap.'),
24: (24,0,'take 2 steps towards the toilet','walk all the way to the toilet',
     'take 2 steps towards the toilet','UNSUPPORTED_ADDITION','C02','L3_stage_checks',
     'A bounded two-step approach is strengthened to travel all the way to the toilet.',
     'The source does not authorize this additional distance or arrival.'),
25: (25,0,'hop over the bench','reach the open doorway',
     'hop over the bench','LOST_EVENT','C03','L3_stage_checks',
     'The required hop over the second bench is replaced by arrival at the merely visible doorway.',
     'The bench traversal is lost and an unsupported arrival is inserted before the next approach and entry.'),
26: (6,1,'Walk straight ahead with the TV and translucent wall on your left and the dining room chairs on your right.',
     'Turn left and walk towards the dining room chairs.',
     'Walk straight ahead with the TV and translucent wall on your left and the dining room chairs on your right.',
     'WRONG_REFERENCE_FRAME','C06','L2_dependencies',
     'The maintained TV-left/chairs-right straight traversal is replaced by a left turn toward the chairs.',
     'The path relation changes; the final endpoint is between the chairs and TV, not between tables.'),
28: (25,1,'Move forward to the left and enter that doorway.','From inside that open doorway,',
     'Move forward to the left and enter that doorway.','MISSING_ENTRY_ANCHOR','C09','L4_handoffs',
     'After seeing the doorway from the post-hop position, the next stage falsely starts inside it and omits approach and entry.',
     'The entry state is unsupported. Room-description, column, tables and television clauses are otherwise retained.'),
29: (2,0,'On your right a glass window on your left','A glass window is on your left',
     'their should be a wine room on your right and on your right a glass window on your left and an open door in front of you',
     'WRONG_RELATION','C06','L2_dependencies',
     'The candidate silently resolves the conflicting auxiliary window-side description to the left.',
     'The unsupported auxiliary relation may alter orientation; the stable open-door/agent-right-bench identity and prior route are not separately broken.'),
}


def revise_parent(row, parent, spec):
    parent_number,index,old,new,source_quote,code,cc,layer,problem,consequence=spec
    src=row['review_input']['original_instruction']; stages=copy.deepcopy(parent['review_input']['candidate']['subtasks'])
    if src!=parent['review_input']['original_instruction'] or source_quote not in src:
        raise ValueError('Diagnostic source/parent mismatch')
    if stages[index].count(old)!=1: raise ValueError(f"{row['template_id']}: mutation absent {old!r}")
    before=stages[index]; start=before.index(old); stages[index]=before.replace(old,new,1)
    audit=copy.deepcopy(parent['expected_review']); changed=[]
    for c in audit['source_coverage']:
        affected=False
        for ev in c['candidate_evidence']:
            if ev['subtask_index']!=index: continue
            q,hit,_=mapped_quote(before,stages[index],ev['quote'],start,old,new)
            ev['quote']=q
            affected |= hit
        if affected:
            c['status']='altered_or_missing';changed.append(c['requirement_id'])
    changeid='SRC-CHANGE'
    audit['source_coverage'].append(dict(requirement_id=changeid,source_quote=source_quote,requirement=problem,
        candidate_evidence=[evidence(stages,index,new)],status='altered_or_missing'))
    changed.append(changeid)
    # Never preserve a positive description while only swapping its quote.
    check=audit['stage_checks'][index];check['status']='gap'
    check['source_requirement_ids']=list(dict.fromkeys(check['source_requirement_ids']+changed))
    for key in ('entry','target','process','ending','conditions'):
        obj=check[key]; hits=[]
        for q in obj['candidate_quotes']:
            nq,hit,_=mapped_quote(before,stages[index],q,start,old,new)
            hits.append((nq,hit))
        obj['candidate_quotes']=[q for q,_ in hits if q]
        if any(hit for _,hit in hits):
            obj['text']='Source requires '+old+'; candidate instead states '+new+'. '+problem
    check['process']=field('The stage retains its unaffected movements but contains this local defect: '+problem,stages[index])
    affected_handoffs=[]
    for h in audit['handoffs']:
        for key,side in (('preceding_exit','from_subtask_index'),('next_entry','to_subtask_index')):
            if h[side]!=index: continue
            nq,hit,_=mapped_quote(before,stages[index],h[key]['candidate_quote'],start,old,new)
            h[key]['candidate_quote']=nq
            if hit:
                h[key]['text']='The candidate endpoint/entry now states '+new+'. '+problem
        # Only the explicit premature-entry diagnostic changes this boundary's
        # required entry support; final target faults do not break prior entry.
        if row['template_id']=='RxR-DIAG-28' and h['to_subtask_index']==index:
            h['status']='gap';h['source_requirement_ids']=list(dict.fromkeys(h['source_requirement_ids']+changed))
            h['shared_context']=[{'kind':'inherited_context','text':'The previous stage only completed the bench hop and saw the door; candidate entry inside that door is unsupported.'}]
            h['handoff_rationale']=problem
            affected_handoffs.append(h)
        elif row['template_id']=='RxR-DIAG-25' and h['from_subtask_index']==index:
            # A missing prior event and invented arrival are process/fidelity
            # defects; the later actual approach/entry is not itself omitted.
            h['shared_context']=[{'kind':'inherited_context','text':'The candidate claims doorway arrival instead of the source-required bench hop. The following approach/entry text is still present; restore the prior event rather than deleting the next action.'}]
            h['handoff_rationale']='The candidate sequence can continue, but its claimed prior outcome is not source-faithful; see the localized stage finding.'
    related=['closure_handoff'] if layer in ('L3_stage_checks','L4_handoffs') else []
    audit['verdict']='revise';audit['dimensions']={d:'issue' if d=='source_fidelity' or d in related else 'pass' for d in ('source_fidelity','closure_handoff','segmentation_adequacy')}
    audit['findings']=[dict(code=code,failed_layer=layer,c_check=cc,dimension='source_fidelity',related_dimensions=related,
        affected_subtask_indices=[index],source_requirement_ids=list(dict.fromkeys(changed)),source_quote=source_quote,
        candidate_evidence=[evidence(stages,index,new)],evidence_level='S1',problem=problem,execution_consequence=consequence,
        repair=dict(operation='bind_entry' if layer=='L4_handoffs' else 'restore',affected_subtask_indices=[index],
            instruction='Restore the cited source relation at this occurrence and preserve the rest of the reviewed parent candidate.',
            protected_requirements=['Keep all unaffected events, descriptions, quantities, constraints and order.','A stage boundary neither creates a STOP nor cancels an explicit source stop.']))]
    issue_layers={'L1_source_coverage','L3_stage_checks','L6_route_readback',layer}
    for l in audit['layer_checks']:
        if l['layer'] in issue_layers:
            l.update(status='issue',finding_indices=[0],conclusion=problem)
        else:
            l['finding_indices']=[]
            if l['layer']=='L4_handoffs':
                l.update(status='pass' if audit['handoffs'] else 'not_applicable',conclusion='The existing adjacent boundaries are unchanged by this local defect.' if audit['handoffs'] else 'One stage has no adjacent handoff.')
    audit['prior_finding_reviews']=[]
    row['review_input']['candidate']=dict(status='ok',subtasks=stages)
    row['expected_review']=audit
    row['teaching_notes']['case_specific_focus']=problem+' '+consequence
    row['teaching_notes']['anti_pattern']='Do not spread a local defect to unrelated coverage rows or unchanged boundaries. Check the actual source and candidate, not the diagnostic label.'
    return dict(template_id=row['template_id'],parent_id=parent['template_id'],basis='reviewed_parent_except_authored_span',
                source_quote=source_quote,old=old,replacement=new,changed_stage=index,code=code,unaffected_text_preserved=True)


def grouping_diagnostic(row,parent):
    """One supported-placement grouping contrast, not a fabricated lexical loss."""
    stages=parent['review_input']['candidate']['subtasks'];src=row['review_input']['original_instruction']
    if src!=parent['review_input']['original_instruction'] or len(stages)!=2: raise ValueError('Grouping parent mismatch')
    joined=' '.join(stages);audit=copy.deepcopy(parent['expected_review'])
    for c in audit['source_coverage']:
        for ev in c['candidate_evidence']: ev['subtask_index']=0
    sq='do not go outside just go near and stand. Once you are standing near the open door just at the back door'
    if sq not in src: raise ValueError('Grouping source quote must be exact')
    rids=[c['requirement_id'] for c in audit['source_coverage']]
    last=copy.deepcopy(audit['stage_checks'][-1]);last['subtask_index']=0
    last['entry']=copy.deepcopy(audit['stage_checks'][0]['entry'])
    last['source_requirement_ids']=rids
    last['source_quotes']=list(dict.fromkeys(c['source_quote'] for c in audit['source_coverage']))
    last['process']=field('The candidate contains both the completed stand-near-opening objective and the subsequent route to the bed in one stage.',joined)
    last['status']='supported';last['carryover']=[]
    audit['stage_checks']=[last];audit['handoffs']=[]
    audit['verdict']='revise';audit['dimensions']=dict(source_fidelity='pass',closure_handoff='pass',segmentation_adequacy='issue')
    problem='The source completes an explicit stand-near-opening placement without going outside, then starts a distinct door/desk/bed leg. The one-stage candidate buries this supported local-objective change; the route words themselves are retained.'
    audit['findings']=[dict(code='UNDERSEGMENTED',failed_layer='L5_grouping',c_check='C10',dimension='segmentation_adequacy',related_dimensions=[],
        affected_subtask_indices=[0],source_requirement_ids=['SRC-05','SRC-06'],source_quote=sq,
        candidate_evidence=[evidence([joined],0,'Do not go outside; move near the opening and stand there.'),evidence([joined],0,'From near the open back door')],
        evidence_level='S2',problem=problem,execution_consequence='The explicit completed intermediate placement and the subsequent independent target are not given distinct local focus.',
        repair=dict(operation='regroup',affected_subtask_indices=[0],instruction='Separate after the explicit stand-near-opening placement, preserving the same English route and uncertainty. No new movement or STOP is needed.',
                    protected_requirements=['Do not go outside.','Keep the room-or-door uncertainty, desk/chair relations and final foot-of-bed state.']))]
    for l in audit['layer_checks']:
        l.pop('note',None)
        if l['layer']=='L5_grouping': l.update(status='issue',finding_indices=[0],conclusion=problem)
        elif l['layer']=='L4_handoffs': l.update(status='not_applicable',finding_indices=[],conclusion='There is currently one stage, so no existing inter-stage handoff is broken.')
        else: l.update(status='not_applicable' if l['layer']=='L0_integrity' else 'pass',finding_indices=[],conclusion='All route words are retained; the finding concerns a supported intermediate-objective grouping, not a fabricated source omission.')
    row['review_input']['candidate']=dict(status='ok',subtasks=[joined]);row['expected_review']=audit
    row['teaching_notes']['case_specific_focus']=problem
    return dict(template_id=row['template_id'],parent_id=parent['template_id'],basis='boundary_only_grouping_contrast',code='UNDERSEGMENTED',unaffected_text_preserved=True)


def repair(rows):
    records=[]
    for n in range(1,21):
        records.append(single_diagnostic(rows[f'RxR-DIAG-{n:02d}'],n))
    for n,spec in PARENT.items():
        parent=rows[f'RxR-REV-{spec[0]:03d}']
        records.append(revise_parent(rows[f'RxR-DIAG-{n:02d}'],parent,spec))
    records.append(grouping_diagnostic(rows['RxR-DIAG-27'],rows['RxR-REV-020']))
    return sorted(records,key=lambda r:r['template_id'])
