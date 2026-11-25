"""Offline field-local refinement of immutable evaluated R2R examples.

Existing candidate and audit evidence is retained unless an explicit authored
correction below applies. No runtime request invokes these functions.
"""
from copy import deepcopy
from r2r_authoring.positive import LESSONS,CANDIDATES,ENDINGS,CONDITIONS,OWNERS,field,evidence
CANDIDATE_REPAIRS=frozenset({20,23,30,35})
CONTEXT={
1:['After the descent and right turn, retain the resulting heading for the rug/bench approach.'],
2:['After the descent and right turn, retain the bench identity and right-side selection for the remaining approach.'],
3:['Retain the post-descent right-turn frame; the display case is a pass-by cue on the bench route.'],
4:['The selected far-wall doorway has actually been crossed; the next movement continues into the stated hallway.'],
5:['Continue from the crossed table-side doorway into the hall.','The hallway-end room is the same large room containing the circular tables.'],
6:['The entered next room contains the uniquely specified blue mat; continue to that mat without repeating entry.'],
7:['The entered lobby establishes the frame for the first left and subsequent dining-hall left.'],
8:['The fountain pass and left turn are complete; the doorway across from the stairs remains the stopping target.'],
9:['The banquet hall has been entered; near the door refers to the source hall doorway.'],
10:['The original bedroom has been exited into the hallway; entry into the blue-floral-bedroom remains.'],
11:['The explicitly reached hallway end establishes where the next left is taken.'],
12:['The initial left and room exit are complete; continue in the hall before selecting the left bedroom.'],
13:['The far bedroom doorway is crossed; the hallway/corner route and home-entrance stop remain.'],
14:['The source bedroom traversal precedes the right turn and glass-door placement; no outside crossing is established.'],
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
8:'Evaluate the complete pass-and-turn before a doorway placement; a faithful single maneuver can also be valid, and no intermediate physical stop is introduced.',
11:'Use an explicitly stated corridor-end turn to bound that traversal; preserve the subsequent turn, entry and terminal doorway placement.',
13:'Preserve an open-door adjective as object state while executing the source crossing; add door operation only when the source commands it.',
14:'Retain the bedroom traversal before the right turn and glass-door stop; the source before relation keeps the outside exit unperformed.',
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
    if number==8:lesson='The complete fountain pass and left turn establish the next doorway-directed leg. The same source also permits a coherent unsplit maneuver; the example adds no intermediate STOP.'
    if number==14:lesson='The completed bedroom traversal is followed by a right turn and glass-door stop before the outside exit. A faithful combined maneuver is also possible; preserve the before-exit limit in either grouping.'
    reusable=TRANSFER.get(number) or notes.get('reusable_rule') or notes.get('transfer_rule')
    if not reusable:raise ValueError('Missing evaluated transfer rule: '+row['template_id'])
    notes.update(case_rationale=lesson,case_specific_focus=lesson,primary_skills=skills.split(),counter_example_boundary=counter,reusable_rule=reusable,transfer_rule=reusable,five_element_focus='Check Entry, Target, Process, Ending and Conditions against exact case-specific evidence; preserve the operative relation and scope.')
    row['decision']['rationale']=lesson
    if out['status']!='ok':return
    if number in CANDIDATE_REPAIRS:
        out['subtasks']=deepcopy(CANDIDATES[number]);row['decision']['mode']='split' if len(out['subtasks'])>1 else 'keep'
    parts=out['subtasks'];specs=deepcopy(ENDINGS[number]);audits=deepcopy(old['stage_audit'])
    if number==8:specs=[('bounded_action','turn left.','none','The post-fountain state after the specified left turn.'),('explicit_event','Stop in the doorway.','terminal','The doorway directly across from the stairs.')]
    if number==14:specs=[('explicit_event','Walk through the bedroom.','none','The completion of the source bedroom traversal.'),('explicit_event','stop at the glass doors before the outside exit.','terminal','The glass doors before the outside exit.')]
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
        if number==8:phrases=[['past the water fountain','turn left'],['After passing the water fountain and turning left','directly across from the stairs']][i]
        if number==14:phrases=[['through the bedroom'],['After walking through the bedroom','before the outside exit']][i]
        if phrases:
            for phrase in phrases:evidence(parts,i,phrase)
            audit['conditions']=field('Operative constraints: '+'; '.join(phrases),*phrases)
        elif stage!=old['subtasks'][i] and any(q not in stage for q in audit['conditions']['candidate_quotes']):
            raise ValueError('Changed condition needs exact evidence: '+row['template_id'])
        if number==28:audit['conditions']=field('Select the center door in the right-side set after the stair-bottom pass.','center door on right')
        if number==35:audit['source_quotes']=(['Exit the pool area and walk toward the stairs','enter the hallway to the slight right past the chair'] if i==0 else ['turn right and enter the third door on the left','wait by the lockers'])
        for q in audit['source_quotes']:
            if not q or q not in source:raise ValueError('Source quote changed: '+row['template_id'])
        if len(parts)>1:
            ctx=CONTEXT.get(number)
            if ctx is None or len(ctx)!=len(parts)-1:raise ValueError('Missing carrying-state mapping: '+row['template_id'])
            audit['carryover']=[ctx[i]] if i<len(parts)-1 else []
        _quotes(audit,stage)
    out['stage_audit']=audits;hands=deepcopy(old['handoffs'])
    if len(hands)!=len(parts)-1:raise ValueError('Missing evaluated handoffs')
    for i,h in enumerate(hands):
        context=CONTEXT[number][i]
        if parts[i]!=old['subtasks'][i] or h['preceding_exit']['candidate_quote'] not in parts[i]:h['preceding_exit']=dict(text=audits[i]['ending']['text'],candidate_quote=specs[i][1])
        if parts[i+1]!=old['subtasks'][i+1] or h['next_entry']['candidate_quote'] not in parts[i+1]:
            quote=parts[i+1].split('. ')[0].rstrip('.')+'.' if '. ' in parts[i+1] else parts[i+1]
            if quote not in parts[i+1]:raise ValueError('No exact next-entry event quote')
            h['next_entry']=dict(text=context,candidate_quote=quote)
        kind='count_origin' if number==15 else 'orientation' if number in (1,2,3,7,8,27) else 'temporal_state' if number==20 else 'entity_or_region'
        h['shared_context']=[dict(kind=kind,text=context)];h['handoff_rationale']=context+' '+reusable
    out['handoffs']=hands

def author_paired(row,generator,number):
    src=row['review_input']['original_instruction']
    if src!=generator['input']['original_instruction']:raise ValueError('Paired source mismatch')
    out=generator['output'];row['review_input']['candidate']['subtasks']=deepcopy(out['subtasks']);row['review_input']['candidate']['status']=out['status']
    gnotes=generator['teaching_notes']
    row['teaching_notes'].update(case_specific_focus=gnotes['case_rationale'],transfer_rule=gnotes['transfer_rule'],reusable_rule=gnotes['reusable_rule'],counter_example_boundary=gnotes['counter_example_boundary'],primary_skills=deepcopy(gnotes['primary_skills']))
    if out['status']!='ok':return
    a=row['expected_review'];parts=out['subtasks'];owners=deepcopy(OWNERS.get(number))
    if number==8:owners=[[0],[1],[1]]
    if number==14:owners=[[0],[1]]
    if number==35:
        quotes=['Exit the pool area and walk toward the stairs','enter the hallway to the slight right past the chair','turn right and enter the third door on the left','wait by the lockers'];owners=[[0],[0],[1],[1]]
        a['source_coverage']=[dict(requirement_id=f'SRC-{i+1:02d}',source_quote=q,requirement=q,candidate_evidence=[],status='covered') for i,q in enumerate(quotes)]
    if owners is None or len(owners)!=len(a['source_coverage']):raise ValueError('Coverage owner mismatch: '+row['template_id'])
    for c,indices in zip(a['source_coverage'],owners):
        c['status']='covered';old=c.get('candidate_evidence',[]);ev=[]
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
    for h in a['handoffs']:h['source_requirement_ids']=list(dict.fromkeys(a['stage_checks'][h['from_subtask_index']]['source_requirement_ids']+a['stage_checks'][h['to_subtask_index']]['source_requirement_ids']))
    a['prior_finding_reviews']=[]

def finalize_detail(rows):
    r=rows['R2R-CORE-R06'];r['provenance']['curation_basis']='Authored comparison of faithful coarse and multi-stage organization, not a navigation-ground-truth judgment.'
    for layer in r['expected_review']['layer_checks']:
        if layer['layer']=='L5_grouping':layer['conclusion']='The candidate explicitly retains office traversal, selected doorway, hall-end room entry and final table approach in usable order. The multi-stage form exposes those objectives, but no specific dependency or local-focus loss is established here. Other evidenced missed-goal cases remain C10 defects.'
    for tid in ('R2R-CORE-R04','R2R-DIAG-25'):rows[tid]['teaching_notes']['transfer_rule']='Assess the preparatory turn with the ascent it enables in this source; a turn with its own stated observation or placement can be independent.'
    for row in rows.values():
        notes=row['teaching_notes']
        if row['role']=='reviewer' and not notes.get('reusable_rule'):notes['reusable_rule']=notes.get('transfer_rule') or notes.get('case_specific_focus')
