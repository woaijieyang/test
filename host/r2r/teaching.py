"""Complete R2R runtime demonstrations; summary projection is not supported.

All fixed Core and selected Dynamic cards preserve the entire active output.
Selection and authoring metadata stay Host-owned. This module is not used by RxR.
"""
from copy import deepcopy
from host.r2r.selection import teaching_index, _verify


def dynamic_is_detailed(role, selected_ids, position):
    """Every selected R2R dynamic case, including diagnostics, is complete."""
    if role not in ('generator', 'reviewer'):
        raise ValueError('Unsupported R2R teaching role')
    if type(position) is not int or not 0 <= position < len(selected_ids):
        raise ValueError('Invalid dynamic position')
    return True


def card(example, role, detailed):
    index, _ = teaching_index()
    item = index.get(example['template_id'])
    if item is None:
        raise ValueError('Unindexed R2R teaching card')
    _verify(example, item)
    if role != example['role'] or type(detailed) is not bool:
        raise ValueError('Teaching role/detail mismatch')
    if not detailed:
        raise ValueError('R2R summary projection is disabled; complete teaching is required')
    source = (example.get('input') or example['review_input'])['original_instruction']
    result = dict(template_id=example['template_id'], source=source,
                  lesson=item['lesson'], reusable_rule=item.get('reusable_rule'),
                  counter_boundary=item['counter_boundary'], skills=item['skills'],
                  format=('complete_initial_output_demonstration' if role == 'generator'
                          else 'complete_review_output_demonstration'))
    boundary = example.get('teaching_notes', {}).get('decision_boundary')
    if boundary:
        result['decision_boundary'] = deepcopy(boundary)
    if not result['reusable_rule']:
        raise ValueError('Missing reusable teaching operation')
    if role == 'generator':
        result['decision'] = deepcopy(example['decision'])
        result['expected_output'] = deepcopy(example['output'])
    else:
        result['candidate'] = deepcopy(example['review_input']['candidate'])
        result['expected_output'] = deepcopy(example['expected_review'])
    return result
