"""RxR-only teaching projection and explicit production-bundle validation.

No authoring, downloads, ranking changes or semantic decisions happen here.
Summaries retain actual source, candidate, conditions and repair evidence.
"""
from __future__ import annotations

from copy import deepcopy

SCOPES = {'RxR', 'RxR_prompt_teaching_example'}


def dynamic_is_detailed(role, position):
    if role not in ('generator', 'reviewer') or type(position) is not int or position < 0:
        raise ValueError('Invalid RxR role or dynamic position')
    # Reviewer pairs precede diagnostics, so the same first two cases are detailed.
    return position < 2


def _stage_summary(audit, stages):
    """Remove duplicated process prose only; never truncate a relation or quote."""
    result = []
    for row in audit:
        item = deepcopy(row)
        index = item['subtask_index']
        if not 0 <= index < len(stages):
            raise ValueError('RxR teaching stage index is out of range')
        process = item['process']
        if process.get('text') == stages[index]:
            # The full executable stage and all process quotes remain visible.
            process.pop('text')
        result.append(item)
    return result


def card(example, role, detailed, *, review_output):
    if example.get('dataset_scope') not in SCOPES or example.get('language') != 'en-US':
        raise ValueError('RxR projection received foreign teaching')
    if example.get('role') != role or type(detailed) is not bool:
        raise ValueError('Invalid RxR teaching role or detail policy')
    notes = example['teaching_notes']
    if role == 'generator':
        output = example['output']
        teaching = dict(source=example['input']['original_instruction'],
                        decision=example['decision'], stages=output['subtasks'],
                        handoffs=output['handoffs'], issues=output['issues'])
        if detailed:
            teaching['stage_evidence'] = output['stage_audit']
        else:
            teaching['stage_summary'] = _stage_summary(output['stage_audit'], output['subtasks'])
        lesson = notes.get('case_rationale') or notes.get('reusable_rule') or notes.get('why_this_case_matters')
    elif role == 'reviewer':
        audit = review_output(example)
        stages = example['review_input']['candidate']['subtasks']
        teaching = dict(review_case=example['review_input'], verdict=audit['verdict'],
                        dimensions=audit['dimensions'], findings=audit['findings'])
        if detailed:
            teaching.update(coverage_evidence=audit['source_coverage'],
                            stage_checks=audit.get('stage_checks', []),
                            layer_checks=audit.get('layer_checks', []))
        else:
            # All requirements/evidence are retained. Only repeated layer conclusions
            # and duplicate process narration are summarized, not the actual defect.
            teaching.update(coverage_summary=audit['source_coverage'],
                            stage_summary=_stage_summary(audit.get('stage_checks', []), stages),
                            layer_summary=[{k: row[k] for k in ('layer', 'status', 'finding_indices')}
                                           for row in audit.get('layer_checks', [])])
        teaching['handoffs'] = audit['handoffs']
        teaching['prior_finding_reviews'] = audit.get('prior_finding_reviews', [])
        lesson = notes.get('case_specific_focus') or notes.get('review_principle') or notes.get('reuse_rule')
    else:
        raise ValueError('Invalid RxR teaching role')
    if not isinstance(lesson, str) or not lesson.strip():
        raise ValueError('RxR teaching requires an actual transferable lesson')
    return deepcopy(dict(template_id=example['template_id'], teaching=teaching,
                         applicable_lesson=lesson, avoid=notes.get('anti_pattern')))


def validate_selection(role, ids, rows, mode='adaptive'):
    """Validate explicit/replayed IDs without reranking them or silently filling gaps."""
    if role not in ('generator', 'reviewer') or mode not in ('adaptive', 'all'):
        raise ValueError('Invalid RxR selection mode or role')
    bank = {row['template_id']: row for row in rows}
    if len(bank) != len(rows) or len(ids) != len(set(ids)) or any(tid not in bank for tid in ids):
        raise ValueError('Invalid RxR dynamic identities')
    if mode == 'all':
        if ids != [row['template_id'] for row in rows]:
            raise ValueError('RxR all mode must explicitly export the complete ordered library')
        return
    selected = [bank[tid] for tid in ids]
    if role == 'generator':
        if not 2 <= len(selected) <= 4:
            raise ValueError('RxR production requires two to four Generator dynamics')
    else:
        pairs = [row for row in selected if row.get('pair_id')]
        diagnostics = [row for row in selected if not row.get('pair_id')]
        if not 2 <= len(pairs) <= 4 or len(diagnostics) > 2 or selected != pairs + diagnostics:
            raise ValueError('RxR production requires ordered pairs followed by up to two diagnostics')
        if len({row['pair_id'] for row in pairs}) != len(pairs):
            raise ValueError('Duplicate RxR Generator pair identity')
    def source(row):
        return (row.get('input') or row['review_input'])['original_instruction']
    identities = [' '.join(source(row).casefold().split()) for row in selected]
    if len(identities) != len(set(identities)):
        raise ValueError('Duplicate RxR dynamic source in production bundle')


def validate_pair_bundle(selections, mode='adaptive'):
    from host.template_selector import library
    if mode == 'all':
        return  # Explicit offline full-library export, not a production pairing claim.
    rows = library('reviewer', 'rxr-en-us')
    bank = {row['template_id']: row for row in rows}
    pairs = [bank[tid]['pair_id'] for tid in selections['reviewer'] if bank[tid].get('pair_id')]
    if pairs != selections['generator']:
        raise ValueError('RxR Reviewer pairs must match the frozen Generator order exactly')
