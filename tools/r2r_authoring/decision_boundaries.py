"""Small case-local decision boundaries; preserve sources and approved candidates.

An optional expression is not a negative example. Evidence is checked against
source and actual candidate before any teaching asset is emitted.
"""
from copy import deepcopy

SPECS = {
    34: dict(rules=['B2','B4'], source=['Move through door into hallway', 'turn right'],
        candidate=[(0,'go through the door into the hallway.'),(1,'From the hallway, turn right')],
        operation='The preceding stage already establishes hallway entry. Omitting the new From the hallway phrase leaves the next right turn uniquely grounded; prefer inheritance when generating afresh.',
        boundary='The shown anchored candidate remains faithful and acceptable. Do not demand its rewrite merely for verbosity. If a necessary region, referent or counting frame were unclear, retain the shortest supporting anchor.'),
    15: dict(rules=['A3','B2','B4'], source=['Exit the bedroom.', 'first door on your right', 'turn right again'],
        candidate=[(0,'exit the bedroom.'),(1,'After exiting the bedroom'),(1,'first door on your right')],
        operation='The first right-hand door is selected after the bedroom exit; the later right is a distinct turn. Preserve that count origin, either by clear inheritance or a minimal explicit exit anchor.',
        boundary='Do not erase a navigation-critical origin in pursuit of shorter wording. The explicit exit anchor is legal; it is not universally mandatory when the same origin is already unambiguous.'),
    19: dict(rules=['B1','B4'], source=['then turn left.', 'Continue up the stairs and stop.'],
        candidate=[(0,'then turn left. Continue up the stairs and stop.')],
        operation='Here the left turn prepares the ascent. Preserve the coherent source maneuver without inventing a separate turn-completion goal or cosmetically rewriting the source.',
        boundary='A different source explicitly asking to turn and observe or wait may give the turn an independent objective. Do not transfer this KEEP decision by route length alone.'),
    11: dict(rules=['B1','B2'], source=['going straight to the end of the hallway.', 'Turn left and enter the bedroom.'],
        candidate=[(0,'Continue straight to the end of the hallway.'),(1,'turn left and enter the bedroom.')],
        operation='Reaching the stated hallway end establishes the position of the following left turn and bedroom selection. It can support useful local focus, unlike a merely preparatory turn.',
        boundary='The split shown is supported, not a universal obligation. A faithful coarse version is not a C10 defect without a concrete loss of target focus or dependency.'),
    21: dict(rules=['A5','B3'], source=['Go up the three steps and when you get to the top, wait.'],
        candidate=[(0,'Go up the three steps and when you get to the top, wait.')],
        operation='The top and wait refine the same three-step ascent. Keep the bounded ascent and its final wait together; no second climb is requested.',
        boundary='A matching place name does not license moving a final stop across a separately requested later action. Check event identity, intervening order and stop scope together.'),
    30: dict(rules=['A3','B2'], source=['first room to the left of the staircase'],
        candidate=[(1,'the first room to the left of the staircase')],
        operation='Retain the staircase as the reference object at room selection. Reaching its bottom establishes position, not a new egocentric left.',
        boundary='A source saying on your left has a different reference. Do not remove the object-relative phrase as a redundant entry anchor.'),
    35: dict(rules=['A4','B1','B2'], source=['enter the hallway to the slight right past the chair', 'turn right and enter the third door on the left'],
        candidate=[(0,'enter the hallway to the slight right past the chair.'),(1,'Turn right and enter the third door on the left.')],
        operation='The slight-right/chair description belongs to hallway entry. Complete that entry before the later right turn and third-left-door choice; the second stage can inherit this established region.',
        boundary='Do not move past the chair onto an unsupported separate waypoint. An added From phrase cannot substitute for an unperformed crossing.'),
}
REV_RULES = {'A3':'A2','A4':'A2','A5':'A3','B1':'B1','B2':'B2','B3':'B2','B4':'B1'}
CORE_REVIEW = {1:4,3:19,5:20,9:2}


def apply(rows):
    for row in rows.values():
        tid = row['template_id']; role = row['role']
        if role == 'generator':
            n = int(row['provenance']['core_curated_from'][-3:]) if '-CORE-' in tid else int(tid[-3:])
            source=row['input']['original_instruction'];parts=row['output']['subtasks']
        elif tid.startswith('R2R-REV-'):
            n=int(tid[-3:]);source=row['review_input']['original_instruction'];parts=row['review_input']['candidate']['subtasks']
        elif tid.startswith('R2R-CORE-R'):
            n=CORE_REVIEW.get(int(tid[-2:]));source=row['review_input']['original_instruction'];parts=row['review_input']['candidate']['subtasks']
        else:continue
        if n not in SPECS:continue
        spec=deepcopy(SPECS[n])
        if any(q not in source for q in spec['source']):raise ValueError('Missing decision-boundary source evidence: '+tid)
        if any(i>=len(parts) or q not in parts[i] for i,q in spec['candidate']):raise ValueError('Stale decision-boundary candidate evidence: '+tid)
        rules=['G-P2-'+r for r in spec['rules']] if role=='generator' else sorted({'R-P2-'+REV_RULES[r] for r in spec['rules']})
        row['teaching_notes']['decision_boundary']=dict(
            rule_ids=rules, source_quotes=spec['source'],
            candidate_evidence=[dict(subtask_index=i,quote=q) for i,q in spec['candidate']],
            operation=spec['operation'] if role=='generator' else 'Independently check the source/candidate evidence below. '+spec['operation'],
            counter_boundary=spec['boundary'],
            framing='Generation preference is not a new review rejection criterion; no stage-count or edit-distance optimization.')
