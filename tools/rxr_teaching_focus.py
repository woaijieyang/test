"""Explicit RxR teaching calibration; offline authoring, never an online judge.

These finite edits were read against their source instructions. Quote validation
proves existence and identity, not semantic entailment or navigation success.
No source text, retrieval label, pool membership or runtime schema is changed.
"""
from __future__ import annotations
from tools.rxr_positive_repairs import evidence, field, replace_candidate, stages_and_checks

# Each tuple is (Generator lesson, Reviewer lesson, counterexample/transfer limit).
LESSONS = {
1: ("Initial standing and the right-hand doorway establish the starting view; only the commanded turn, washroom entry and final between-fixtures placement are actions. Split after entry without replaying the initial observation.",
    "Verify initial view, the commanded turn, actual washroom entry and the final sink/bathtub placement separately. Seeing the doorway does not prove entry; entry does support the inside-washroom next stage.",
    "Do not turn initial observations into searches or visits, and do not use a visible doorway as evidence that the room was entered."),
2: ("The hallway traversal ends on reaching the second right-hand doorway. Not entering the first doorway constrains that traversal but cannot prove arrival; retain the original counting scope before the study turn.",
    "Require separate evidence for second-doorway arrival, the first-doorway prohibition and the subsequent study entry. Use arrival, not the negative constraint, to establish the handoff.",
    "Do not count only open doors, restart the count at a cut, or substitute compliance with a prohibition for the required arrival."),
3: ("Turn left before dining-room entry and then enter the open area. The before-clause locates the turn; it does not command entry into the dining room. Keep this coupled maneuver together.",
    "Check that the left turn precedes any dining-room entry and that the candidate enters the open area instead. That entry is a completion event even without an added STOP; there is no inter-stage handoff.",
    "Do not infer dining-room entry from before entering, or require an extra STOP to validate entry into the actual destination."),
4: ("Reconstruct the right-turn, hallway-end and kitchen-entry order from before/after across sentences. Later kitchen, dining-room and study transitions remain distinct source-supported events.",
    "Compare temporal dependencies rather than sentence order: right turn before hallway traversal, kitchen entry after its end, then dining-room entry, study entry and the desk-to-window finish.",
    "Do not execute kitchen entry before the earlier-mentioned prerequisite, or preserve sentence order at the expense of the stated temporal order."),
5: ("Bind the close-doorway and dark-wall descriptions to bathroom-door selection. These properties identify the requested door; only the actual entry establishes the inside-bathroom handoff.",
    "Independently verify bedroom traversal, first-right-door selection, the close pair and dark-wall cue, and bathroom entry. Use entry evidence for the next inside-bathroom left turn.",
    "Do not treat identification of the dark-wall door as completed entry, redefine the ordinal counting scope, or drop the late identifying description."),
6: ("Halfway down refines the same staircase descent. Descend only about halfway, then stop and wait there; this is one bounded event, not a full descent followed by a second movement.",
    "Read the general descent and its later approximate halfway limit together. Verify both stop and wait at that location; a single complete stage is valid and has no adjacent handoff.",
    "Do not complete the whole staircase first, convert about halfway into an exact distance, or manufacture another descent or stage."),
7: ("The later beside-table state refines the table approach. Preserve proximity and the left-side relation at that position, then the right turn, kitchen entry and just-inside sink-facing stop.",
    "Check beside-table proximity separately from table-on-left orientation. Together they support the following turn; the final stop is just inside the kitchen facing the sink, not a visit to the sink.",
    "Do not use a side relation alone as arrival evidence, extend an endpoint-only relation over the entire path, or turn a facing reference into a destination."),
8: ("The local correction replaces only left with right. Retain blue-door entry, sofa-on-left crossing, the explicit window stop and the real return through the same blue door to the stairs.",
    "Verify the corrected turn, continuous sofa-side constraint, intermediate window stop and later return to the same door. Repeated door identity does not erase the intervening route.",
    "Do not execute the corrected-away left turn, erase the window leg as repetition, or carry the crossing-only sofa constraint over the return."),
9: ("Keep the explicit counter stop before choosing exactly the source-supported door/archway branch. Both entrances lead to the laundry room; sink stopping follows entry, not both branches in sequence.",
    "Verify counter placement, the door-open condition and otherwise alternative, their common destination, and the inside-laundry sink stop. Preserve the source's intermediate stop without making every cut a STOP.",
    "Do not execute both mutually exclusive branches, treat them as descriptive uncertainty, or cancel the counter stop because the route continues."),
10: ("When the full source supplies neither the referent of there nor the turn direction, preserve route-critical uncertainty through the existing needs_review path instead of fabricating a partial route.",
     "Confirm that merging or reading the full source cannot identify there or the turn direction. Return source-limited unresolved rather than a speculative PASS or a candidate-only repair.",
     "Do not generalize this source ambiguity to ordinary descriptive uncertainty or to context lost only because of a bad candidate boundary."),
}

# Authored local evidence, not a substring-search-based semantic aligner.
# Existing local SRC identifiers and candidate routes are retained.
COVERAGE = {
1: [
 (1,"Preserve the starting glass-door view and the doorway on the right, not new movements.",[(0,"You start standing in front of a glass door, with a doorway on your right.")]),
 (2,"Turn around and retain the resulting washroom-doorway observation.",[(0,"Turn around; you should see a doorway to the washroom.")]),
 (3,"Approach the identified doorway and enter the washroom.",[(0,"Walk towards that doorway and enter the washroom.")]),
 (4,"After entry, finish standing between the sink and bathtub.",[(1,"Once inside the washroom, stand between the sink and the bathtub."),(1,"This is your final destination.")]),
],
2: [
 (1,"Traverse the hallway past both paintings on the left until reaching the second right-hand doorway.",[(0,"Walk along the hallway, passing the two paintings on your left, until you reach the second doorway on your right.")]),
 (2,"Do not enter the first doorway during this counted traversal.",[(0,"Do not enter the first doorway.")]),
 (3,"From the reached second doorway, turn right into the study and stop beside the desk.",[(1,"From the second doorway on the right that you have just reached"),(1,"turn right into the study and stop beside the desk.")]),
],
3: [
 (1,"Approach the dining room, turn left before entering it, and enter the open area instead.",[(0,"Walk towards the dining room"),(0,"turn left before entering it and go into the open area.")]),
],
4: [
 (1,"Kitchen entry follows reaching the hallway end, not the source sentence's surface position.",[(0,"walk down the hallway to its end and enter the kitchen.")]),
 (2,"The right turn occurs before hallway traversal.",[(0,"Turn right, then walk down the hallway")]),
 (3,"After kitchen entry, cross the kitchen and traverse the archway into the dining room.",[(1,"Once inside the kitchen"),(1,"cross it and go through the archway into the dining room.")]),
 (4,"Cross the dining room and enter the study via the bookcase-side door.",[(2,"Cross the dining room"),(2,"enter the study through the door beside the bookcase.")]),
 (5,"Inside the study, go around the desk before stopping at the window.",[(3,"In the study, walk around the desk"),(3,"stop at the window.")]),
],
5: [
 (1,"Cross the bedroom and enter the bathroom through the first door on the right.",[(0,"Walk across the bedroom and enter the bathroom through the first door on your right.")]),
 (2,"Use the close doorway pair and darker wall to identify the bathroom doorway, not to establish completed entry.",[(0,"There are two doorways close together; the bathroom doorway is in the darker-painted wall.")]),
 (3,"Once inside the bathroom, turn left and stop in front of the toilet.",[(1,"Inside the bathroom, turn left"),(1,"stop in front of the toilet.")]),
],
6: [
 (1,"Descend the staircase, subject to the subsequent halfway refinement of this same event.",[(0,"Go about halfway down the staircase")]),
 (2,"Limit that descent to about halfway and then stop.",[(0,"Go about halfway down the staircase, then stop")]),
 (3,"Wait at the same approximately halfway position after stopping.",[(0,"about halfway down the staircase"),(0,"then stop and wait there.")]),
],
7: [
 (1,"Begin facing the wall; this is a starting state.",[(0,"You start facing a wall.")]),
 (2,"Turn left and approach the white table.",[(0,"Turn left and walk towards the white table")]),
 (3,"Finish the same approach next to the white table with it on the left at that position.",[(0,"walk towards the white table until you are next to it."),(0,"At that position, the table should be on your left.")]),
 (4,"From beside that table, turn right and pass through the open doorway into the kitchen.",[(1,"From beside the white table"),(1,"turn right and walk through the open doorway into the kitchen.")]),
 (5,"Stop just inside the entered kitchen while facing the sink, without an additional visit to it.",[(1,"Stop just inside the kitchen, facing the sink.")]),
],
8: [
 (1,"Apply the explicit left-to-right correction and approach the blue door next to the stairs.",[(0,"Turn right and walk to the blue door next to the stairs")]),
 (2,"Enter the lounge through that same identified blue door.",[(0,"the blue door next to the stairs"),(0,"then go through that door into the lounge.")]),
 (3,"Keep the sofa on the left while crossing the lounge, then make the explicit window-side stop.",[(1,"Cross the lounge with the sofa on your left"),(1,"stop beside the window.")]),
 (4,"After the window stop, return through the same blue door and stop beside the stairs.",[(2,"From beside the window, return through the same blue door next to the stairs"),(2,"stop beside the stairs.")]),
],
9: [
 (1,"Enter the kitchen and make the source-required intermediate counter-side stop.",[(0,"Enter the kitchen"),(0,"stop beside the counter.")]),
 (2,"From the counter, take the laundry door only under its stated open condition.",[(1,"From beside the counter, if the door to the laundry room is open, go through it")]),
 (3,"Otherwise use the open archway beside that door, not both branches unconditionally.",[(1,"if the door to the laundry room is open, go through it; otherwise use the open archway beside that door.")]),
 (4,"Both conditional entrances lead into the same laundry room.",[(1,"Both entrances lead into the laundry room.")]),
 (5,"After laundry-room entry, stop at the sink.",[(1,"Once inside the laundry room, stop at the sink.")]),
],
}
HANDOFF_REQUIREMENTS = {
1:[[3,4]], 2:[[1,3]], 3:[], 4:[[1,3],[3,4],[4,5]],
5:[[1,2,3]], 6:[], 7:[[2,3,4]], 8:[[2,3],[1,2,3,4]], 9:[[1,2,3]],
}


def _quote_replacements(obj, replacements):
    """Replace only declared candidate-evidence strings; never source quotes."""
    if isinstance(obj,list):
        for item in obj: _quote_replacements(item,replacements)
    elif isinstance(obj,dict):
        for key,value in obj.items():
            if key in ('source_quote','source_quotes'): continue
            if key in ('quote','candidate_quote') and isinstance(value,str):
                for old,new in replacements: value=value.replace(old,new)
                obj[key]=value
            elif key=='candidate_quotes':
                updated=[]
                for value in value:
                    for old,new in replacements: value=value.replace(old,new)
                    updated.append(value)
                obj[key]=updated
            else: _quote_replacements(value,replacements)


def refine_positive(rows):
    """Two source-preserving route edits before dependent diagnostics are built."""
    old=("The source gives conflicting left/right descriptions for the glass window "
         "('on your right' and 'on your left'), so treat the window only as an uncertain "
         "visual reference; an open door is in front of you.")
    new="On your right a glass window on your left and an open door in front of you."
    for tid in ('RxR-GEN-002','RxR-REV-002'):
        row=rows[tid]
        replace_candidate(row,0,old,new)
        stages,checks,_=stages_and_checks(row)
        audit=row['output'] if row['role']=='generator' else row['expected_review']
        _quote_replacements(audit,[("conflicting left/right descriptions for the glass window",
                                  "On your right a glass window on your left"),
                                 ("an open door is in front of you","an open door in front of you")])
        checks[0]['process']['text']=stages[0]
        checks[0]['conditions']['text']=("Preserve the ordered turns and few-step approach. The contradictory window-side wording is retained without choosing a side; the open door ahead and agent-relative bench cue identify the commanded route. This does not license ignoring a route-critical conflict in another source.")
        row['teaching_notes']['case_rationale']=("Preserve the auxiliary window-side wording without choosing a side or placing source-analysis commentary in executable text. Keep the door-ahead target and the bench on your right; do not transfer the bench relation to the door.")
        if row['role']=='reviewer':
            row['teaching_notes']['case_specific_focus']=row['teaching_notes']['case_rationale']
            for layer in audit['layer_checks']:
                if layer['layer']=='L0_integrity':
                    layer.update(status='not_applicable',finding_indices=[],conclusion='No rendered artifact is supplied in this teaching case; review the actual candidate text without claiming renderer verification.')

    old_prefix="From near the open back door, look towards a room or another door visible at the back of it and move towards that target."
    new_prefix="From near the open back door, you should see a room or another door at the back of it. Walk towards that target."
    old_move="Continue until you are near a desk and at the back of the brown chairs."
    new_move="You should now be standing near a desk and at the back of the brown chairs."
    old_tail="When you are standing at the chair, turn right and continue until you are standing near the foot of the bed. This is your destination."
    new_tail="When you are standing at the chair, turn right. Now you should be standing near the foot of the bed; once you are here, you are done."
    replacements=[
        ("When you are standing at the chair, turn right and continue until you are standing near the foot of the bed.",new_tail),
        ("look towards a room or another door visible at the back of it and move towards that target","you should see a room or another door at the back of it. Walk towards that target"),
        ("continue until you are standing near the foot of the bed","Now you should be standing near the foot of the bed"),
        ("until you are standing near the foot of the bed","Now you should be standing near the foot of the bed"),
        ("This is your destination.","once you are here, you are done."),
    ]
    for tid in ('RxR-GEN-020','RxR-REV-020'):
        row=rows[tid]
        for old,new in [(old_prefix,new_prefix),(old_move,new_move),(old_tail,new_tail)]:
            replace_candidate(row,1,old,new)
        stages,checks,_=stages_and_checks(row)
        audit=row['output'] if row['role']=='generator' else row['expected_review']
        _quote_replacements(audit,replacements)
        checks[1]['process']=field('From the established back-door position, retain the expected room-or-door observation, walk toward that target, preserve the resulting desk/chair state, turn right at the chair, and retain the stated foot-of-bed final state without commanding another traversal.',new_prefix,new_move,new_tail)
        checks[1]['ending'].update(kind='explicit_event',stop_scope='terminal',
            text='Finish in the stated near-foot-of-bed position. The source describes this state after the chair-side right turn; no extra continue-until movement is prescribed.',
            candidate_quotes=['Now you should be standing near the foot of the bed; once you are here, you are done.'])
        checks[1]['conditions']=field('Do not resolve room-or-door descriptive uncertainty into another route. Preserve the desk and behind-chair relations, the right turn at the chair, and the final bed-foot state. Expected standing is not a new movement command.',
            'a room or another door','near a desk and at the back of the brown chairs','When you are standing at the chair, turn right.','Now you should be standing near the foot of the bed; once you are here, you are done.')
        lesson='Preserve the explicit stand-near-opening intermediate stop and the final foot-of-bed state. Keep expected observations and result states as such; do not add look or continue-until commands merely to make the audit appear closed.'
        row['teaching_notes']['case_rationale']=lesson
        if row['role']=='reviewer':
            row['teaching_notes']['case_specific_focus']=lesson
            byid={c['requirement_id']:c for c in audit['source_coverage']}
            byid['SRC-06'].update(requirement='Preserve the expected room-or-door view from the back-door position without selecting an unsupported alternative or adding a viewing action.',candidate_evidence=[evidence(stages,1,'From near the open back door, you should see a room or another door at the back of it.')])
            q='walk towards that and now you should be standing near a desk and  at the back of the brown chairs'
            if q not in row['review_input']['original_instruction']: raise ValueError('Missing authored desk/chair source span')
            byid['SRC-07'].update(source_quote=q,requirement='Walk toward the described target and retain the resulting desk-near, behind-brown-chairs state.',candidate_evidence=[evidence(stages,1,'Walk towards that target.'),evidence(stages,1,new_move)])
            byid['SRC-08'].update(requirement='At the stated chair position, turn right; do not add a further movement command.',candidate_evidence=[evidence(stages,1,'When you are standing at the chair, turn right.')])
            byid['SRC-09'].update(requirement='Preserve the stated final position near the foot of the bed and completion without inferring additional distance.',candidate_evidence=[evidence(stages,1,'Now you should be standing near the foot of the bed; once you are here, you are done.')])
            for layer in audit['layer_checks']:
                if layer['layer']=='L0_integrity':
                    layer.update(status='not_applicable',finding_indices=[],conclusion='No rendered artifact is supplied; this example reviews the actual candidate, not an unobserved rendering.')
                elif layer['layer']=='L3_stage_checks':
                    layer['conclusion']='The intermediate stand and final foot-of-bed state remain explicit. Expected observation and standing clauses do not create extra looking or locomotion commands.'


def refine_core(rows):
    """Authored case lessons and event-local evidence, applied after normalization."""
    for number,(gen_lesson,rev_lesson,avoid) in LESSONS.items():
        for role,letter,lesson in [('generator','G',gen_lesson),('reviewer','R',rev_lesson)]:
            row=rows[f'RXR-CORE-{letter}{number:02d}'];notes=row['teaching_notes']
            if row['role']!=role: raise ValueError('Core role mismatch')
            if role=='generator':
                notes['case_rationale']=lesson
                notes['reusable_rule']=lesson
                notes['why_this_case_matters']=lesson
            else:
                notes['case_specific_focus']=lesson
                notes['reuse_rule']=lesson
            notes['anti_pattern']=avoid
        if number==10: continue
        row=rows[f'RXR-CORE-R{number:02d}'];audit=row['expected_review']
        stages=row['review_input']['candidate']['subtasks'];coverage=audit['source_coverage']
        authored=COVERAGE[number]
        if [c['requirement_id'] for c in coverage]!=[f'SRC-{n:02d}' for n,_,_ in authored]:
            raise ValueError(f'Core coverage identity changed: {number}')
        for c,(_,requirement,pairs) in zip(coverage,authored):
            if c['status']!='covered' or c['source_quote'] not in row['review_input']['original_instruction']:
                raise ValueError('Unexpected source coverage state')
            c['requirement']=requirement
            c['candidate_evidence']=[evidence(stages,index,quote) for index,quote in pairs]
        if number==5:
            q='There are two doorways close together. The bathroom doorway is in the darker-painted wall.'
            if q not in row['review_input']['original_instruction']: raise ValueError('Missing close-doorway source context')
            coverage[1]['source_quote']=q
        expected=HANDOFF_REQUIREMENTS[number]
        if len(expected)!=len(audit['handoffs']): raise ValueError('Core boundary count changed')
        for h,ids in zip(audit['handoffs'],expected):
            h['source_requirement_ids']=[f'SRC-{i:02d}' for i in ids]
        for s in audit['stage_checks']:
            index=s['subtask_index']
            s['source_requirement_ids']=[c['requirement_id'] for c in coverage if any(e['subtask_index']==index for e in c['candidate_evidence'])]
            s['source_quotes']=[c['source_quote'] for c in coverage if c['requirement_id'] in s['source_requirement_ids']]
        for layer in audit['layer_checks']:
            if layer['layer']=='L1_source_coverage':
                layer['conclusion']='The event-local evidence below supports each source requirement, including its action or state, target and operative qualifiers. Matching a noun alone is insufficient.'
            elif layer['layer']=='L2_dependencies':
                layer['conclusion']=rev_lesson
            elif layer['layer']=='L4_handoffs' and not audit['handoffs']:
                layer.update(status='not_applicable',finding_indices=[],conclusion='This candidate has one stage and no adjacent-stage handoff. Its process and completion are assessed separately.')
