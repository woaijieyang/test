"""Materialize source-reviewed RxR teaching corrections from immutable Git data.

Offline authoring only. Source identities, retrieval tags and pool size remain
frozen. Unexpected local edits are never overwritten. Reports contain field-level
changes, not claims of measured navigation benefit or automatic entailment proof.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = 'da277a0f9a6ee7d8eebb78dafa852e469cd1a50e'
FOLDERS = ('generator/templates/RxR/core', 'generator/templates/RxR/val_seen',
           'reviewer/templates/RxR/core', 'reviewer/templates/RxR/paired',
           'reviewer/templates/RxR/diagnostics')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def diff(a, b, path=''):
    if type(a) is not type(b):
        return [{'path': path, 'before': a, 'after': b}]
    if isinstance(a, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            p = path + '/' + str(k).replace('~', '~0').replace('/', '~1')
            if k not in a:
                out.append({'path': p, 'added': b[k]})
            elif k not in b:
                out.append({'path': p, 'removed': a[k]})
            else:
                out.extend(diff(a[k], b[k], p))
        return out
    if isinstance(a, list):
        out = []
        for i in range(max(len(a), len(b))):
            p = path + '/' + str(i)
            if i >= len(a):
                out.append({'path': p, 'added': b[i]})
            elif i >= len(b):
                out.append({'path': p, 'removed': a[i]})
            else:
                out.extend(diff(a[i], b[i], p))
        return out
    return [] if a == b else [{'path': path, 'before': a, 'after': b}]


def expected():
    from tools.rxr_positive_repairs import repair as positive
    from tools.rxr_diagnostic_repairs import repair as diagnostics
    from tools.rxr_review_contract import finalize
    from tools.rxr_teaching_focus import refine_positive, refine_core
    from tools.rxr_teaching_alignment import align_positive, align_diagnostics
    from host.template_selector import validate_template
    from host.compile import runtime_review_output, teaching_card
    from host import protocol
    files = git('ls-tree', '-r', '--name-only', BASE, '--', *FOLDERS).decode().splitlines()
    original, paths, raw = {}, {}, {}
    for path in files:
        if not path.endswith('.json'):
            continue
        data = git('show', BASE + ':' + path)
        row = json.loads(data)
        tid = row['template_id']
        if tid in original:
            raise ValueError(f'Duplicate source identity {tid}')
        original[tid], paths[tid], raw[tid] = row, path, data
    if len(original) != 119:
        raise ValueError(f'Unexpected frozen teaching count: {len(original)}')
    rows = copy.deepcopy(original)
    positive(rows)
    # Refine the reviewed parent before dependent diagnostics are materialized.
    # This prevents a grouping contrast from retaining an obsolete parent route.
    refine_positive(rows)
    align_positive(rows)
    contrasts = diagnostics(rows)
    align_diagnostics(rows)
    finalize(rows)
    refine_core(rows)
    ledger, outputs = [], {}
    for tid in sorted(rows):
        row, old, path = rows[tid], original[tid], paths[tid]
        role = row['role']
        src = row['input']['original_instruction'] if role == 'generator' else row['review_input']['original_instruction']
        oldsrc = old['input']['original_instruction'] if role == 'generator' else old['review_input']['original_instruction']
        for k in ('template_id', 'role', 'dataset_scope', 'language', 'source', 'retrieval_tags', 'pair_id'):
            if row.get(k) != old.get(k):
                raise ValueError(f'Protected identity/retrieval field changed: {tid}/{k}')
        if src != oldsrc:
            raise ValueError(f'Source text changed: {tid}')
        try:
            validate_template(role, row, source_path=path)
            if role == 'generator':
                protocol.generator(src, row['output'])
            else:
                protocol.reviewer(src, row['review_input']['candidate'], runtime_review_output(row))
            teaching_card(row, role, True)
            teaching_card(row, role, False)
        except Exception as exc:
            raise ValueError(f'Authored teaching contract failed for {tid}: {exc}') from exc
        changes = diff(old, row)
        data = encode(row) if changes else raw[tid]
        outputs[path] = (raw[tid], data)
        ledger.append(dict(template_id=tid, path=path, source_sha256=digest(src.encode()),
            before_sha256=digest(raw[tid]), after_sha256=digest(data),
            candidate_changed=(old['output']['subtasks'] != row['output']['subtasks'] if role == 'generator'
                else old['review_input']['candidate'] != row['review_input']['candidate']),
            status='authored_correction' if changes else 'unchanged', fields=changes))
    for row in rows.values():
        if row['role'] == 'reviewer' and row.get('pair_id') in rows:
            gen = rows[row['pair_id']]
            if (row['review_input']['original_instruction'] != gen['input']['original_instruction']
                    or row['review_input']['candidate']['subtasks'] != gen['output']['subtasks']):
                raise ValueError(f'Pair mismatch: {row["template_id"]}')
    report = dict(baseline_commit=BASE, legacy_template_count=len(rows),
        source_and_retrieval_identity_preserved=True, template_count_preserved=True,
        mechanical_runtime_contracts_pass=True, semantic_correctness_certified=False,
        navigation_evaluated=False, core_case_specific_lessons=True,
        core_event_local_coverage_rows=33,
        curation_limits=[
            'Natural-language entailment is not proven by schema, quote or pair checks.',
            'The room-or-door description remains source uncertainty; the final bed-foot state is preserved without prescribing an extra traversal.',
            'Contradictory auxiliary-window wording remains in source-preserving descriptive form; analysis is kept outside executable navigation text.',
            'No retrieval, template-count, runtime-schema, renderer or navigation-budget change is included in this calibration.'
        ], contrasts=contrasts, templates=ledger)
    return outputs, report


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--inspect', action='store_true')
    group.add_argument('--write', action='store_true')
    group.add_argument('--check', action='store_true')
    args = parser.parse_args()
    outputs, report = expected()
    report_path = ROOT / 'provenance/rxr_teaching_changes.json'
    previous = {}
    if report_path.is_file():
        stored = json.loads(report_path.read_bytes())
        if stored.get('baseline_commit') != BASE:
            raise ValueError('Refuse an unrelated authoring baseline')
        previous = {r['path']: r for r in stored['templates']}
    mismatches = []
    # Validate every write before touching any output.
    for name, (original, desired) in outputs.items():
        current = (ROOT / name).read_bytes()
        if current != desired:
            mismatches.append(name)
            old = previous.get(name, {})
            known_prior = (old.get('before_sha256') == digest(original)
                           and old.get('after_sha256') == digest(current))
            if args.write and current != original and not known_prior:
                raise ValueError('Refuse to overwrite independently changed teaching: ' + name)
    report_data = encode(report)
    if args.write:
        for name in mismatches:
            (ROOT / name).write_bytes(outputs[name][1])
        report_path.write_bytes(report_data)
    if args.check and (mismatches or not report_path.is_file() or report_path.read_bytes() != report_data):
        raise ValueError('Reviewed teaching differs from authored specification: ' + ', '.join(mismatches))
    print(json.dumps(dict(legacy_templates=len(report['templates']),
        changed_templates=sum(bool(t['fields']) for t in report['templates']),
        candidate_changes=[t['template_id'] for t in report['templates'] if t['candidate_changed']],
        field_changes=sum(len(t['fields']) for t in report['templates']),
        mechanical_runtime_contracts_pass=True, semantic_correctness_certified=False,
        navigation_evaluated=False), ensure_ascii=False))


if __name__ == '__main__':
    main()
