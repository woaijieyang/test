"""Offline R2R positive teaching specification; all edits are source-local.

The source strings are immutable. This module authors examples, not a runtime
route parser. Skill labels name the lesson actually taught, not incidental nouns.
"""
from copy import deepcopy

# Ordered skills, decisive teaching, and a counter-boundary for each source.
LESSONS = {
1: ('stair_target terminal', 'Complete the descent and right turn before the rug-side bench/piano placement; inherit that heading for the remaining approach.', 'A midway limit would constrain the descent itself rather than a new full descent.'),
2: ('stair_target terminal scope', 'The forward approach begins after the descent/right turn; the bench trigger closes at the wood between the bench and carpet.', 'Keep a source-requested approach without inventing arrival if no later placement refines it.'),
3: ('stair_target pass_by terminal', 'Keep the display-case pass on the route to the right-hand bench; inherit the completed descent and right turn.', 'Passing a case alone does not establish entry into a different room.'),
4: ('observation target_identity entry', 'The chandelier/table is the expected facing cue after the turn; the far-wall open door is selected and crossed before the hallway route.', 'A source that explicitly asks to stop facing the chandelier would define a different endpoint.'),
5: ('entry target_identity final_approach', 'Use the table-side and arched-window cues to cross the selected door; traverse the hall into its end room before approaching the circular tables.', 'A faithful single stage can preserve these ordered objectives; tables are approached, not certified reached.'),
6: ('transit endpoint terminal', 'Use the unique arched doorway and straight small-hall transit to reach the next room; the blue mat specifies the final stop.', 'Entering the next room does not alone satisfy the later blue-mat placement.'),
7: ('entry direction', 'The lobby entry establishes the next frame; left toward the stairway is followed by another left into the dining hall.', 'Approaching the dining hall preserves its noun but loses the required turn and entry.'),
8: ('coupled pass_by terminal', 'The fountain pass and left turn prepare the approach to the doorway across from the stairs; stop in that doorway.', 'A separate visit with a stated completion before the turn could justify another stage.'),
9: ('transit entry terminal', 'The big room is transit to the banquet hall; retain both left movements and the final position near the hall door.', 'A room name alone is not a mandatory stage boundary.'),
10: ('attribute entry target_identity', 'The open door identifies the exit, not an opening command; the hallway connects to the bedroom selected by its blue floral blanket.', 'A source command to open a closed door would be an additional action worth preserving.'),
11: ('hall_end direction terminal', 'The source explicitly ends the straight hallway traversal before the left turn; enter the bedroom and wait in its doorway.', 'A generic instruction to go down a hallway does not establish its far end.'),
12: ('entry direction', 'The television-front movement and left exit precede the hall traversal and left-bedroom entry.', 'A predicted view of a doorway would not establish that exit.'),
13: ('attribute transit entry', 'Open doors describe the passage state. Continue through the bedroom and its far-side door before the hallway/corner route to the home entrance.', 'An open-door adjective does not request operating the door.'),
14: ('coupled transit terminal', 'Treat crossing the bedroom, turning right and stopping at the glass doors before the outside exit as one complete maneuver.', 'A distinct visit completed inside the bedroom would change the grouping test.'),
15: ('ordinal entry frame', 'Exit the bathroom, cross and exit the bedroom, then count the first right-hand door from that established region; keep the final right turn and stop.', 'Removing the bedroom-exit context can change the origin of first door even when the ordinal word survives.'),
16: ('entry terminal frame', 'The star-tile crossing establishes bedroom entry; the bed approach and route around it end at the left set of windows.', 'A right-window ending is a target error, not a failure of the already completed bedroom handoff.'),
17: ('pass_by entry target_identity', 'Retain the ordered sink, hand-statue and bird-statue route before bedroom entry identified by the wooden cabinet.', 'An observed landmark is not automatically a separate visit or stop.'),
18: ('transit endpoint terminal', 'Follow the transit route until the bedroom, keeping the waiting position at its door. Until limits the hallway movement.', 'A separate final placement can be legitimate when its location and inherited entry remain explicit.'),
19: ('coupled direction terminal', 'The coach pass prepares the left turn and stair ascent; keep this coupled local process and its final stop.', 'An independently requested turn-and-observe or turn-and-wait task could be a separate objective.'),
20: ('scope stair_target ordinal', 'Keep passing and taking-left attached to the living-room maneuver; climb into the entryway and preserve the third tile from the left at the top step.', 'A participial turn is not automatically an action that begins only after an invented waypoint.'),
21: ('bounded endpoint terminal', 'The three steps and their top-wait describe one bounded ascent; the later condition closes that ascent.', 'Completing the entire staircase before climbing three more steps repeats movement.'),
22: ('entry direction final_approach', 'Execute both door exits in order before the right turn, table-directed movement and stair target.', 'A later context anchor cannot stand in for an unperformed doorway crossing.'),
23: ('observation entry endpoint', 'The indoor glass window is an expected cue after the vanity turn; cross the doorway before the hallway route and explicit side-of-stairs arrival.', 'Walking toward stairs alone weakens the source-defined final arrival condition.'),
24: ('coupled direction terminal', 'Preserve the ordered right-left-right chain after the bathroom exit and wait at the top of the stairs.', 'Turn count or sentence count alone does not establish independent local targets.'),
25: ('entry terminal frame', 'Enter the living room before placing the agent just behind the couch; the plant table remains an approach reference.', 'Living-room entry alone does not satisfy the just-behind-couch wait.'),
26: ('transit entry', 'Continue alongside the stairs through the hall, then turn the corner into the couch-filled living area.', 'The stairs are a route-side landmark, not an instruction to climb them.'),
27: ('entry frame terminal', 'Retain the explicit open-area and living-room frames for successive right turns and the final couch-corner stop.', 'Repeated right turns have different region owners; merging text cannot erase those owners.'),
28: ('coupled target_identity final_approach', 'Pass the bottom of the stairs before selecting the center door on the right; preserve the compact whole maneuver.', 'A center-door descriptor is not interchangeable with an ordinal door count.'),
29: ('coupled pass_by terminal', 'Keep the entranceway approach, leftward pass of the stairs and stop near the doorway front together.', 'Stopping inside the hall would strengthen the source stop near the doorway front.'),
30: ('entity_frame ordinal terminal', 'The first room is left of the staircase; reaching the staircase bottom does not redefine that relation as the agent current left.', 'A source explicitly using on your left would supply an egocentric reference instead.'),
31: ('uncertainty target_identity', 'Read the back-of-church route and handrail/wall relations before assessing pack exit. Preserve a necessary unresolved exit identity rather than turning a likely spelling into certainty.', 'An explicit back exit in an otherwise identical source resolves that identity without a guess.'),
32: ('coupled final_approach', 'Keep the leftward hallway travel with continuation to the stairs; preserve the stated target without adding an unstated stop.', 'An explicit source wait at the stairs would add a terminal event.'),
33: ('pass_by terminal', 'The fan and baptismal font are ordered pass-by landmarks; the in-ground pond is the waiting target.', 'Reaching the font does not complete the later pond placement.'),
34: ('transit entry terminal', 'Cross the sitting area and actually enter the hallway before turning right toward the locker room; wait inside that room.', 'From the hallway is valid only after its entry has been expressed or uniquely established.'),
35: ('attachment entry ordinal', 'Keep past the chair attached to the slight-right hallway-entry description. Complete that entry before the right turn, third left door and locker wait.', 'A chair-pass waypoint is not uniquely authorized as a separate first-stage endpoint by this wording.'),
}

# Explicit candidate edits. Unlisted source/candidate text is retained.
CANDIDATES = {
5: ['Walk through the office past the table and armchairs. Walk through the door on the other side of the table with the arched window above.', 'Walk down the hall and enter the room at the end of the hallway.', 'Walk towards the circular tables in the middle of the large room.'],
8: None,
14: None,
20: ['Walk straight into the living room passing the chair and the couch and taking a left behind the couch and past the dining room table.', 'Go up the stairs into the entryway, stopping on the third tile from the left at the top step.'],
23: ['Go toward the door. Turn left by the black vanity. You will see an indoor glass window. Go toward the glass window and through the doorway.', 'When you are in the hallway by the window, take a right. Go toward the table with the pictures on it. Then go toward the wall with the security box or thermostat. Finally take a right; when you get to the side of the stairs you have arrived.'],
30: ['Go to the bottom of the staircase.', 'Go to the entrance of the first room to the left of the staircase and wait by the chair.'],
35: ['Exit the pool area and walk toward the stairs, enter the hallway to the slight right past the chair.', 'Turn right and enter the third door on the left. Wait by the lockers.'],
}
# Each ending is (kind, exact candidate quote, stop scope, target description).
ENDINGS = {
1:[('bounded_action','turn right.','none','The post-descent state after the right turn.'),('explicit_event','Wait near the bench and piano along the right side of the wall.','terminal','The waiting place near the bench and piano along the right wall.')],
2:[('bounded_action','take a right.','none','The post-descent state after the right turn.'),('explicit_event','stop and stand on the wood between the bench and the carpet.','terminal','The wood between the bench and carpet, on reaching the bench at the right.')],
3:[('bounded_action','turn right.','none','The post-descent right-turn state.'),('explicit_event','wait in front of the bench on the right.','terminal','The front of the right-hand bench.')],
4:[('explicit_event','go through it.','none','The far-wall open doorway, identified separately from the chandelier observation.'),('explicit_event','walk down the hallway into the room with the blue patterned carpet and the table in the middle.','none','The room with the blue patterned carpet and middle table.')],
5:[('explicit_event','Walk through the door on the other side of the table with the arched window above.','none','The specified far-side doorway crossed from the office.'),('explicit_event','enter the room at the end of the hallway.','none','The room entered at the hallway end.'),('terminal_goal_directive','Walk towards the circular tables in the middle of the large room.','none','The circular tables being approached; no arrival threshold is supplied.')],
6:[('explicit_event','enter the next room.','none','The next room reached through the small hallway.'),('explicit_event','stop once you reach the blue mat.','terminal','The blue-mat stopping position.')],
7:[('explicit_event','enter the large room that looks like a lobby.','none','The lobby-like room entered after the initial movement.'),('explicit_event','Take another left into the large dining hall.','none','The dining-hall interior after the second left.')],
8:[('explicit_event','Stop in the doorway.','terminal','The doorway directly across from the stairs.')],
9:[('explicit_event','enter the banquet hall.','none','The banquet-hall interior.'),('explicit_event','stand near the door and wait.','terminal','The position near the banquet-hall door.')],
10:[('explicit_event','Walk out of the bedroom and into the hallway.','none','The hallway reached through the open bedroom door.'),('explicit_event','enter the bedroom with the blue floral blanket.','none','The bedroom identified by the blue floral blanket.')],
11:[('explicit_event','Continue straight to the end of the hallway.','none','The explicitly stated hallway end.'),('explicit_event','Wait in the doorway.','terminal','The bedroom doorway after the left turn and entry.')],
12:[('explicit_event','Turn left and exit the room.','none','The completed room exit after the television-side movement.'),('explicit_event','step into the bedroom on the left.','none','The left bedroom interior.')],
13:[('explicit_event','Walk through the door on the other side of the bedroom, past the bed and lamp.','none','The far-side bedroom doorway crossing.'),('explicit_event','stop in the doorway.','terminal','The home-entrance doorway.')],
14:[('explicit_event','stop at the glass doors before the outside exit.','terminal','The glass doors before the outside exit.')],
15:[('explicit_event','exit the bedroom.','none','The bedroom exit establishing the next selection region.'),('explicit_event','Turn right again and stop.','terminal','The post-entry right-turn stopping position.')],
16:[('explicit_event','enter the bedroom.','none','The bedroom reached across the star tile.'),('explicit_event','stop next to the left set of windows.','terminal','The left window set after going around the bed.')],
17:[('explicit_event','down the hall past the statue of a bird.','none','The bird-statue pass on the ordered route.'),('explicit_event','enter the bedroom area with the wooden cabinet.','none','The bedroom area identified by the wooden cabinet.')],
18:[('explicit_event','Wait at the bedroom door.','terminal','The bedroom-door waiting position.')],
19:[('explicit_event','Continue up the stairs and stop.','terminal','The stair-ascent stopping state.')],
20:[('explicit_event','past the dining room table.','none','The dining-table pass within the coupled living-room route.'),('explicit_event','stopping on the third tile from the left at the top step.','terminal','The third tile from the left at the top step.')],
21:[('explicit_event','when you get to the top, wait.','terminal','The top of the prescribed three-step ascent.')],
22:[('explicit_event','Turn left and go out that door.','none','The second doorway exit after the left turn.'),('terminal_goal_directive','Proceed to the stairs on the right.','none','The right-hand stairs as the final directed target.')],
23:[('explicit_event','Go toward the glass window and through the doorway.','none','The hallway-side doorway crossing by the glass window.'),('explicit_event','when you get to the side of the stairs you have arrived.','none','The explicit side-of-stairs arrival position.')],
24:[('explicit_event','wait at the top of the stairs.','terminal','The top of the stairs after the ordered turns.')],
25:[('explicit_event','enter the living room.','none','The living-room interior.'),('explicit_event','stand just behind the couch and wait.','terminal','The position just behind the couch.')],
26:[('explicit_event','Turn the corner into the living room area with couches.','none','The living area entered around the corner.')],
27:[('explicit_event','enter the open area.','none','The open area after the console-table pass.'),('explicit_event','stop behind the couch near the right corner.','terminal','Behind the couch near the right corner in the living room.')],
28:[('terminal_goal_directive','go to center door on right.','none','The center door on the right after the stair-bottom pass.')],
29:[('explicit_event','Stop near the front of the doorway to the hall.','terminal','Near the front of the hall doorway.')],
30:[('explicit_event','Go to the bottom of the staircase.','none','The staircase bottom.'),('explicit_event','wait by the chair.','terminal','The chair-side position at the entrance of the first room left of the staircase.')],
32:[('terminal_goal_directive','Continue to the stairs.','none','The stairs as the final directed target.')],
33:[('explicit_event','Wait at in-ground baptismal pond.','terminal','The in-ground baptismal pond.')],
34:[('explicit_event','go through the door into the hallway.','none','The actual hallway entry after sitting-area transit.'),('explicit_event','Wait inside the locker room.','terminal','Inside the locker room.')],
35:[('explicit_event','enter the hallway to the slight right past the chair.','none','The hallway entered using the original slight-right/chair description.'),('explicit_event','Wait by the lockers.','terminal','The lockers after the right turn and third left-hand door entry.')],
}
CONDITIONS = {
2:[[],['Once you reach the bench on your right','between the bench and the carpet']],
4:[['facing the chandelier above the green table','open door on the far wall'],['blue patterned carpet']],
5:[['on the other side of the table','arched window above'],['at the end of the hallway'],['in the middle of the large room']],
6:[['arched, round design above it','straight'],['once you reach the blue mat']],
7:[['proceed to your left'],['head left towards the stairway','another left']],
11:[['straight to the end of the hallway'],['turn left','in the doorway']],
15:[['exit the bedroom'],['After exiting the bedroom','first door on your right','Turn right again']],
16:[['star tile'],['around it','left set of windows']],
18:[['until you get to a bedroom','at the bedroom door']],
20:[['taking a left behind the couch','past the dining room table'],['third tile from the left','at the top step']],
21:[['three steps','when you get to the top']],
23:[['You will see an indoor glass window'],['When you are in the hallway by the window','when you get to the side of the stairs']],
27:[['console table on the right'],['In the open area','In the living room','near the right corner']],
30:[[],['first room to the left of the staircase','by the chair']],
34:[['straight through the sitting area'],['From the hallway','Wait inside']],
35:[['hallway to the slight right past the chair'],['Turn right','third door on the left','by the lockers']],
}
# Authored coverage owners, not an automated entailment test.
OWNERS={1:[[0,1],[1]],2:[[0],[1],[1]],3:[[0],[0],[1]],4:[[0],[0],[1],[1]],5:[[0],[0],[1],[2]],6:[[0],[0],[1]],7:[[0],[0],[1],[1]],8:[[0],[0],[0]],9:[[0],[0],[1]],10:[[0],[0],[1]],11:[[0],[1],[1]],12:[[0],[0],[1]],13:[[0],[0],[1],[1]],14:[[0],[0]],15:[[0],[0],[0],[1]],16:[[0,1],[1]],17:[[0],[0],[0],[1]],18:[[0],[0]],19:[[0],[0]],20:[[0],[0],[1],[1]],21:[[0],[0],[0]],22:[[0],[0],[1],[1]],23:[[0],[0],[0],[0],[1],[1],[1],[1]],24:[[0],[0],[0]],25:[[0],[0,1]],26:[[0],[0]],27:[[0],[1],[1]],28:[[0]],29:[[0],[0],[0]],30:[[0],[1],[1]],32:[[0],[0]],33:[[0],[0],[0]],34:[[0],[0],[0,1],[1]]}

def field(text,*quotes): return {'text':text,'candidate_quotes':list(quotes)}
def evidence(stages,i,q):
    if not q or q not in stages[i]: raise ValueError(f'Absent authored evidence stage {i}: {q!r}')
    return {'subtask_index':i,'quote':q}

def author_generator(row,number):
    source=row['input']['original_instruction']
    out=row['output']
    if number in CANDIDATES:
        out['subtasks']=deepcopy(CANDIDATES[number]) if CANDIDATES[number] is not None else [source]
        row['decision']['mode']='split' if len(out['subtasks'])>1 else 'keep'
    skills,lesson,counter=LESSONS[number]
    notes=row['teaching_notes']
    notes.update(case_rationale=lesson,case_specific_focus=lesson,transfer_rule=lesson,
                 counter_example_boundary=counter,primary_skills=skills.split(),
                 reusable_rule='',why_this_case_matters=lesson)
    row['decision']['rationale']=lesson
    if out['status']!='ok': return
    parts=out['subtasks'];specs=ENDINGS[number]
    if len(parts)!=len(specs): raise ValueError(f'Stage/spec mismatch {row["template_id"]}')
    audits=[]
    for i,(kind,q,scope,target) in enumerate(specs):
        evidence(parts,i,q)
        cs=CONDITIONS.get(number,[[] for _ in parts])[i]
        for c in cs:evidence(parts,i,c)
        entry={'mode':'episode_start' if i==0 else 'inherited_pose',
               'text':'Begin in the actual episode context.' if i==0 else 'Use the preceding source-supported completion and continue with this stage first unperformed action.',
               'candidate_quotes':[]}
        audits.append(dict(subtask_index=i,entry=entry,target=field(target,q),
                           process=field(parts[i],parts[i]),
                           ending=dict(kind=kind,text=target + (' This is a final approach without an asserted arrival or STOP.' if kind=='terminal_goal_directive' else ' Complete the quoted source-directed event.'),candidate_quotes=[q],stop_scope=scope),
                           conditions=field('; '.join(cs),*cs) if cs else field(None),
                           source_quotes=[source.strip()],carryover=[]))
    out['stage_audit']=audits
    out['handoffs']=[dict(from_subtask_index=i,to_subtask_index=i+1,status='supported',
                         preceding_exit=dict(text=audits[i]['ending']['text'],candidate_quote=specs[i][1]),
                         next_entry=dict(text='The next stage continues from this completion; any stated anchor binds context rather than replaying movement.',candidate_quote=parts[i+1]),
                         shared_context=[],source_requirement_ids=[],handoff_rationale=lesson)
                    for i in range(len(parts)-1)]

def author_paired(row,generator,number):
    src=row['review_input']['original_instruction']
    if src!=generator['input']['original_instruction']: raise ValueError('Paired source mismatch')
    out=generator['output'];row['review_input']['candidate']['subtasks']=deepcopy(out['subtasks'])
    row['review_input']['candidate']['status']=out['status']
    skills,lesson,counter=LESSONS[number]
    row['teaching_notes'].update(case_specific_focus=lesson,transfer_rule=lesson,counter_example_boundary=counter,primary_skills=skills.split())
    if out['status']!='ok': return
    a=row['expected_review'];parts=out['subtasks'];owners=OWNERS.get(number)
    if number==35:
        quotes=['Exit the pool area and walk toward the stairs','enter the hallway to the slight right past the chair','turn right and enter the third door on the left','wait by the lockers']
        owners=[[0],[0],[1],[1]]
        a['source_coverage']=[dict(requirement_id=f'SRC-{i+1:02d}',source_quote=q,requirement=q,candidate_evidence=[],status='covered') for i,q in enumerate(quotes)]
    if len(owners)!=len(a['source_coverage']):raise ValueError(f'Coverage owner mismatch {row["template_id"]}')
    for c,indices in zip(a['source_coverage'],owners):
        c['status']='covered'
        old=c.get('candidate_evidence',[]);ev=[]
        for i in indices:
            options=[e.get('quote') if isinstance(e,dict) else e for e in old]
            exact=[q for q in options if q and q in parts[i]]
            q=c['source_quote'] if c['source_quote'] in parts[i] else exact[0] if exact else parts[i]
            ev.append(evidence(parts,i,q))
        c['candidate_evidence']=ev
    a['stage_checks']=[]
    for check in out['stage_audit']:
        check=deepcopy(check);i=check['subtask_index'];check['status']='supported'
        check['source_requirement_ids']=[c['requirement_id'] for c,own in zip(a['source_coverage'],owners) if i in own]
        check['source_quotes']=[c['source_quote'] for c,own in zip(a['source_coverage'],owners) if i in own]
        a['stage_checks'].append(check)
    a['handoffs']=deepcopy(out['handoffs'])
    for h in a['handoffs']:
        h['source_requirement_ids']=list(dict.fromkeys(a['stage_checks'][h['from_subtask_index']]['source_requirement_ids']+a['stage_checks'][h['to_subtask_index']]['source_requirement_ids']))
    a['prior_finding_reviews']=[]
