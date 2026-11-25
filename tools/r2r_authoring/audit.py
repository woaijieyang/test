"""Deterministic selection/projection audit, never a navigation evaluation.

The default inputs are unique authored teaching sources (development self-check).
Provide --records JSON/JSONL with original_instruction and optional task_id,
source metadata and split to audit another frozen source-only collection.
Scores and trajectories are deliberately ignored. This tool makes no LLM calls.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from host.compile import compile_prompt, teaching_card
from host.template_selector import library
from host.r2r.relations import route_family
from host.r2r.selection import core_rows, normalized, select_bundle, teaching_index
from host.r2r.teaching import card, dynamic_is_detailed
from shared.identity import canonical, text_hash

ROOT = Path(__file__).resolve().parents[2]


def source_records(path: Path | None) -> tuple[list[dict], dict]:
    if path is not None:
        raw = path.read_bytes()
        if path.suffix.lower() == '.jsonl':
            records = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
        else:
            records = json.loads(raw)
        if not isinstance(records, list):
            raise ValueError('Expected a JSON array or JSONL records')
        origin = dict(kind='provided_source_records', input_sha256=hashlib.sha256(raw).hexdigest(),
                      original_1068_verified=False)
    else:
        index, _ = teaching_index()
        records = []
        seen = set()
        for item in index.values():
            if item['role'] != 'generator' or '-CORE-' in item['template_id']:
                continue
            row = json.loads((ROOT/item['path']).read_bytes())
            source = row['input']['original_instruction']
            if normalized(source) not in seen:
                records.append(dict(task_id=item['template_id'], original_instruction=source,
                                    source=row['source'], split=row['source'].get('split')))
                seen.add(normalized(source))
        origin = dict(kind='teaching_source_self_check', original_1068_verified=False,
                      caveat='These sources developed the teaching assets. Not held-out or navigation data.')
    for i, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get('original_instruction'), str):
            raise ValueError(f'Record {i} must contain an exact original_instruction string')
        if record.get('source') is not None and not isinstance(record['source'], dict):
            raise ValueError(f'Record {i} source metadata must be an object')
    return records, origin


def audit(records: list[dict], origin: dict) -> dict:
    banks = {role: {r['template_id']: r for r in library(role, 'r2r-en')}
             for role in ('generator', 'reviewer')}
    counts, diagnostics, reasons, gaps = Counter(), Counter(), Counter(), Counter()
    cases = []
    for number, record in enumerate(records):
        source = record['original_instruction']
        metadata = record.get('source') or {}
        family = route_family(metadata, record.get('split') or metadata.get('split'))
        bundle = select_bundle(source, source_family=family)
        # Repeat independently to test determinism, not merely stored IDs.
        if bundle != select_bundle(source, source_family=family):
            raise AssertionError('Nondeterministic selection')
        counts[len(bundle['generator'])] += 1
        diagnostics[len(bundle['reviewer'])-len(bundle['generator'])] += 1
        selected = bundle['evidence']['generator']['selected']
        reasons.update(row['selection_reason'] for row in selected)
        gaps.update(bundle['evidence']['generator']['unmatched_query_skills'])
        snapshots = []
        for role, phases in (('generator', ('initial','repair')), ('reviewer', ('review','recheck'))):
            ids = bundle[role]
            projected = [canonical(card(banks[role][tid], role, dynamic_is_detailed(role, ids, pos)))
                         for pos, tid in enumerate(ids)]
            receipts = bundle['evidence'][role]['projection']
            if [text_hash(p) for p in projected] != [r['projection_sha256'] for r in receipts]:
                raise AssertionError('Projection receipts do not match teaching content')
            for phase in phases:
                prompt, schema = compile_prompt(role, phase, profile='r2r-en',
                    original_instruction=source, selected_ids=ids)
                for payload in projected:
                    if prompt.count(payload) != 1:
                        raise AssertionError('Selected projected teaching not injected exactly once')
                for core in core_rows(role):
                    if prompt.count(canonical(teaching_card(core, role, detailed=True))) != 1:
                        raise AssertionError('Fixed Core not injected exactly once')
                if phase in ('repair','recheck'):
                    filename='r2r_repair_examples.json' if role=='generator' else 'r2r_recheck_examples.json'
                    phase_lessons=json.loads((ROOT/role/'dataset_rules'/filename).read_bytes())
                    for lesson in phase_lessons:
                        if lesson['phase']!=phase or prompt.count(canonical(lesson))!=1:
                            raise AssertionError('Phase lesson not injected exactly once in correct phase')
                snapshots.append(dict(role=role, phase=phase, ids=ids,
                    prompt_sha256=text_hash(prompt), schema_sha256=text_hash(canonical(schema)),
                    utf8_bytes=len(prompt.encode('utf-8')), projection=receipts))
        cases.append(dict(task_id=record.get('task_id', number), source_sha256=text_hash(source),
            source_family=family, generator_ids=bundle['generator'], reviewer_ids=bundle['reviewer'],
            fixed_core_overlaps=bundle['core_source_overlaps'],
            fixed_core_family_overlaps=bundle['evidence']['generator']['fixed_core_overlap'],
            generator_decisions=selected,
            diagnostic_decisions=bundle['evidence']['reviewer']['diagnostics']['selected'],
            diagnostic_prior_units=bundle['evidence']['reviewer']['diagnostics']['prior_lesson_units'],
            unmatched_query_skills=bundle['evidence']['generator']['unmatched_query_skills'],
            snapshots=snapshots))
    return dict(origin=origin, query_count=len(records), phase_count=4*len(records),
        deterministic_selection=True, selected_projection_verified=True, fixed_core_verified=True, phase_teaching_verified=True,
        generator_dynamic_counts=dict(sorted(counts.items())),
        reviewer_diagnostic_counts=dict(sorted(diagnostics.items())),
        generator_selection_reasons=dict(sorted(reasons.items())),
        unmatched_query_skills=dict(sorted(gaps.items())),
        core_text_overlap_queries=sum(bool(c['fixed_core_overlaps']) for c in cases),
        core_family_overlap_queries=sum(bool(c['fixed_core_family_overlaps']) for c in cases),
        semantic_model_evaluated=False, navigation_evaluated=False,
        cases=cases)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'provenance/r2r_selection_audit.json')
    args = parser.parse_args()
    records, origin = source_records(args.records)
    report = audit(records, origin)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='cases'}, ensure_ascii=False))

if __name__ == '__main__':
    main()
