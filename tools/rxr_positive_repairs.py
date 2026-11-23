"""Explicit, source-reviewed edits to existing RxR positive teaching assets.

Offline authoring only. No route inference, model calls, retrieval changes or
runtime acceptance decisions are performed here. Every quote is checked against
its declared stage. Source strings, identities and retrieval tags stay frozen.
"""
from __future__ import annotations
import copy


def evidence(stages, index, quote):
    if quote not in stages[index]:
        raise ValueError(f'Authored evidence absent from stage {index}: {quote!r}')
    return {'subtask_index': index, 'quote': quote}


def field(text, *quotes):
    return {'text': text, 'candidate_quotes': list(quotes)}


def replace_candidate(row, index, old, new):
    """Apply a unique authored route edit; preserve source and source quotations."""
    if row['role'] == 'generator':
        stages = row['output']['subtasks']; audit = row['output']
    else:
        stages = row['review_input']['candidate']['subtasks']; audit = row['expected_review']
    if stages[index].count(old) != 1:
        raise ValueError(f"{row['template_id']}: nonunique authored replacement {old!r}")
    stages[index] = stages[index].replace(old, new, 1)
    def visit(obj):
        if isinstance(obj, list):
            return [visit(x) for x in obj]
        if isinstance(obj, dict):
            return {k: (v if k in ('source_quote','source_quotes') else visit(v)) for k,v in obj.items()}
        return obj.replace(old, new) if isinstance(obj, str) else obj
    revised = visit(audit)
    if row['role'] == 'generator':
        row['output'] = revised
    else:
        row['expected_review'] = revised


def stages_and_checks(row):
    if row['role'] == 'generator':
        return row['output']['subtasks'], row['output']['stage_audit'], row['output']['handoffs']
    return (row['review_input']['candidate']['subtasks'],
            row['expected_review']['stage_checks'], row['expected_review']['handoffs'])


def end(row, index, text, quote, *, kind=None, stop=None, target=None):
    stages, checks, hands = stages_and_checks(row)
    evidence(stages, index, quote)
    old = checks[index]['ending']
    checks[index]['ending'] = dict(kind=kind or old['kind'], text=text,
                                  candidate_quotes=[quote], stop_scope=stop or old['stop_scope'])
    if target is not None:
        checks[index]['target'] = field(target, quote)
    for h in hands:
        if h['from_subtask_index'] == index:
            h['preceding_exit'] = {'text': text, 'candidate_quote': quote}


def conditions(row, index, text, *quotes):
    stages, checks, _ = stages_and_checks(row)
    for q in quotes:
        evidence(stages, index, q)
    checks[index]['conditions'] = field(text, *quotes)


def apply_stage_repairs(row):
    """The same authored event definitions constrain both independently read roles."""
    tid = row['template_id']
    core = tid.startswith('RXR-CORE-')
    number = int(tid[-2:] if core else tid[-3:])
    stages, checks, hands = stages_and_checks(row)
    if core:
        if number == 1:
            end(row,1,'Stand between the sink and bathtub inside the washroom; the entry trigger is not the ending mechanism.',
                'Once inside the washroom, stand between the sink and the bathtub.',kind='explicit_event',stop='terminal')
        elif number == 2:
            end(row,0,'Reach the second doorway on the right after passing the two paintings; not entering the first doorway is a constraint, not proof of arrival.',
                'until you reach the second doorway on your right',kind='explicit_event',stop='none',target='The second doorway on the right of the prescribed hallway traversal.')
            conditions(row,0,'Pass both paintings on the left, count doorways from the original traversal, and do not enter the first doorway.',
                       'passing the two paintings on your left','second doorway on your right','Do not enter the first doorway.')
        elif number == 3:
            end(row,0,'Enter the open area after the left turn before dining-room entry. An entry completes without an additional physical stop.',
                'go into the open area.',kind='explicit_event',stop='none')
        elif number == 4:
            end(row,1,'Cross the kitchen and pass through the archway into the dining room; Once inside the kitchen supplies entry, not completion.',
                'cross it and go through the archway into the dining room.',kind='explicit_event',stop='none')
        elif number == 5:
            end(row,0,'Enter the bathroom through the selected first right-hand door. Wall colour and doorway proximity identify the door but do not establish entry.',
                'enter the bathroom through the first door on your right',kind='explicit_event',stop='none',target='The bathroom interior reached through the identified first right-hand door.')
            conditions(row,0,'Select the first right-hand bathroom doorway among the close pair using the darker-painted wall.',
                       'first door on your right','two doorways close together','bathroom doorway is in the darker-painted wall')
        elif number == 7:
            end(row,0,'Complete the approach beside the white table, with the table on the left at that position; the side relation alone does not establish proximity.',
                'until you are next to it. At that position, the table should be on your left.',kind='linked_trigger_or_refinement',stop='none',target='The beside-table position with the table on the left.')
    else:
        if number == 2:
            for a in checks:
                for name in ('target','ending'):
                    a[name]['text'] = a[name]['text'].replace('black bench on its right','black bench on your right')
        elif number == 5:
            end(row,2,'The final approach is refined by the prescribed destination near the sink. No metric tolerance or extra STOP is supplied.',
                'Walk towards the bathroom; your destination is near the sink.',kind='linked_trigger_or_refinement',stop='none',target='The prescribed final position near the sink, not merely the visible bathroom.')
        elif number == 7:
            end(row,0,'Step through the identified door, then continue directly across into the opposite hallway.',
                'Step through that door. Once you are outside, continue directly across into the hallway opposite.',kind='explicit_event',stop='none')
        elif number == 9:
            end(row,0,'Complete the prescribed step toward the wooden news stand after the slight right turn. News stand names furniture, not a stop command.',
                'Turn slightly to the right and take a step forward to the wooden news stand holding a pile of books.',kind='bounded_action',stop='none')
        elif number == 12:
            end(row,0,'Exit the closet and enter the hallway through the open door. The lights and neighbouring room are identifying observations, not entry evidence.',
                'exit, and enter the open door which will take you inside a hallway.',kind='explicit_event',stop='none',target='The hallway entered through the open door after exiting the closet.')
        elif number == 14:
            end(row,2,'Complete the final step to the position directly underneath the shower head.',
                'Take another step forward until you are right underneath the shower head.',kind='bounded_action',stop='none',target='The position directly underneath the shower head.')
        elif number == 15:
            conditions(row,0,'The first open door is to the left; approach its front before using the other door directly ahead to enter the ladies bathroom. Right in front intensifies front, not right-side selection.',
                       'Directly to the left is an open door.','until you are right in front of it','other open door directly in front of you','until you are inside the ladies\' bathroom')
            conditions(row,1,'Inside the bathroom the sink is left and stalls ahead; enter the open stall, retain the window ahead and toilet left, and stop inside.',
                       'the sink is on the left','bathroom stalls are right in front of you','Walk inside the open bathroom stall.','toilet to your left','Stop inside this bathroom stall.')
        elif number == 19:
            replace_candidate(row,1,'At the table, look towards the left.','Look towards the left.')
            stages, checks, hands = stages_and_checks(row)
            end(row,0,'Cross the doorway to the source-described position in front of the two white chairs. Expected standing does not add an intermediate stop.',
                'Walk through this doorway. You will be standing in front of two white chairs.',kind='explicit_event',stop='none',target='The position in front of the two white chairs reached through the doorway.')
        elif number == 21:
            # The source predicts the intermediate standing state but gives its
            # explicit stop only before the podium in the final stage.
            checks[0]['ending']['stop_scope'] = 'none'
        elif number == 23:
            replace_candidate(row,2,'walk to the end of the brick patio.','walk to the end, mostly to the end of the brick patio.')
            conditions(row,2,'Keep the pool on the right and the home on the left during the patio movement; retain the approximate extent. Stop at the pool edge, where the plant is a left-side reference.',
                       'With the pool on the right and the home to your left','mostly to the end of the brick patio','Stop when you are at the edge of the pool.','There will be a potted plant on your left-hand side.')
        elif number == 32:
            end(row,1,'Reach the middle of the living-room doorway and obey the explicit instruction not to move further.',
                'Move forward until you are in the middle of the doorway that leads into a living room. Once you are there, do not move.',kind='explicit_event',stop='terminal',target='The middle of the doorway leading into the living room.')
        elif number == 35:
            replace_candidate(row,2,'a narrow opening with a closed door.','a narrow opening with a closed door and now it will open for you.')
            conditions(row,0,'Preserve the specified step counts and ordered left/right turns. Once again denotes repetition of a turn, not a separate prerequisite.',
                       'one step','two steps','Turn left once again')
            conditions(row,2,'Repeat the right turn; retain the closed-to-open door state and select the narrow opening rather than the previously closer one. No door-opening action is invented.',
                       'Turn right once again','closed door and now it will open for you','not the one that was closest to you earlier','Take a step inside')
    # A stage boundary never adds a stop, but cannot cancel an explicit source stop.
    for h in stages_and_checks(row)[2]:
        if h['handoff_rationale'] == 'The next stage continues from the immediately preceding intended endpoint; no extra physical stop or unmentioned route is introduced.':
            h['handoff_rationale'] = 'The cited preceding outcome supports the next first unperformed action. The boundary adds no physical stop or route; any stop explicitly required by the source remains mandatory.'


# Source requirement numbers remain local to each review, never shared role IDs.
# Each boundary below was read against its source, actual exit and next action.
HANDOFF_IDS = {
    1: [[2,3,4]], 2: [[6,7,8]], 3: [[3,4]], 4: [[3,4]],
    5: [[3,4],[5,6]], 6: [[2,3,4]], 7: [[2,3]],
    9: [[4,5],[8,9]], 11: [[4,5]], 12: [[3,4],[7,8]],
    14: [[6,7,8],[13,14]], 15: [[5,6,7,8]], 16: [[3,4]],
    19: [[4,5,12]], 20: [[5,6]], 21: [[3,4,5]],
    23: [[5,11],[13,7]], 25: [[4,5,10]],
    28: [[2,3],[7,8]], 29: [[3,4],[5,6,7]],
    32: [[4,5]], 35: [[5,6,7],[9,10]],
}


def repair_coverage(row):
    """Explicit corrections; no nearest-string or keyword semantic alignment."""
    if row['role'] != 'reviewer':
        return
    from host.compile import runtime_review_output
    audit = row['expected_review']
    stages = row['review_input']['candidate']['subtasks']
    src = row['review_input']['original_instruction']
    tid = row['template_id']
    if tid.startswith('RXR-CORE-'):
        # Core source units are short and remain ordered in the existing table.
        # The cited completion fields above, rather than arbitrary SRC numbers,
        # are the evidence for the existing boundary.
        audit = runtime_review_output(row)
        row['expected_review'] = audit
        for h in audit['handoffs']:
            ids = []
            for c in audit['source_coverage']:
                for ev in c['candidate_evidence']:
                    if (ev['subtask_index'] == h['from_subtask_index'] and
                        (h['preceding_exit']['candidate_quote'] in ev['quote'] or ev['quote'] in h['preceding_exit']['candidate_quote'])) or (ev['subtask_index'] == h['to_subtask_index'] and
                        (h['next_entry']['candidate_quote'] in ev['quote'] or ev['quote'] in h['next_entry']['candidate_quote'])):
                        ids.append(c['requirement_id']); break
            if ids:
                h['source_requirement_ids'] = list(dict.fromkeys(ids))
        return
    n = int(tid[-3:])
    def setrow(k, pairs, *, source=None, requirement=None):
        c = next(x for x in audit['source_coverage'] if x['requirement_id'] == f'SRC-{k:02d}')
        if source is not None:
            if source not in src: raise ValueError(f'{tid}: absent authored source {source!r}')
            c['source_quote'] = source
        c['candidate_evidence'] = [evidence(stages,i,q) for i,q in pairs]
        if requirement is not None: c['requirement'] = requirement
    def add(k, source, pairs, requirement):
        if any(c['requirement_id'] == f'SRC-{k:02d}' for c in audit['source_coverage']):
            raise ValueError(f'{tid}: duplicate authored requirement {k}')
        if source not in src: raise ValueError(f'{tid}: missing source {source!r}')
        audit['source_coverage'].append(dict(requirement_id=f'SRC-{k:02d}',source_quote=source,requirement=requirement,
                                            candidate_evidence=[evidence(stages,i,q) for i,q in pairs],status='covered'))
    if n == 2:
        setrow(1,[(0,'You are standing inside a living room.')],requirement='Preserve the initial living-room context; it is not a newly commanded stop.')
        setrow(4,[(0,'then turn left and take a few steps towards the two entrances in front.'),(0,'Then turn left.')])
        setrow(5,[(0,'There should be a wine room on your right.'),(0,"The source gives conflicting left/right descriptions for the glass window ('on your right' and 'on your left'), so treat the window only as an uncertain visual reference; an open door is in front of you.")])
        setrow(7,[(0,'Go towards the open door which has a black bench on your right until you reach that open door.')],source='go towards the open door which has a black bench, on your right',requirement='The bench is on your right in this event; do not transfer the relation to the door as subject.')
        # These notes were copied from a negative case into a PASS positive.
        for layer in audit['layer_checks']:
            if 'note' in layer:
                layer.pop('note')
                layer['conclusion'] = 'The candidate retains both window-side descriptions as uncertainty, preserves the agent-relative bench cue and keeps the ordered route. No candidate-created omission is asserted.'
    elif n == 3:
        setrow(4,[(1,'From the right side of the dining table, head to the base of the stairs in front of you.')])
    elif n == 5:
        setrow(5,[(1,'On your right there is an open door, and on your left there is a bedroom.'),(1,'Walk towards the bedroom, turn left and walk towards the edge of the bed.'),(1,'Turn around.')])
        setrow(6,[(2,'Now you are facing a short hallway.'),(2,'Walk towards the hallway.'),(2,'In front of you there is the bathroom.'),(2,'Walk towards the bathroom; your destination is near the sink.')])
    elif n == 7:
        setrow(2,[(0,'Step through that door.'),(0,'Once you are outside, continue directly across into the hallway opposite.')])
    elif n == 9:
        setrow(1,[(0,'You are currently looking into a whiteboard.'),(0,'Turn around and face right.')],source="You're currently looking into a whiteboard. Turn around, and face right.",requirement='The first turn-around/right-facing event occurs from the initial whiteboard context.')
        setrow(3,[(0,'Turn slightly to the right')],requirement='Retain the slight right turn before the step toward the news stand, not either later turn-around.')
        setrow(4,[(0,'take a step forward to the wooden news stand holding a pile of books.')],requirement='Take the specified step toward the news stand; stand here is part of the furniture name, not a stopping command.')
        setrow(5,[(1,'Turn around and face right.')],source='Take a step forward to the wooden news stand, holding a pile books. Turn around, and face right.',requirement='After the news-stand step, execute the second turn-around/right-facing event before passing the long tan table.')
    elif n == 11:
        setrow(4,[(0,'Take a small step inside this room, then walk back out from the place you came.'),(1,'From that wooden doorway, turn right into the wooden doorless doorway and into a small hall.')])
        setrow(6,[(1,'Stop at the entrance of it.'),(1,'There will be a fire extinguisher on the wall next to you.')])
    elif n == 12:
        setrow(3,[(0,'Turn left from this closet, exit, and enter the open door which will take you inside a hallway.'),(0,'There are hanging black lights on your right and a railing; on your left there is another room with brown furniture.')])
        setrow(8,[(2,'Go near the washroom door and turn around.'),(2,'From this point, go near the blue throw.'),(2,'This is where your destination ends.')])
    elif n == 14:
        setrow(9,[(1,'Walk towards the hallway.'),(1,'When you are there, you will see a room.')])
        setrow(12,[(1,'Walk towards the right side of the bed.'),(1,'When you are at the right side of the bed, you will see an open door on the right.')])
        setrow(16,[(2,'Walk inside that area.'),(2,'In front of you is a shower area with a black shower head and shower hose.')])
    elif n == 15:
        q="Then walk towards the other open door directly in front of you until you are inside the ladies' bathroom."
        setrow(5,[(0,q)])
        setrow(6,[(0,q)],requirement='The repeated bathroom-entry wording elaborates the same entry, not the later stall entry or a second bathroom traversal.')
    elif n == 19:
        setrow(1,[(0,'You are standing in a living room.')],requirement='Preserve the initial living-room context, not a new completion or stop.')
        setrow(5,[(1,'From in front of the two white chairs, walk towards the white sofa on your left.')])
        setrow(8,[(1,'Look towards the left.'),(1,'You can see a white bench with some pillows on it; walk towards this bench.')])
        setrow(9,[(1,'To the left you will see an open door; walk towards this door.')])
        add(12,"You'll be standing in front of two white chairs.",[(0,'You will be standing in front of two white chairs.')],'Preserve the expected chair-front state after doorway crossing; it is not an extra intermediate STOP.')
    elif n == 20:
        setrow(5,[(0,'Do not go outside; move near the opening and stand there.')])
        for layer in audit['layer_checks']:
            note = layer.pop('note',None)
            if note: layer['conclusion'] += ' ' + note
    elif n == 21:
        setrow(7,[(1,'On your left should be a bathtub with a window above it;'),(1,'in front of you should be two podiums, one with a sink and one with something else.')])
    elif n == 22:
        add(4,'Just standing in the threshold, you are done.',[(0,'Just standing in the threshold, you are done.')],'Preserve the final threshold placement, not a full-room destination.')
    elif n == 23:
        setrow(2,[(0,'Walk between the bathtub and all of the wood furniture, taking a left and walking toward the bed.'),(0,'Exit the bedroom.')])
        setrow(8,[(2,'With the pool on the right and the home to your left, walk to the end, mostly to the end of the brick patio.')],requirement='Preserve the approximate extent and pool-right/home-left relation during the patio movement, not only at its endpoint.')
        add(11,'Going down a stair or two.',[(1,'From the top of these stairs, go down a stair or two.')],'Descend the approximate one-or-two-stair amount from the established top.')
        add(12,'You will see a piano directly in front of you.',[(1,'You will see a piano directly in front of you.')],'Retain the expected piano ahead after the small descent.')
        add(13,'Walking out the glass doors with a pool directly in front of us.',[(1,'Walk out the glass doors with a pool directly in front of you.')],'Exit through the glass doors before the outdoor left turn.')
    elif n == 25:
        setrow(1,[(0,'For your start point, you are facing a wooden garden arbor.'),(0,'Turn around so that you can see the rows of white chairs to your right and left.')])
        setrow(6,[(1,'Move one step inside; it looks like a dining room or a banquet hall.')])
        setrow(7,[(1,'Turn to the left.'),(1,'You will move in front of a column and see a banquet table to your left and one to your right, closest to the flat-screen TV on the wall.')])
        add(9,"And from that column that is supporting the balcony above you will see a bench, a black iron bench.",[(0,'From that column supporting the balcony above, you will see a black iron bench.')],'Identify the first bench from the balcony-supporting column before selecting the opposite second bench.')
        add(10,"you will see there's an open doorway.",[(0,'You will see an open doorway.')],'The open doorway is seen after the hop, not already reached or entered.')
    elif n == 28:
        setrow(8,[(2,'Now you are facing a table with books on top.'),(2,'Turn right.')])
        setrow(10,[(2,'Turn left, leaving the small round table on your right.')])
        setrow(13,[(2,'Walk past the staircase towards the right.')])
    elif n == 29:
        setrow(4,[(0,'Walk to it.'),(1,'From the plant in the middle of the stairs, look to your right and climb up the remaining stairs to the end.')])
        setrow(5,[(1,'Then, to our left, we will be facing a closed door; walk to it.')])
        setrow(6,[(2,'the curved stairs')],requirement='Retain the curved-stair identity used in the final selection; do not cite the earlier plant as evidence for this later referent.')
    elif n == 32:
        setrow(7,[(1,'Move forward until you are in the middle of the doorway that leads into a living room.'),(1,'Once you are there, do not move.')])
    elif n == 35:
        setrow(10,[(2,'Turn right once again and you will see a narrow opening with a closed door and now it will open for you.')],requirement='Preserve the repeated turn and the described door opening state; do not insert a door-opening action.')
    # Shorten mechanically identical evidence only when the original quotation
    # has exactly one occurrence in exactly one stage. Never guess occurrence.
    for c in audit['source_coverage']:
        q = c['source_quote']
        matches = [i for i,s in enumerate(stages) if q in s and s.count(q)==1]
        if len(matches)==1:
            c['candidate_evidence'] = [evidence(stages,matches[0],q)]
    row['expected_review'] = runtime_review_output(row)
    audit = row['expected_review']
    if n in HANDOFF_IDS:
        if len(HANDOFF_IDS[n]) != len(audit['handoffs']): raise ValueError(tid)
        for h, numbers in zip(audit['handoffs'], HANDOFF_IDS[n]):
            h['source_requirement_ids'] = [f'SRC-{k:02d}' for k in numbers]
    # Update each review's local traceability from its own explicit indexed map.
    for check in audit['stage_checks']:
        i=check['subtask_index']
        matched=[c for c in audit['source_coverage'] if any(e['subtask_index']==i for e in c['candidate_evidence'])]
        check['source_requirement_ids']=[c['requirement_id'] for c in matched]
        check['source_quotes']=list(dict.fromkeys(c['source_quote'] for c in matched))


def repair(rows):
    for row in rows.values():
        if row['role']=='generator' or '-REV-' in row['template_id'] or row['template_id'].startswith('RXR-CORE-R'):
            apply_stage_repairs(row)
    for row in rows.values():
        if row['role']=='reviewer' and 'DIAG' not in row['template_id']:
            repair_coverage(row)
    # Ground G's illustrative local requirement names against the paired source
    # evidence without introducing a shared runtime ID protocol.
    generators={r['template_id']:r for r in rows.values() if r['role']=='generator'}
    for rev in rows.values():
        if rev['role']!='reviewer' or rev.get('pair_id') not in generators: continue
        gen=generators[rev['pair_id']]
        if gen['output']['subtasks'] != rev['review_input']['candidate']['subtasks']:
            raise ValueError(f"Pair candidate mismatch: {rev['template_id']}")
        if len(gen['output']['handoffs']) != len(rev['expected_review']['handoffs']): raise ValueError('Pair handoff count')
        for gh,rh in zip(gen['output']['handoffs'],rev['expected_review']['handoffs']):
            gh['source_requirement_ids']=copy.deepcopy(rh['source_requirement_ids'])
