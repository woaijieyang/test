"""Offline, field-local refinements of evaluated R2R teaching examples.

Retain the evaluated source and candidate except explicit semantic corrections.
Existing stage-specific evidence is the starting point, not a generic audit
reconstruction. Runtime code never invokes this authoring module.
"""
from copy import deepcopy
from r2r_authoring.positive import LESSONS,CANDIDATES,ENDINGS,CONDITIONS,field,evidence
CANDIDATE_REPAIRS=frozenset({20,23,30,35})
CONTEXT={
1:['After the descent and right turn, retain the resulting heading for the rug/bench approach.'],
2:['After the descent and right turn, retain the bench identity and right-side selection for the remaining approach.'],
3:['Retain the post-descent right-turn frame; the display case is a pass-by cue on the bench route.'],
4:['The selected far-wall doorway has actually been crossed; the next movement continues into the stated hallway.'],
5:['Continue from the crossed table-side doorway into the hall.','The hallway-end room is the same large room containing the circular tables.'],
6:['The entered next room contains the uniquely specified blue mat; continue to that mat without repeating entry.'],
7:['The entered lobby establishes the frame for the first left and subsequent dining-hall left.'],
9:['The banquet hall has been entered; near the door refers to the source hall doorway.'],
10:['The original bedroom has been exited into the hallway; entry into the blue-floral-bedroom remains.'],
11:['The explicitly reached hallway end establishes where the next left is taken.'],
12:['The initial left and room exit are complete; continue in the hall before selecting the left bedroom.'],
13:['The far bedroom doorway is crossed; the hallway/corner route and home-entrance stop remain.'],
15:['The bedroom exit establishes the region and count origin for the first door on the right; entering that door and turning right again remain.'],
16:['The bedroom entry is complete; retain the same bed and the left window set for the remaining route.'],
17:['The bird statue has been passed on the source route; cabinet-identified bedroom entry remains.'],
20:['The coupled living-room maneuver retains its participial attachment; the stair ascent and third-tile placement remain.'],
22:['The second doorway exit has occurred; the next right and table/stair route remain.'],
23:['The window-side doorway crossing establishes hallway context for the next right.'],
25:['The living room has been entered; the plant table is a reference on the way to the behind-couch waiting position.'],
27:['The open area establishes the next right-turn frame; the living-room right turn has its own later owner.'],
30:['The staircase remains the spatial reference for the first room to its left; reaching its bottom does not supply a new egocentric left.'],
34:['Actual hallway entry is complete; the right turn and locker-room entry remain.'],
35:['Actual slight-right hallway entry is complete; retain that hallway frame for the subsequent right turn and third left-hand door.'],
}
TRANSFER={
2:'Inherit a completed stair/turn pose when unique, then keep the later trigger and exact terminal placement attached to the remaining approach.',
4:'Use expected facing as an orientation cue, identify and cross the requested door, and keep observation separate from a visit goal.',
5:'Bind target-identifying relations before selection; distinct completed transitions may expose useful goals, while a faithful coarse alternative needs its own C10 assessment.',
11:'Use an explicitly stated corridor-end turn to bound that traversal; preserve the subsequent turn, entry and terminal doorway placement.',
13:'Preserve an open-door adjective as object state while executing the source crossing; add door operation only when the source commands it.',
15:'Retain the completed exit establishing an ordinal selection region; keep the count class, right-side frame and later second turn distinct.',
18:'Keep the until condition on its hallway movement and the bedroom-door placement on the same endpoint; assess separate placement by its real objective.',
20:'Preserve simultaneous/participial movement attachment before evaluating a cut; retain the later stair and ordinal placement.',
21:'Bind a top-wait and step count to one ascent; a completion refinement does not create a second ascent.',
23:'Preserve expected observation without promoting it to an extra visit; crossing and final specified arrival require their own source events.',
28:'Keep the center/right relation on door selection and the source-directed destination as an event without inventing physical STOP.',
30:'Keep object-relative left/right tied to its reference object; arrival near that object does not convert it to agent heading.',
35:'Keep a modifier on its source action when a different attachment is not uniquely supported; complete actual entry before inheriting that region.',
}

def _quotes(audit,stage):
    for key in ('entry','target','process','ending','conditions'):
        for q in audit[key]['candidate_quotes']:
            if not q or q not in stage:raise ValueError('Stale '+key+' evidence: '+repr(q))

def author_generator(row,number):
    source=row['input']['original_instruction'];out=row['output'];old=deepcopy(out);notes=row['teaching_notes']
    skills,lesson,counter=LESSONS[number]
    reusable=TRANSFER.get(number) or notes.get('reusable_rule') or notes.get('transfer_rule')
    if not reusable:raise ValueError('Missing evaluated transfer rule: '+row['template_id'])
    notes.update(case_rationale=lesson,case_specific_focus=lesson,primary_skills=skills.split(),counter_example_boundary=counter,reusable_rule=reusable,transfer_rule=reusable,five_element_focus='Check Entry, Target, Process, Ending and Conditions against the exact case-specific evidence; preserve the operative relation and scope.')
    row['decision']['rationale']=lesson
    if out['status']!='ok':return
    if number in CANDIDATE_REPAIRS:
        out['subtasks']=deepcopy(CANDIDATES[number]);row['decision']['mode']='split' if len(out['subtasks'])>1 else 'keep'
    parts=out['subtasks'];specs=deepcopy(ENDINGS[number]);audits=deepcopy(old['stage_audit'])
    if len(parts)!=len(audits) or len(parts)!=len(specs):raise ValueError('Changed stage count needs an explicit mapping: '+row['template_id'])
    if number in (22,28,32):
        _,q,scope,target=specs[-1];specs[-1]=('explicit_event',q,scope,target.replace('final directed target','source-directed destination'))
    if number==5:
        specs[1]=('explicit_event','enter the room at the end of the hallway.','none','The room entered at the explicitly stated hallway end.')
        specs[2]=('terminal_goal_directive','walk towards the circular tables in the middle.','none','The circular tables in the already entered large room, approached without a stated arrival threshold.')
    for i,(audit,(kind,q,scope,target)) in enumerate(zip(audits,specs)):
        stage=parts[i];evidence(parts,i,q)
        audit['target']=field(target,q)
        audit['ending']=dict(kind=kind,text=target+(' The source directs a final approach without specifying arrival or STOP.' if kind=='terminal_goal_directive' else ' This is the source-directed completion event; it adds no physical STOP.'),candidate_quotes=[q],stop_scope=scope)
        if stage!=old['subtasks'][i]:
            audit['process']=field(stage,stage)
            if any(q not in stage for q in audit['entry']['candidate_quotes']):
                if i==0:raise ValueError('First-stage context requires explicit remapping')
                audit['entry']=dict(mode='inherited_pose',text=CONTEXT[number][i-1],candidate_quotes=[])
        phrases=CONDITIONS.get(number,[[] for _ in parts])[i]
        if number==5 and i==2:phrases=['Inside the large room','circular tables in the middle']
        if phrases:
            for phrase in phrases:evidence(parts,i,phrase)
            audit['conditions']=field('Operative constraints: '+'; '.join(phrases),*phrases)
        elif stage!=old['subtasks'][i] and any(q not in stage for q in audit['conditions']['candidate_quotes']):
            raise ValueError('Changed condition needs exact evidence: '+row['template_id'])
        if number==28:audit['conditions']=field('Select the center door in the right-side set after the stair-bottom pass.','center door on right')
        if number==35:
            audit['source_quotes']=(['Exit the pool area and walk toward the stairs','enter the hallway to the slight right past the chair'] if i==0 else ['turn right and enter the third door on the left','wait by the lockers'])
        for q in audit['source_quotes']:
            if not q or q not in source:raise ValueError('Source quote changed: '+row['template_id'])
        if len(parts)>1:
            ctx=CONTEXT.get(number)
            if ctx is None or len(ctx)!=len(parts)-1:raise ValueError('Missing carrying-state mapping: '+row['template_id'])
            audit['carryover']=[ctx[i]] if i<len(parts)-1 else []
        _quotes(audit,stage)
    out['stage_audit']=audits
    hands=deepcopy(old['handoffs'])
    if len(hands)!=len(parts)-1:raise ValueError('Missing evaluated handoffs')
    for i,h in enumerate(hands):
        context=CONTEXT[number][i]
        if parts[i]!=old['subtasks'][i] or h['preceding_exit']['candidate_quote'] not in parts[i]:
            h['preceding_exit']=dict(text=audits[i]['ending']['text'],candidate_quote=specs[i][1])
        if parts[i+1]!=old['subtasks'][i+1] or h['next_entry']['candidate_quote'] not in parts[i+1]:
            quote=parts[i+1].split('. ')[0].rstrip('.')+'.' if '. ' in parts[i+1] else parts[i+1]
            if quote not in parts[i+1]:raise ValueError('No exact next-entry event quote')
            h['next_entry']=dict(text=context,candidate_quote=quote)
        h['shared_context']=[context];h['handoff_rationale']=context+' '+reusable
    out['handoffs']=hands

def finalize_detail(rows):
    r=rows['R2R-CORE-R06']
    r['provenance']['curation_basis']='Authored comparison of faithful coarse and multi-stage organization, not a navigation-ground-truth judgment.'
    for layer in r['expected_review']['layer_checks']:
        if layer['layer']=='L5_grouping':
            layer['conclusion']='The candidate explicitly retains office traversal, selected doorway, hall-end room entry and final table approach in usable order. The multi-stage form exposes those objectives, but no specific dependency or local-focus loss is established here. Other evidenced missed-goal cases remain C10 defects.'
    for tid in ('R2R-CORE-R04','R2R-DIAG-25'):
        rows[tid]['teaching_notes']['transfer_rule']='Assess the preparatory turn with the ascent it enables in this source; a turn with its own stated observation or placement can be independent.'
    for row in rows.values():
        notes=row['teaching_notes']
        if row['role']=='reviewer' and not notes.get('reusable_rule'):notes['reusable_rule']=notes.get('transfer_rule') or notes.get('case_specific_focus')
