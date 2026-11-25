"""Case-local, source-grounded teaching corrections. Offline only.

These repairs leave every source and every approved candidate unchanged. They
correct evidence and explanations; they do not certify model or navigation quality.
"""
from copy import deepcopy
from tools.r2r_authoring.positive import field


def ending_text(kind, target, scope):
    if scope == 'terminal':
        return target + ' Preserve the source-required final stop/wait or standing placement as quoted; no additional stop is introduced.'
    if scope == 'intermediate':
        return target + ' Preserve this source-required intermediate stop/wait before the remaining source route; it is not episode completion.'
    if kind == 'terminal_goal_directive':
        return target + ' The source directs a final approach without specifying arrival or STOP.'
    if kind == 'bounded_action':
        return target + ' Complete exactly the source-bounded movement; the stage boundary adds no physical stop.'
    return target + ' Complete this source-directed event; the stage boundary adds no physical stop.'


def _coverage(quotes, requirements, evidence):
    return [dict(requirement_id=f'SRC-{i+1:02d}', source_quote=q, requirement=req,
                 candidate_evidence=[dict(subtask_index=j, quote=c) for j,c in ev], status='covered')
            for i,(q,req,ev) in enumerate(zip(quotes,requirements,evidence))]


def _positive(row, number):
    out=row['output']; notes=row['teaching_notes']; stages=out['subtasks']
    if number == 30:
        out['stage_audit'][0]['source_quotes']=['Go to the bottom of the staircase']
        out['stage_audit'][1]['source_quotes']=['go to the entrance of first room to the left of the staircase','wait by the chair']
        out['stage_audit'][1]['target']=field('The chair-side waiting position at the entrance of the first room to the left of the staircase.',
            'the entrance of the first room to the left of the staircase','wait by the chair')
        notes.update(why_this_case_matters='Reaching the staircase bottom establishes position, not a new agent-relative left. Select the first room relative to the staircase, then preserve the chair-side wait.',
                     handoff_focus='The completed staircase-bottom approach retains the staircase as the reference for the room selection.',
                     segmentation_pattern='staircase_bottom_then_object_relative_room_and_wait')
    elif number == 35:
        notes.update(why_this_case_matters='The first stage includes actual hallway entry with its slight-right/chair description. Only then does the second stage turn right, select the third left-hand door and wait by the lockers.',
                     handoff_focus='Actual hallway entry establishes the region for the subsequent right turn and third left-hand door. No separate chair-pass waypoint is inferred.',
                     segmentation_pattern='completed_hallway_entry_then_ordinal_door_and_wait')
        out['stage_audit'][1]['target']=field('The locker-side waiting position reached by the right turn and third left-hand door entry.',
            'enter the third door on the left','Wait by the lockers.')
    for stage in out.get('stage_audit',[]):
        # Target and ending need not share a quote: the target can contain the
        # selecting relation while ending quotes the final requested wait.
        if stage['ending']['stop_scope'] != 'none':
            stage['ending']['text']=ending_text(stage['ending']['kind'],stage['target']['text'],stage['ending']['stop_scope'])


def _paired(row, number):
    """Reviewer-specific evidence, derived from source/candidate, not Generator audit."""
    a=row['expected_review'];parts=row['review_input']['candidate']['subtasks']
    if number == 30:
        quotes=['Go to the bottom of the staircase','go to the entrance of first room to the left of the staircase','wait by the chair']
        a['source_coverage']=_coverage(quotes,
            ['Reach the staircase bottom.','Select the first room left of the staircase, not agent-left, and go to its entrance.','Wait by the chair at that selected entrance.'],
            [[(0,'Go to the bottom of the staircase.')],[(1,'Go to the entrance of the first room to the left of the staircase')],[(1,'wait by the chair.')]])
        groups=[[0],[1,2]]
        a['stage_checks'][1]['target']=field('The chair-side position at the selected room entrance, with the staircase-relative direction retained.',
            'the entrance of the first room to the left of the staircase','wait by the chair')
    elif number == 35:
        groups=[[0,1],[2,3]]
        a['source_coverage'][1]['candidate_evidence']=[dict(subtask_index=0,quote='enter the hallway to the slight right past the chair')]
        a['stage_checks'][1]['target']=field('The locker-side wait following the specified third left-hand door entry.',
            'enter the third door on the left','Wait by the lockers.')
    else:return
    for s,own in zip(a['stage_checks'],groups):
        s['source_requirement_ids']=[a['source_coverage'][i]['requirement_id'] for i in own]
        s['source_quotes']=[a['source_coverage'][i]['source_quote'] for i in own]
        if s['ending']['stop_scope']!='none':s['ending']['text']=ending_text(s['ending']['kind'],s['target']['text'],s['ending']['stop_scope'])
    a['handoffs'][0]['source_requirement_ids']=[c['requirement_id'] for c in a['source_coverage']]
    note='The staircase remains the spatial reference after reaching its bottom; the final chair-side wait is still required.' if number==30 else 'Actual hallway entry, not merely a chair pass, supports the later right turn and ordinal selection; the final locker wait remains required.'
    row['teaching_notes'].update(why_this_review_matters=note,review_pattern='source_grounded_relation_and_handoff')


def _r06(row):
    a=row['expected_review'];s=a['stage_checks'][0]
    s['conditions']=field('Preserve the table-relative doorway identity, arched-window cue, hall-end room and table position without asserting final arrival.',
        'on the other side of the table with the arched window above','the room at the end of the hallway','the circular tables in the middle of the large room')
    row['teaching_notes']['why_this_review_matters']='The ordered clauses retain local target identity and dependencies in a usable coarse stage. Another valid split is not evidence of a grouping defect; source coverage alone is also not sufficient to decide C10.'
    row['teaching_notes']['anti_pattern']='Do not infer a grouping defect merely from multiple room names, and do not excuse a genuinely obscured independent objective merely because all source words remain.'


def _diag28(row):
    a=row['expected_review'];parts=row['review_input']['candidate']['subtasks']
    quotes=['Go through the doorway to the room with the sink','follow the hallway until you get to a bedroom.','Wait at the bedroom door.']
    req=['Cross the doorway identified by the room with the sink.','Follow the hallway until reaching the bedroom.','Preserve the final wait at that bedroom door.']
    a['source_coverage']=_coverage(quotes,req,[[(i,parts[i])] for i in range(3)])
    targets=[('The room identified by the sink, reached through its doorway.','the room with the sink'),('The bedroom reached along the hallway.','a bedroom'),('The door of that same bedroom as the final waiting position.','the bedroom door')]
    conditions=[('The sink identifies the destination room.','the room with the sink'),('Until binds the hallway movement to bedroom arrival.','until you get to a bedroom'),('At the bedroom door fixes the final placement, without requiring bedroom entry.','at the bedroom door')]
    contexts=['The source-directed doorway crossing is complete; the remaining hallway movement follows without repeating the crossing.','The source-directed bedroom arrival identifies the bedroom whose door is the remaining waiting position.']
    for i,s in enumerate(a['stage_checks']):
        s['target']=field(*targets[i]);s['process']=field(req[i],parts[i]);s['conditions']=field(*conditions[i])
        s['entry']=dict(mode='episode_start' if i==0 else 'inherited_pose',text='Use the source episode start.' if i==0 else contexts[i-1],candidate_quotes=[])
        s['source_requirement_ids']=[f'SRC-{i+1:02d}'];s['source_quotes']=[quotes[i]]
        s['carryover']=[contexts[i]] if i<2 else []
        s['ending']=dict(kind='explicit_event',text=ending_text('explicit_event',targets[i][0],'terminal' if i==2 else 'none'),candidate_quotes=[parts[i]],stop_scope='terminal' if i==2 else 'none')
    for i,h in enumerate(a['handoffs']):
        h.update(preceding_exit=dict(text=a['stage_checks'][i]['ending']['text'],candidate_quote=parts[i]),
                 next_entry=dict(text=contexts[i],candidate_quote=parts[i+1]),
                 shared_context=[dict(kind='entity_or_region',text=contexts[i])],
                 source_requirement_ids=[f'SRC-{i+1:02d}',f'SRC-{i+2:02d}'],
                 handoff_rationale=contexts[i]+' The next stage performs only the remaining source-directed action; no extra crossing or stop is inferred.')
    for layer in a['layer_checks']:
        if layer['layer']=='L5_grouping':layer['conclusion']='The crossing, hallway-to-bedroom leg and door-specific final placement retain supported entries and local targets. The final wait adds a location relation, not a content-free STOP. A coarser faithful organization is also valid.'


def apply(rows):
    for row in rows.values():
        tid=row['template_id']
        if row['role']=='generator':
            number=int(row['provenance']['core_curated_from'][-3:]) if '-CORE-' in tid else int(tid[-3:])
            if row['output']['status']=='ok':_positive(row,number)
        elif tid.startswith('R2R-REV-'):
            _paired(row,int(tid[-3:]))
    _r06(rows['R2R-CORE-R06']);_diag28(rows['R2R-DIAG-28'])
    # No change to actual source/candidate strings is authorized by this module.
    for row in rows.values():
        if row['role']=='reviewer' and not row['expected_review']['findings']:
            for h in row['expected_review']['handoffs']:
                if 'finding below' in h['handoff_rationale'].lower():raise ValueError('Stale finding reference: '+row['template_id'])
