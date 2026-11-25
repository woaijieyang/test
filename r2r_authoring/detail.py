"""Offline, source-local refinements of the evaluated R2R positive examples.

Start from each evaluated author's stage evidence. Keep existing candidate text
except the explicitly listed source repairs. This module does not infer semantic
truth from word matches and is never imported by the navigation request path.
"""
from copy import deepcopy
from r2r_authoring.positive import LESSONS, CANDIDATES, ENDINGS, CONDITIONS, field, evidence

# Only these candidate changes are independently explained source corrections.
# Other baseline candidates retain their wording and useful existing anchors.
CANDIDATE_REPAIRS = frozenset({20, 23, 30, 35})

# Case-local carrying state. This is intended completion, not observed pose.
CONTEXT = {
 1:['After the descent and right turn, retain the resulting heading for the rug/bench approach.'],
 2:['After the descent and right turn, retain the bench identity and right-side selection for the remaining approach.'],
 3:['Retain the post-descent right-turn frame; the display case is a pass-by cue on the bench route.'],
 4:['The selected far-wall doorway has actually been crossed; the next movement continues into the stated hallway.'],
 5:['Continue from the crossed table-side doorway into the hall.','The hallway-end room is the same large room containing the circular tables.'],
 6:['The entered next room contains the uniquely specified blue mat; continue to that mat without repeating entry.'],
 7:['The entered lobby establishes the frame for the first left and the subsequent dining-hall left.'],
 9:['The banquet hall has been entered; near the door refers to the source hall doorway.'],
 10:['The agent has exited the original bedroom into the hallway; the blue-floral-bedroom entry is still unperformed.'],
 11:['The explicitly reached hallway end establishes where the next left is taken.'],
 12:['The initial left and room exit are complete; continue in the hall before selecting the left bedroom.'],
 13:['The far bedroom doorway is crossed; the hallway/corner route and home-entrance stop remain.'],
 15:['The bedroom exit establishes the region and count origin for the first door on the right; entering that door and turning right again remain.'],
 16:['The bedroom entry is complete; preserve the same bed and the left window set for the remaining route.'],
 17:['The bird statue has been passed on the source route; the cabinet-identified bedroom entry remains.'],
 20:['The coupled living-room maneuver retains its participial attachment; the stair ascent and third-tile placement remain.'],
 22:['The second doorway exit has occurred; the next right and table/stair route remain.'],
 23:['The window-side doorway crossing establishes the hallway context for the next right.'],
 25:['The living room has been entered; the plant table is a reference on the way to the behind-couch waiting position.'],
 27:['The open area establishes the next right-turn frame; the living-room right turn has its own later owner.'],
 30:['The staircase remains the spatial reference for the first room to its left; reaching its bottom does not supply a new egocentric left.'],
 34:['Actual hallway entry is complete; the right turn and locker-room entry remain.'],
 35:['Actual slight-right hallway entry is complete; preserve the same hallway frame for the subsequent right turn and third left-hand door.'],
}

TRANSFER = {
 2:'Inherit a completed stair/turn pose when unique, then keep the later trigger and exact terminal placement attached to the remaining approach.',
 4:'Use expected facing as an orientation cue, identify and cross the requested door, and keep observation separate from a visit goal.',
 5:'Bind target-identifying relations before selection; distinct completed transitions may expose useful goals, while a faithful coarse alternative needs its own C10 assessment.',
 11:'Use an explicitly stated corridor-end turn to bound that traversal; preserve the subsequent turn, entry and terminal doorway placement.',
 13:'Preserve an open-door adjective as object state while executing the source crossing; add door operation only when the source commands it.',
 15:'Retain the completed exit that establishes an ordinal selection region; keep the count class, right-side frame and later second turn distinct.',
 18:'Keep the until condition on its hallway movement and the bedroom-door placement on the same identified endpoint; assess separate placement by its real objective.',
 20:'Preserve the attachment of simultaneous/participial movement before evaluating a cut; retain the later bounded stair and ordinal placement.',
 21:'Bind a top-wait and step count to one ascent; a completion refinement does not create a second ascent.',
 23:'Preserve an expected observation without promoting it to an extra visit; crossing and the final specified arrival still require their own source events.',
 28:'Treat the center/right relation as the door-selection condition and the source-directed destination as an event without inventing a physical STOP.',
 30:'Keep an object-relative left/right relation tied to that object; arrival near the object does not convert the relation to the agent heading.',
 35:'Keep a modifier on its source action when a different attachment is not uniquely supported; complete actual region entry before inheriting that region.',
}


def _all_quotes_valid(audit, stage):
    for key in ('entry', 'target', 'process', 'ending', 'conditions'):
        for quote in audit[key]['candidate_quotes']:
            if not quote or quote not in stage:
                raise ValueError('Stale authored '+key+' quote: '+repr(quote))


def author_generator(row, number):
    source = row['input']['original_instruction']
    out = row['output']
    old = deepcopy(out)
    notes = row['teaching_notes']
    skills, lesson, counter = LESSONS[number]
    reusable = TRANSFER.get(number) or notes.get('reusable_rule') or notes.get('transfer_rule')
    if not reusable:
        raise ValueError('Missing evaluated transfer rule: '+row['template_id'])
    notes.update(case_rationale=lesson, case_specific_focus=lesson,
                 primary_skills=skills.split(), counter_example_boundary=counter,
                 reusable_rule=reusable, transfer_rule=reusable,
                 five_element_focus='Check Entry, Target, Process, Ending and Conditions against this case-specific source and candidate evidence; retain the relevant relation and its scope.')
    row['decision']['rationale'] = lesson
    if out['status'] != 'ok':
        return
    if number in CANDIDATE_REPAIRS:
        out['subtasks'] = deepcopy(CANDIDATES[number])
        row['decision']['mode'] = 'split' if len(out['subtasks']) > 1 else 'keep'
    parts = out['subtasks']
    if len(parts) != len(old['stage_audit']) or len(parts) != len(ENDINGS[number]):
        raise ValueError('A changed stage count needs a separate explicit mapping: '+row['template_id'])
    audits = deepcopy(old['stage_audit'])
    # Target and ending corrections are per-case authored, never last-verb rules.
    specs = deepcopy(ENDINGS[number])
    if number in (22, 28, 32):
        kind, q, scope, target = specs[-1]
        specs[-1] = ('explicit_event', q, scope, target.replace('final directed target','source-directed destination'))
    if number == 5:
        # Retain the evaluated candidate's supported anchors and exact wording.
        specs[1] = ('explicit_event','enter the room at the end of the hallway.','none','The room entered at the explicitly stated hallway end.')
        specs[2] = ('terminal_goal_directive','walk towards the circular tables in the middle.','none','The circular tables in the already entered large room, approached without a stated arrival threshold.')
    for i, (audit, (kind, q, scope, target)) in enumerate(zip(audits, specs)):
        stage = parts[i]
        evidence(parts, i, q)
        audit['target'] = field(target, q)
        audit['ending'] = dict(kind=kind,
            text=target + (' The source directs a final approach without specifying arrival or STOP.' if kind == 'terminal_goal_directive' else ' This is the source-directed completion event; it does not add a physical STOP.'),
            candidate_quotes=[q], stop_scope=scope)
        if stage != old['subtasks'][i]:
            audit['process'] = field(stage, stage)
            if any(q not in stage for q in audit['entry']['candidate_quotes']):
                if i == 0:
                    raise ValueError('First-stage context changed without an explicit source mapping')
                audit['entry'] = dict(mode='inherited_pose',
                    text=CONTEXT[number][i-1], candidate_quotes=[])
        # A listed override refines that field; an absent entry preserves evidence.
        if number in CONDITIONS and CONDITIONS[number][i]:
            phrases = CONDITIONS[number][i]
            for phrase in phrases:
                evidence(parts, i, phrase)
            audit['conditions'] = field('Operative constraints: '+'; '.join(phrases), *phrases)
        elif stage != old['subtasks'][i] and any(q not in stage for q in audit['conditions']['candidate_quotes']):
            raise ValueError('Changed condition needs exact authored evidence: '+row['template_id'])
        if number == 28:
            audit['conditions'] = field('Select the center door in the right-side set after the stair-bottom pass.', 'center door on right')
        if number == 30 and i == 1:
            audit['source_quotes'] = ['Go to the entrance of the first room to the left of the staircase.', 'Wait by the chair.']
            # Exact capitalization varies in the source; use original event quotes
            # unless the explicitly proposed fragments both occur verbatim.
            if not all(q in source for q in audit['source_quotes']):
                audit['source_quotes'] = deepcopy(old['stage_audit'][i]['source_quotes'])
        if number == 35:
            audit['source_quotes'] = (['Exit the pool area and walk toward the stairs', 'enter the hallway to the slight right past the chair'] if i == 0 else ['turn right and enter the third door on the left', 'wait by the lockers'])
        for quote in audit['source_quotes']:
            if not quote or quote not in source:
                raise ValueError('Source evidence changed: '+row['template_id'])
        if len(parts) > 1:
            context = CONTEXT.get(number)
            if context is None or len(context) != len(parts)-1:
                raise ValueError('Missing explicit carrying-state mapping: '+row['template_id'])
            audit['carryover'] = [context[i]] if i < len(parts)-1 else []
        _all_quotes_valid(audit, stage)
    out['stage_audit'] = audits
    hands = deepcopy(old['handoffs'])
    if len(hands) != len(parts)-1:
        raise ValueError('Missing evaluated handoff inventory')
    for i, hand in enumerate(hands):
        context = CONTEXT[number][i]
        if parts[i] != old['subtasks'][i] or hand['preceding_exit']['candidate_quote'] not in parts[i]:
            hand['preceding_exit'] = dict(text=audits[i]['ending']['text'],candidate_quote=specs[i][1])
        if parts[i+1] != old['subtasks'][i+1] or hand['next_entry']['candidate_quote'] not in parts[i+1]:
            hand['next_entry'] = dict(text=context,candidate_quote=parts[i+1].split('. ')[0].rstrip('.')+'.' if '. ' in parts[i+1] else parts[i+1])
            if hand['next_entry']['candidate_quote'] not in parts[i+1]:
                raise ValueError('No exact next-entry event quote')
        hand['shared_context'] = [context]
        hand['handoff_rationale'] = context+' '+reusable
    out['handoffs'] = hands


def finalize_detail(rows):
    """Keep local semantic repairs and explain calibrated grouping judgments."""
    r = rows['R2R-CORE-R06']
    r['provenance']['curation_basis'] = 'Authored comparison of faithful coarse and multi-stage organizations; not a navigation-ground-truth judgment.'
    a = r['expected_review']
    for layer in a['layer_checks']:
        if layer['layer'] == 'L5_grouping':
            layer['conclusion'] = ('This candidate explicitly preserves the office traversal, selected doorway, hall-end room entry and final table approach in usable order. A three-stage form can expose those objectives; no specific dependency or local-focus loss is established for this faithful coarse form. Other real missed-goal cases remain C10 defects.')
    for tid in ('R2R-CORE-R04','R2R-DIAG-25'):
        row=rows[tid]
        row['teaching_notes']['transfer_rule']='Assess a preparatory turn together with the ascent it enables in this source; a turn with its own source-defined observation or placement objective can be independent.'
    for row in rows.values():
        notes=row['teaching_notes']
        if row['role']=='reviewer' and not notes.get('reusable_rule'):
            notes['reusable_rule']=notes.get('transfer_rule') or notes.get('case_specific_focus')
