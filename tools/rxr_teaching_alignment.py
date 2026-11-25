"""Finite source-local RxR evidence repairs, applied by the offline authoring chain.

Source instructions, candidate routes, boundaries, identities and retrieval tags
are unchanged. No online semantic heuristic or automatic word-count rule exists.
"""
from __future__ import annotations

from copy import deepcopy
from tools.rxr_positive_repairs import conditions, field, stages_and_checks

LESSONS = {
    6: ('Retain the bathroom-entry leg before the actual turn-around and return. Bind the initial couch/TV frame to the first turn, the veer-right return to its own event, and the TV-left/chairs-right relation to the final traversal. Seven or eight is an approximate chair count, not a branch.',
        'Match the two turn-around events to their own stages. Verify bathroom entry, the subsequent return and veer, approximate chair count, path-wide TV/chair sides and final between-objects position independently.'),
    23: ('Keep the stair-top right turn with its established completion, then descend and exit through the glass doors. On the patio, pool-right/home-left constrains the movement; mostly to the end remains approximate, while the pool edge is the stop and the plant is a terminal reference.',
         'Use the completed stair-top turn and actual glass-door exit for the two handoffs. Distinguish the sustained pool/home relation from the final plant cue, preserve the approximate patio extent, and require the pool-edge stop rather than a visit to the plant.'),
    27: ('Preserve the door selected relative to the bear head, the bounded two-step approach and final bed-side position. The window-facing state and conditional leftward view are different relations; the conditional description alone does not command another turn.',
         'Check door identity, two-step extent, final bedside placement and window-facing evidence together. Do not turn the conditional bed observation into an unconditional left turn or weaken the stated final placement.'),
}


def align_positive(rows):
    protected = {tid: deepcopy(row['output']['subtasks'] if row['role'] == 'generator'
                              else row['review_input']['candidate']) for tid, row in rows.items()}
    for role, prefix in [('generator', 'RxR-GEN-'), ('reviewer', 'RxR-REV-')]:
        row = rows[prefix + '006']
        stages, checks, hands = stages_and_checks(row)
        conditions(row, 0,
                   'Initial couch-facing view has TV left and coffee table ahead. The 180-degree turn is an orientation change; the later left turn selects bathroom entry.',
                   'Facing the couch, with the TV on the left and the coffee table straight ahead',
                   'turn 180 degrees and exit the room', 'take a left into the bathroom')
        conditions(row, 1,
                   'After bathroom entry, turn around and return by the specified veer-right path. Preserve the open-area reference relations, approximate chair count, three stools, the later TV-left/chairs-right traversal and final between-objects placement.',
                   'Once in the bathroom', 'turn 180 degrees and head back',
                   'not straight, but veer right',
                   'just to the left of where you came out of and to the right of the small area between the bar',
                   '7 or 8 white chairs', 'To the left are 3 bar stools',
                   'in front of you is a TV on a translucent wall',
                   'with the TV and translucent wall on your left and the dining room chairs on your right',
                   'between the dining room chairs and the TV')
        # The paired review already has event-local source ownership. Bind the
        # Generator to those explicitly indexed requirements, not substring proximity.
        coverage = rows['RxR-REV-006']['expected_review']['source_coverage']
        for index, check in enumerate(checks):
            check['source_quotes'] = list(dict.fromkeys(c['source_quote'] for c in coverage
                if any(ev['subtask_index'] == index for ev in c['candidate_evidence'])))
            check['carryover'] = (['Bathroom entry is complete; the next stage performs its own turn-around and return.'] if index == 0 else [])
        hands[0]['shared_context'] = [dict(kind='entity_or_region', text='The bathroom entered by the preceding left turn; the return remains unperformed.')]
        row['teaching_notes']['five_element_focus'] = 'Keep the initial frame, bathroom-entry completion, actual return, approximate chair count, sustained side constraints and final between-objects position tied to their own events.'

        row = rows[prefix + '023']
        stages, checks, hands = stages_and_checks(row)
        conditions(row, 0,
                   'Preserve the initial closet-facing state, between-furniture passage, bed-relative path, stair ascent and the right turn at its top.',
                   'facing some brown closet doors', 'between the bathtub and all of the wood furniture',
                   'taking a left and walking toward the bed', 'to the left of the bed',
                   'Go up a few stairs.', 'At the top of these stairs, turn to the right.')
        if 'Now we will go up a few stairs.' not in checks[0]['source_quotes']:
            checks[0]['source_quotes'].append('Now we will go up a few stairs.')
        checks[1]['entry'] = dict(mode='explicit_context',
            text='At the stair top after the preceding right turn; the descent is not yet performed.',
            candidate_quotes=['From the top of these stairs'])
        conditions(row, 1,
                   'The descent is a stair or two. Preserve the piano ahead, passage on its left past the fireplace, and the pool ahead when exiting through the glass doors.',
                   'a stair or two', 'piano directly in front of you', 'to the left of the piano',
                   'passing a large fireplace', 'Walk out the glass doors with a pool directly in front of you.')
        checks[0]['carryover'] = ['At the top of these stairs after the stated right turn; the downward stair movement remains next.']
        checks[1]['carryover'] = ['Outside the glass doors with the pool ahead; the next left turn remains unperformed.']
        checks[2]['carryover'] = []
        hands[0]['shared_context'] = [dict(kind='inherited_context', text=checks[0]['carryover'][0])]
        hands[1]['shared_context'] = [dict(kind='inherited_context', text=checks[1]['carryover'][0])]
        row['teaching_notes']['five_element_focus'] = 'Pool-right and home-left apply during patio movement. Mostly to the end remains approximate. The stop is at the pool edge; the plant-left observation identifies the final position.'

        row = rows[prefix + '027']
        _, checks, _ = stages_and_checks(row)
        checks[0]['ending']['candidate_quotes'] = [
            'Once you are there, you should be facing the big window',
            'We should be standing on the left side of the bed, and you are done.']
        conditions(row, 0,
                   'Select the door to the right of the bear head, preserve the two-step extent and final window-facing/bed-side state. Turning left describes a conditional view, not an unconditional additional turn.',
                   'the door that is on the right of the bear head',
                   'Take two more steps towards the foot of the bed.',
                   'Once you are there, you should be facing the big window',
                   'if we turn to the left, we should see the bed',
                   'We should be standing on the left side of the bed, and you are done.')
        for number, lessons in LESSONS.items():
            notes = rows[prefix + f'{number:03d}']['teaching_notes']
            notes['case_rationale' if role == 'generator' else 'case_specific_focus'] = lessons[0 if role == 'generator' else 1]

    for tid in ('RXR-CORE-G06', 'RXR-CORE-R06'):
        conditions(rows[tid], 0,
                   'About halfway limits the same staircase descent; stop and wait at that approximate position, not after a full descent.',
                   'about halfway down the staircase', 'then stop and wait there.')
    for tid, previous in protected.items():
        row = rows[tid]
        current = row['output']['subtasks'] if row['role'] == 'generator' else row['review_input']['candidate']
        if current != previous:
            raise ValueError('Evidence refinement changed executable text: ' + tid)


def align_diagnostics(rows):
    """Repair declared stop losses without broadening unrelated dimension failures."""
    for number in range(1, 21):
        row = rows[f'RxR-DIAG-{number:02d}']
        for finding in row['expected_review']['findings']:
            finding['repair']['instruction'] = (
                'Restore the cited source meaning at this occurrence, including any source-required stop. '
                'Preserve unaffected route text; do not invent an unsupported STOP, traversal or endpoint.')
    for number in (7, 17):
        row = rows[f'RxR-DIAG-{number:02d}']
        review = row['expected_review']
        review['dimensions']['closure_handoff'] = 'issue'
        finding = review['findings'][0]
        finding['failed_layer'] = 'L3_stage_checks'
        finding['related_dimensions'] = ['closure_handoff']
        finding['repair']['instruction'] = (
            'Replace the unsupported continuation with the original stop at the cited position. '
            'Restore that required stopping condition; preserve the preceding route and do not invent other stops or destinations.')
        row['teaching_notes']['review_principle'] = (
            'The changed terminal requirement affects both source fidelity and this stage\'s ending. '
            'There is no adjacent handoff in the one-stage candidate, so L4 remains not applicable. '
            'Do not infer an unrelated grouping defect from this local stop loss.')
        for layer in review['layer_checks']:
            if layer['layer'] == 'L3_stage_checks':
                layer['conclusion'] = 'The required terminal stop is lost; the stage continues beyond its prescribed endpoint.'
            elif layer['layer'] == 'L4_handoffs':
                layer.update(status='not_applicable', finding_indices=[],
                             conclusion='One stage has no adjacent handoff; its terminal closure is checked separately by L3.')
