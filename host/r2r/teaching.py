"""R2R teaching projection with explicit, testable detail selection.

Complete demonstrations use the active initial/review output contract. Compact
lessons keep concrete evidence and never imitate an incompatible old schema.
This module is not used by RxR.
"""
from copy import deepcopy
from host.r2r.selection import teaching_index, _verify


def dynamic_is_detailed(role, selected_ids, position):
    """At least two complete Dynamic cases; include a full diagnostic as well."""
    if role not in ('generator', 'reviewer'):
        raise ValueError('Unsupported R2R teaching role')
    if type(position) is not int or not 0 <= position < len(selected_ids):
        raise ValueError('Invalid dynamic position')
    if position < 2:
        return True
    if role == 'reviewer':
        index, _ = teaching_index()
        diagnostic = [i for i in selected_ids if not index[i].get('pair_id')]
        return bool(diagnostic) and selected_ids[position] == diagnostic[0]
    return False


def card(example, role, detailed):
    index, _ = teaching_index()
    item = index.get(example['template_id'])
    if item is None:
        raise ValueError('Unindexed R2R teaching card')
    _verify(example, item)
    if role != example['role'] or type(detailed) is not bool:
        raise ValueError('Teaching role/detail mismatch')
    source = (example.get('input') or example['review_input'])['original_instruction']
    result = dict(template_id=example['template_id'], source=source,
                  lesson=item['lesson'], reusable_rule=item.get('reusable_rule'),
                  counter_boundary=item['counter_boundary'], skills=item['skills'],
                  format='lesson_summary')
    if not result['reusable_rule']:
        raise ValueError('Missing reusable teaching operation')
    out = example['output'] if role == 'generator' else example['expected_review']
    if role == 'generator':
        result['decision'] = deepcopy(example['decision'])
    else:
        result['candidate'] = deepcopy(example['review_input']['candidate'])
    if detailed:
        result['format'] = ('complete_initial_output_demonstration' if role == 'generator'
                            else 'complete_review_output_demonstration')
        result['expected_output'] = deepcopy(out)
        return result
    if role == 'generator':
        result['stages'] = deepcopy(out['subtasks'])
        result['source_issues'] = deepcopy(out['issues'])
        result['boundary_evidence'] = [dict(after_stage=h['from_subtask_index'],
            completed_event=h['preceding_exit']['candidate_quote'],
            next_action_context=h['next_entry']['candidate_quote']) for h in out['handoffs']]
        result['completion_evidence'] = [dict(stage=s['subtask_index'],
            event=deepcopy(s['ending']['candidate_quotes']), kind=s['ending']['kind'],
            stop_scope=s['ending']['stop_scope']) for s in out['stage_audit']]
        result['stage_semantics'] = [dict(stage=s['subtask_index'],
            entry=deepcopy(s['entry']), target=deepcopy(s['target']), process=deepcopy(s['process']),
            conditions=deepcopy(s['conditions']), source_evidence=deepcopy(s['source_quotes']),
            carryover=deepcopy(s['carryover'])) for s in out['stage_audit']]
    else:
        result['verdict'] = out['verdict']
        result['dimensions'] = deepcopy(out['dimensions'])
        result['evidence_excerpt'] = [dict(source=f['source_quote'],
            candidate=deepcopy(f['candidate_evidence']), check=f['c_check'],
            affected_requirements=deepcopy(f['source_requirement_ids']),
            problem=f['problem'], consequence=f['execution_consequence'],
            evidence_level=f['evidence_level']) for f in out['findings']]
        result['local_repair'] = [dict(action=f['repair']['instruction'],
            preserve=deepcopy(f['repair']['protected_requirements'])) for f in out['findings']]
        result['stage_semantics'] = [dict(stage=s['subtask_index'], status=s['status'],
            entry=deepcopy(s['entry']), target=deepcopy(s['target']), process=deepcopy(s['process']), ending=deepcopy(s['ending']),
            conditions=deepcopy(s['conditions'])) for s in out['stage_checks']]
        result['continuity_evidence'] = deepcopy(out['handoffs'])
        if not out['findings']:
            result['evidence_excerpt'] = [dict(source=c['source_quote'],
                candidate=deepcopy(c['candidate_evidence']), status=c['status'])
                for c in out['source_coverage']]
    return result
