"""Verify the real navigation smoke before publishing the remaining frozen inputs."""
from collections import defaultdict
from pathlib import Path
import fcntl
import hashlib
import json
import statistics
import subprocess
import sys
import time

from prepare_original import native, checked, pkg, language_record

work = native.P
root = Path.cwd()
execution = json.loads((pkg / 'config/execution.json').read_bytes())
scheduler = work.with_name('r2r-specialized-A1-20261106-r0')
smoke = scheduler / 'navigation-batch1600/runs/D-r2r-1600'
queue = scheduler / 'navigation-batch538/prepared-runs.json'
rows = [json.loads(line) for line in (work / 'manifest.jsonl').read_bytes().splitlines()]
sources = {row['record_id']: row for row in rows}
assert len(sources) == 615


def load(path):
    return json.loads(path.read_bytes())


def publish(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.writing')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(run):
    proof = run / 'train-flow-audit.json'
    if not proof.exists():
        script = pkg.parent / 'LLM-decompose-v1-r2r-specialized/scripts/audit_navigation.py'
        with (run / 'v3-independent-audit.log').open('ab') as log:
            subprocess.run([sys.executable, '-B', str(script), str(run)], stdout=log, stderr=log, check=True)
    assert load(proof)['status'] == 'PASS'
    return proof


def smoke_gate():
    if not (smoke / 'supervisor-result.json').exists():
        return False
    assert load(smoke / 'worker-result.json')['status'] == 'EXECUTION_COMPLETE_PENDING_INDEPENDENT_AUDIT'
    proof = audit(smoke)
    text, result = checked(rows[0])
    binding = load(smoke / 'mapping.json')['records'][0]
    actual = load(root / binding['language_file'])
    assert actual['assigned_task_text'] == text
    assert actual['assigned_task_sha256'] == result['instruction_sha256']
    publish(work / 'VALIDATION_GATE.json', {
        'status': 'PASS', 'task_key': rows[0]['record_id'],
        'language_record_sha256': digest(work / 'records' / rows[0]['safe_id'] / 'result.json'),
        'navigation_audit_sha256': digest(proof),
        'instruction_sha256': result['instruction_sha256'],
        'basis': 'Real independent generator/reviewer, frozen rendering, native navigation and decoded-token audit',
    })
    return True


lock = (work / 'pipeline.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
assert load(work.with_name('r2r-specialized-v3-fullA-20261109-r2') / 'VALIDATION_GATE.json')['status'] == 'PASS'

groups = [[rows[0]]]
scenes = defaultdict(list)
for row in rows[1:]:
    scenes[row['record_id'].split('|')[3]].append(row)
for scene in scenes.values():
    groups.extend(scene[i:i + execution['batch_scene_size']] for i in range(0, len(scene), execution['batch_scene_size']))

history = load(work / 'prior.json')
assert set(history) == set(sources)
completed = {}
groups_with_numbers = list(enumerate(groups, 13000))
while len(completed) < len(sources):
    prepared = []
    blocked = []
    for number, group in groups_with_numbers:
        if not all((work / 'records' / row['safe_id'] / 'result.json').exists() for row in group):
            continue
        if number < 3000:
            group = [row for row in group if load(work / 'records' / row['safe_id'] / 'result.json')['result']['state'] != 'fallback_technical_failure']
            if not group:
                continue
        native.prepare(group, number)
        run = scheduler / f'navigation-batch{number}/runs/D-r2r-{number}'
        prepared.extend(load(run.parent.parent / 'prepared-runs.json')['runs'])
        proof = run / 'train-flow-audit.json'
        if not proof.exists():
            proof = run / 'retained-audit.json'
        if not proof.exists() or load(proof)['status'] != 'PASS':
            continue
        metrics = {entry['task_key']: entry['metrics'] for entry in load(run / 'trace/independent_metrics.json')['results']}
        for terminal in map(json.loads, (run / 'trace/results.jsonl').read_bytes().splitlines()):
            key = terminal['task_key']
            if key in completed:
                continue
            source = sources[key]
            language = language_record(source)
            calls = [e for e in map(json.loads, (run / 'trace' / terminal['trace_path']).read_bytes().splitlines()) if e['kind'] == 'model_call']
            assert calls and all('Your assigned task is: "' + language['result']['instruction'] + '". ' in call['prompt'] for call in calls)
            completed[key] = {
                'task_key': key, 'part': source['part'], 'episode_id': source['episode_id'],
                'original': source['original_instruction'], 'language': language,
                'navigation': {**history[key]['navigation'], 'v3': {
                    'metrics': metrics[key], 'steps': terminal['primitive_steps'],
                    'calls': terminal['model_calls'], 'termination': terminal['termination_reason'],
                    'trace': str(run / 'trace' / terminal['trace_path']),
                    'input_tokens': sum(len(c['input_ids'][0]) for c in calls),
                    'output_tokens': sum(len(c['output_ids'][0]) for c in calls),
                }},
            }
    assert len({r['path'] for r in prepared}) == len(prepared)
    existing = load(queue)['runs'] if queue.exists() else []
    merged = {r['path']: r for r in existing + prepared}
    publish(queue, {'runs': list(merged.values())})
    publish(work / 'PIPELINE_STATUS.json', {'prepared_episodes': sum(r['count'] for r in prepared), 'audited_episodes': len(completed), 'technical_failures': blocked})
    report = ['# R2R Remaining A complete workflow modified (not uploaded original)', f'Audited {len(completed)}/615', '', '|Part|Method|N|SR %|SPL %|nDTW %|NE m|', '|---|---|---:|---:|---:|---:|---:|']
    for part in ('All', 'Remaining'):
        selected = [r for r in completed.values() if part == 'All' or r['part'] == part]
        if not selected:
            continue
        for variant in ('baseline', 'D', 'E', 'v3'):
            values = [statistics.mean(r['navigation'][variant]['metrics'][metric] for r in selected) * (1 if metric == 'ne' else 100) for metric in ('sr', 'spl', 'ndtw', 'ne')]
            report.append('|' + '|'.join([part, variant, str(len(selected)), *[f'{value:.3f}' for value in values]]) + '|')
    temporary = work / 'PAIRED_REPORT.tmp'
    temporary.write_text('\n'.join(report) + '\n', encoding='utf8')
    temporary.replace(work / 'PAIRED_REPORT.md')
    publish(work / 'PAIRED_EPISODES.json', list(completed.values()))
    time.sleep(execution['poll_seconds'])
