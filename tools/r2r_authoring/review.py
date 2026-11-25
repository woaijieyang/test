"""Explicit author-side repairs of actual R2R teaching defects.

These functions operate offline on fixed authored cases. They are not semantic
validators for live model output and never infer correctness from word presence.
"""
from copy import deepcopy
from tools.r2r_authoring.positive import field,evidence
LAYERS=('L0_integrity','L1_source_coverage','L2_dependencies','L3_stage_checks','L4_handoffs','L5_grouping','L6_route_readback')
AXES=('source_fidelity','closure_handoff','segmentation_adequacy')

def parts(row): return row['review_input']['candidate']['subtasks']

def levels(a,issues,n):
    a['layer_checks']=[dict(layer=l,status='issue' if l in issues else 'not_applicable' if l=='L0_integrity' or (l=='L4_handoffs' and n==1) else 'pass',
                           conclusion=issues[l][0] if l in issues else 'No rendered artifact is supplied.' if l=='L0_integrity' else 'No adjacent stage exists.' if l=='L4_handoffs' and n==1 else 'The requirements checked at this layer are preserved.',
                           finding_indices=issues[l][1] if l in issues else []) for l in LAYERS]

def make_finding(code,layer,check,dimension,rids,sq,ev,problem,repair,affected,related=(),operation='restore',protected=None):
    return dict(code=code,failed_layer=layer,c_check=check,dimension=dimension,related_dimensions=list(related),affected_subtask_indices=list(affected),source_requirement_ids=list(rids),source_quote=sq,candidate_evidence=ev,evidence_level='S1',problem=problem,execution_consequence=problem,
                repair=dict(operation=operation,affected_subtask_indices=list(affected),instruction=repair,protected_requirements=protected or ['Preserve the remaining source actions, target identities, counting origins, reference frames and final placement.']))

# number: code, C-check, exact source span, exact defective candidate span,
# affected requirement, local repair. This is a per-case semantic specification.
DIAG={
2:('WRONG_RELATION','C06','Make a left and walk past the stair case.','Make a right and walk past the stair case.','SRC-01','Restore only the first left before the stair-case pass; retain the later right and locker-room entry.'),
3:('LOST_EVENT','C03','Walk through the kitchen passed the sink.','Walk towards the kitchen passed the sink.','SRC-01','Restore traversal through the kitchen past the sink; retain the following left and wooden-room entry.'),
4:('OMISSION','C05','stand in the door way to the hall','stand in the  way to the hall','SRC-01','Restore door in the first doorway placement; preserve both subsequent left turns.'),
5:('OMISSION','C01','Turn around, go past the bed, out the door and to the right.','Go into the next door on the right.','SRC-01','Restore the omitted initial turn-around, bed pass, exit and rightward movement before the next-door entry; retain quilt identification and wait.'),
6:('DETACHED_CONDITION','C04','turn right after the kitchen table','turn right  the kitchen table','SRC-01','Restore after the kitchen table as the trigger for this right turn. Preserve the later end-table left, couch route and bedroom entry.'),
8:('UNSUPPORTED_ADDITION','C04','Do not enter the first doorway.','enter the first doorway','SRC-02','Restore the prohibition on entering the first doorway; retain the second-door right turn and desk-side stop.'),
9:('OMISSION','C11','stop in doorway facing sink','stop in doorway .','SRC-01','Restore facing sink at the doorway stop; preserve the two earlier right turns and the existing stopping location.'),
10:('WRONG_REFERENCE_FRAME','C06','the sunken seating area is on your left and the stairs going up are to your right','the sunken seating area is on your right and the stairs going up are to your left','SRC-01','Restore the specified seating-left/stairs-right frame after the turn; preserve both chairs and all later placement.'),
11:('COUNT_SCOPE_DRIFT','C07','the third door to your left','the next door to your left','SRC-01','Restore third with the original left-side counting frame, preserving the preceding room crossing.'),
12:('WRONG_RELATION','C06','Turn left and walk to the end of the kitchen bar.','Turn right and walk to the end of the kitchen bar.','SRC-02','Restore left only in the kitchen-bar approach. Keep the subsequent right around the chair and final left into the hallway.'),
13:('LOST_EVENT','C03','go through the doorway on the right','go towards the doorway on the right','SRC-04','Restore the right-doorway crossing, preserving all earlier turns and the final just-inside-bedroom stop.'),
14:('OMISSION','C05','With the rocking chair at your back','With the rocking  at your back','SRC-01','Restore chair in the initial reference. Preserve the existing stop at the wall at the brown-rug edge.'),
15:('OMISSION','C01','Walk through the outdoors deck area towards the open door beside the stair leading into the yard.','Walk inside the home','SRC-01','Restore the deck traversal and identified door approach before home entry; preserve the corner and living-room route.'),
16:('DETACHED_CONDITION','C04','TURN TO THE RIGHT UNTIL YOU THE DINNING TABLE IS ON THE RIGHT AND PILLARS ARE ON THE LEFT','TURN TO THE RIGHT  YOU THE DINNING TABLE IS ON THE RIGHT AND PILLARS ARE ON THE LEFT','SRC-01','Restore UNTIL with the table-right/pillars-left condition on the initial turn. Preserve the later turn and doorway crossing.'),
17:('OMISSION','C11','wait in front of the white couch by the window','in front of the white couch by the window','SRC-02','Restore wait at the retained white-couch location; preserve porch steps, covered-porch entry and house entry.'),
18:('UNSUPPORTED_ADDITION','C04','Do not enter the first doorway.','enter the first doorway','SRC-02','Restore the first-door prohibition; retain the second-door left and table-side stop.'),
20:('WRONG_TARGET','C11','Stop right there.','Stop beside the stairs.','SRC-03','Stop at the source-defined position after passing the chair, retaining the final Wait and all preceding travel.'),
21:('LOST_EVENT','C03','take another left into large dining hall','Walk towards the large dining hall.','SRC-04','Restore the additional left turn and entry into the large dining hall. Preserve the lobby entry and stairway approach.'),
22:('OMISSION','C08','when you get to the side of the stairs you have arrived','Walk towards the stairs.','SRC-08','Restore arrival at the side of the stairs after the final right; preserve prior window, picture-table and wall relations without adding STOP.'),
23:('WRONG_TARGET','C06','left set of windows','right set of windows','SRC-02','Restore the left window set at the existing stop, retaining bedroom entry, bed approach and going around the bed.'),
}
# Actual retained ending descriptions for one-stage negative candidates.
ENDS={
2:('explicit_event','into the locker room.','none'),3:('explicit_event','walk into the room with wooden walls that is completely empty except for a ceiling lamp.','none'),
4:('explicit_event','Make another left into the room next door.','none'),5:('explicit_event','Wait right there.','terminal'),
6:('explicit_event','walk into the bedroom.','none'),8:('explicit_event','stop beside the desk.','terminal'),9:('explicit_event','stop in doorway','terminal'),
10:('explicit_event','Stop just after passing the second white chair and before you enter the room with the double doors.','terminal'),
11:('explicit_event','into the next door to your left.','none'),12:('explicit_event','go into the bedroom.','none'),13:('explicit_event','Stop just inside the doorway.','terminal'),
14:('explicit_event','stopping at the wall at the edge of the brown rug.','terminal'),15:('explicit_event','into the living room area near the kitchen sink counter top.','none'),
16:('terminal_goal_directive','TURN SLIGHTLY TO THE RIGHT TOWARDS A HALL SINK ROOM WITH A PICTURE OF A SAILBOAT ON THE WALL.','none'),
17:('unspecified',None,'none'),18:('explicit_event','stop beside the table.','terminal'),20:('explicit_event','Stop beside the stairs.','terminal'),
}

def project_evidence(row):
    a=row['expected_review'];stages=parts(row)
    for group in ('source_coverage','findings','prior_finding_reviews'):
        for obj in a.get(group,[]):
            out=[]
            for e in obj.get('candidate_evidence',[]):
                if isinstance(e,dict):out.append(evidence(stages,e['subtask_index'],e['quote']));continue
                indices=[i for i,p in enumerate(stages) if e in p]
                if len(indices)!=1:raise ValueError(f'Ambiguous or absent evidence {row["template_id"]}: {e!r}')
                out.append(evidence(stages,indices[0],e))
            obj['candidate_evidence']=out
    a.setdefault('prior_finding_reviews',[])
    for l in a['layer_checks']:
        if l['status']=='not_assessable':l['status']='not_applicable'
    for c in a['source_coverage']:
        if c['status']=='source_limited':c['status']='requires_review'

def repair_diagnostic(row,number):
    if number not in DIAG:return
    a=row['expected_review'];stages=parts(row);src=row['review_input']['original_instruction']
    code,check,sq,cq,rid,repair=DIAG[number]
    if sq not in src:raise ValueError(f'Absent source evidence {number}: {sq}')
    i=0 if number<=20 else 1
    ev=evidence(stages,i,cq)
    related=['closure_handoff'] if number in (3,5,9,13,15,17,21,22) else []
    layer='L2_dependencies' if number in (6,9,10,16) else 'L3_stage_checks' if related or number in (20,23) else 'L1_source_coverage'
    problem=f'The source requires {sq!r}; the actual candidate instead contains {cq!r}.'
    a['findings']=[make_finding(code,layer,check,'source_fidelity',[rid],sq,[ev],problem,repair,[i],related)]
    a['dimensions']={d:'issue' if d=='source_fidelity' or d in related else 'pass' for d in AXES}
    # The listed cases have one explicitly authored corrupted requirement.
    for c in a['source_coverage']:
        c['status']='altered_or_missing' if c['requirement_id']==rid else 'covered'
        if c['requirement_id']==rid:c['candidate_evidence']=[ev]
    issues={'L1_source_coverage':(problem,[0]),layer:(problem,[0]),'L6_route_readback':(repair,[0])}
    if related:issues['L3_stage_checks']=(problem,[0])
    levels(a,issues,len(stages))
    if number<=20:
        st=a['stage_checks'][0];st['status']='gap';st['source_requirement_ids']=[c['requirement_id'] for c in a['source_coverage']]
        st['source_quotes']=[c['source_quote'] for c in a['source_coverage']]
        kind,q,scope=ENDS[number]
        if q:
            evidence(stages,0,q)
            st['ending']=dict(kind=kind,text='The candidate explicitly expresses this ending; the Finding separately checks its fidelity to the source.',candidate_quotes=[q],stop_scope=scope)
            st['target']=field('The actual candidate endpoint: '+q,q)
        else:
            st['ending']=dict(kind='unspecified',text='The source explicitly requires waiting; the candidate retains its location but omits the waiting action.',candidate_quotes=[],stop_scope='none')
            st['target']=field('The retained white-couch location, without the required waiting action.',cq)
        if number==20:
            st['conditions']=field('Preserve the prior stairs and chair passes; right there intensifies the source location rather than specifying a rightward frame.','past the stairs, past the chair')
        if number==4:
            st['conditions']=field('The early stand is part of the process before the later left turns. It is not the final endpoint.','stand in the  way to the hall')
    else:
        # The first stage and its handoff survive the later corrupted objective.
        first=a['stage_checks'][0];first['status']='supported'
        ids0={'SRC-01','SRC-02'} if number==21 else {'SRC-01','SRC-02','SRC-03','SRC-04'} if number==22 else {'SRC-01'}
        first['source_requirement_ids']=sorted(ids0)
        first['source_quotes']=[c['source_quote'] for c in a['source_coverage'] if c['requirement_id'] in ids0]
        for h in a['handoffs']:
            h['status']='supported';h['preceding_exit']=dict(text='The first stage executes the required region entry.',candidate_quote=stages[0])
            h['next_entry']=dict(text='Continue from the entered region.',candidate_quote=stages[1].split(',')[0])
            h['handoff_rationale']='The preceding entry supports this starting region; the later target defect is localized separately.'
        st=a['stage_checks'][1];st['status']='gap';st['entry']=dict(mode='inherited_pose',text='Continue from the supported preceding region entry.',candidate_quotes=[])
        st['process']=field(stages[1],stages[1]);st['target']=field('The candidate actually directs: '+cq,cq)
        st['conditions']=field('The actual candidate relation is quoted; the source-required alternative is supplied by the Finding.',cq)
        st['source_requirement_ids']=[c['requirement_id'] for c in a['source_coverage'] if c['requirement_id'] not in ids0 or c['requirement_id']==rid]
        st['source_quotes']=[c['source_quote'] for c in a['source_coverage'] if c['requirement_id'] in st['source_requirement_ids']]
        st['ending']=dict(kind='explicit_event' if number==23 else 'terminal_goal_directive',text='The candidate stops at the wrong window set.' if number==23 else 'The candidate gives an approach where the source requires a specific entry or arrival.',candidate_quotes=[cq],stop_scope='terminal' if number==23 else 'none')
    row['teaching_notes'].update(case_specific_focus=problem+' '+repair,transfer_rule=repair,counter_example_boundary='When the quoted source relation and its scope are preserved, accept the candidate rather than transferring this verdict.',primary_skills=[{2:'direction',3:'entry',4:'target_identity',5:'lost_action',6:'scope',8:'negation',9:'terminal',10:'frame',11:'ordinal',12:'direction',13:'entry',14:'target_identity',15:'lost_action',16:'scope',17:'terminal',18:'negation',20:'terminal',21:'entry',22:'endpoint',23:'frame'}[number]])

def valid_alternative(row,lesson):
    a=row['expected_review'];a['verdict']='pass';a['findings']=[];a['dimensions']={d:'pass' for d in AXES}
    for c in a['source_coverage']:c['status']='covered'
    for s in a['stage_checks']:s['status']='supported'
    for h in a['handoffs']:h['status']='supported'
    levels(a,{},len(parts(row)))
    row['teaching_notes'].update(review_pattern='valid_alternative_grouping',case_specific_focus=lesson,review_principle=lesson,decision_reason=lesson,transfer_rule=lesson,counter_example_boundary='A real missing target, changed condition or unsupported completion remains a material defect.',primary_skills=['grouping','endpoint'])
    row['provenance']['candidate_corruption_is_authored_not_model_output']=False
    row['provenance']['corruption_pattern']='none_valid_alternative'

def missing_hall_entry(row):
    src=row['review_input']['original_instruction'];stages=['Exit the pool area and walk toward the stairs.','From the hallway, turn right and enter the third door on the left. Wait by the lockers.']
    row['review_input']['candidate']['subtasks']=stages
    quotes=['Exit the pool area and walk toward the stairs','enter the hallway to the slight right past the chair','turn right and enter the third door on the left','wait by the lockers']
    cov=[]
    for i,q in enumerate(quotes):
        if q not in src:raise ValueError('Source identity changed')
        ev=evidence(stages,0,stages[0]) if i==0 else evidence(stages,1,'From the hallway' if i==1 else 'turn right and enter the third door on the left' if i==2 else 'Wait by the lockers.')
        cov.append(dict(requirement_id=f'SRC-{i+1:02d}',source_quote=q,requirement=q,candidate_evidence=[ev],status='altered_or_missing' if i==1 else 'covered'))
    f=make_finding('OMISSION','L4_handoffs','C09','closure_handoff',['SRC-02'],quotes[1],[evidence(stages,0,'walk toward the stairs'),evidence(stages,1,'From the hallway')],
        'A stair-directed approach does not execute the source hallway entry, yet the next stage assumes hallway occupancy.',
        'Restore the complete hallway-entry phrase with its slight-right and chair description before the right turn and third-door count. Keep its original modifier attachment; preserve the locker-side wait.',[0,1],['source_fidelity'],protected=['Preserve the pool exit and stair-directed movement.','Preserve the full hallway-entry description without adding a separate chair-pass waypoint.','Preserve the later right turn, third door on the left and locker-side wait.'])
    a=row['expected_review'];a.update(verdict='revise',dimensions=dict(source_fidelity='issue',closure_handoff='issue',segmentation_adequacy='pass'),source_coverage=cov,findings=[f],prior_finding_reviews=[])
    a['stage_checks']=[]
    for i,p in enumerate(stages):
        a['stage_checks'].append(dict(subtask_index=i,status='gap',entry=dict(mode='episode_start' if i==0 else 'explicit_context',text='Begin at the episode start.' if i==0 else 'The candidate assumes hallway entry that it has not expressed.',candidate_quotes=[] if i==0 else ['From the hallway']),target=field('The candidate stair-directed approach.' if i==0 else 'The locker-side waiting position after selecting the third left-hand door.',p),process=field(p,p),ending=dict(kind='unspecified' if i==0 else 'explicit_event',text='The approach does not establish the hallway entry needed next.' if i==0 else 'The actual candidate still commands the final locker wait.',candidate_quotes=[p] if i==0 else ['Wait by the lockers.'],stop_scope='none' if i==0 else 'terminal'),conditions=field(None) if i==0 else field('The hallway frame is required before the right turn and ordinal selection.','third door on the left'),source_requirement_ids=['SRC-01','SRC-02'] if i==0 else ['SRC-02','SRC-03','SRC-04'],source_quotes=quotes[:2] if i==0 else quotes[1:],carryover=[]))
    a['handoffs']=[dict(from_subtask_index=0,to_subtask_index=1,status='gap',preceding_exit=dict(text='The candidate only approaches the stairs.',candidate_quote='walk toward the stairs'),next_entry=dict(text='The next stage assumes hallway occupancy.',candidate_quote='From the hallway'),shared_context=[],source_requirement_ids=['SRC-02'],handoff_rationale=f['problem'])]
    levels(a,{l:(f['problem'],[0]) for l in ('L1_source_coverage','L2_dependencies','L3_stage_checks','L4_handoffs','L6_route_readback')},2)
    row['teaching_notes'].update(case_specific_focus=f['problem'],transfer_rule=f['repair']['instruction'],primary_skills=['entry','attachment','ordinal'],counter_example_boundary='A preceding actual hallway entry permits inherited pose without a From clause.')

def finalize_special(rows):
    r=rows['R2R-CORE-R06'];valid_alternative(r,'The single stage retains the office traversal, identified doorway, hall-end room and final table approach in usable order. A faithful multi-stage alternative is also valid; a preferred count alone is not a defect.')
    r['expected_review']['stage_checks'][0]['target']['text']='The circular tables in the large room as the final approach target; arrival is not asserted.'
    for tid in ('R2R-CORE-R04','R2R-DIAG-25'):
        r=rows[tid];f=r['expected_review']['findings'][0]
        f['c_check']='C10';f['execution_consequence']='This preparatory turn has no separate local target in this source and is better grouped with its coupled ascent; the turn itself is executable.'
        r['teaching_notes']['primary_skills']=['coupled','grouping']
    for tid in ('R2R-CORE-R07','R2R-DIAG-24','R2R-DIAG-26'):missing_hall_entry(rows[tid])
    r=rows['R2R-DIAG-28'];valid_alternative(r,'The bedroom arrival and the explicitly named bedroom-door wait can remain separate with supported handoff. Keeping them in one maneuver is also valid. Judge their actual relation rather than imposing a universal ban on terminal placement stages.')
    r=rows['R2R-CORE-R08'];a=r['expected_review'];src=r['review_input']['original_instruction']
    a['findings'][0]['problem']='The chandelier observation becomes an unsupported stopping target, while the far-wall door selection, crossing, hallway route and destination room are omitted.'
    a['findings'][0]['repair']['instruction']='Preserve the initial left turn and orientation cue; restore the far-wall open-door selection and crossing, hallway traversal, and room with blue patterned carpet and a table in the middle. Keep the route endpoint at the requested room, without a chandelier STOP.'
    a['findings'][0]['repair']['protected_requirements']=['Preserve the initial left turn and expected orientation.','Preserve the far-wall door identity and its actual crossing.','Preserve the blue patterned carpet and table in the destination room.']
    a['stage_checks'][0]['ending']=dict(kind='explicit_event',text='The candidate actually adds a chandelier-facing stop; the Finding identifies why this endpoint is unsupported.',candidate_quotes=['stop facing the chandelier above the green table'],stop_scope='terminal')
    r['teaching_notes']['primary_skills']=['observation','entry','terminal']
    # Imported source-archive copies use the same explicit current representation.
    for dst,core in [('R2R-DIAG-01','R2R-CORE-R02'),('R2R-DIAG-25','R2R-CORE-R04'),('R2R-REV-031','R2R-CORE-R10')]:
        rows[dst]['expected_review']=deepcopy(rows[core]['expected_review'])
    for n,check in [(7,'C11'),(19,None),(29,'C03')]:
        a=rows[f'R2R-DIAG-{n:02d}']['expected_review']
        if check:
            for f in a['findings']:f['c_check']=check
        else:
            a['findings'][0]['c_check']='C06';a['findings'][1]['c_check']='C11'
    for row in rows.values():
        if row['role']=='reviewer':project_evidence(row)
