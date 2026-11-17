"""Separate demonstration reuse, stricter-gate failures and algorithm claims."""
from collections import Counter
import json
from pathlib import Path
from oracle.common.artifacts import content_digest, digest, owned_output, write_json, package_sources, freeze_sources


def classify_row(key, historical, record, audit):
    return {"task_key": key, "historical_official_status": historical,
            "current_strict_status": "PASS" if audit["full_route_accepted"] else "FAILURE_PRESERVED",
            "failure": record["failure"], "detail": record["detail"],
            "phase": "complete" if audit["full_route_accepted"] else "initial_state" if not record["actions"] else "executed_transition",
            "executed_actions": len(record["actions"]), "first_independent_alert": next(iter(audit["physical_alerts"]), None),
            "algorithm_gain_claim": False, "physical_unreachability": "NOT_PROVEN",
            "explanation": "Current source/native gate is stricter than historical demonstration audit; not a search algorithm comparison."}


def classify(case_root, run_path, output):
    root=Path(case_root).resolve();run=owned_output(root,run_path);output=owned_output(root,output)
    manifest=json.loads((run/'manifest.json').read_text());validation=json.loads((run/'validation.json').read_text())
    if not validation['complete'] or validation['manifest_sha256']!=digest(run/'manifest.json'):
        raise ValueError('Incomplete or changed source run')
    if manifest['config']['teacher']!='oracle.teachers.official:execute':raise ValueError('Not an official demonstration run')
    tasks={t['task_key']:t for t in manifest['tasks']}; rows=[]
    source_checks=[]
    for row in validation['results']:
        if row['task_key'] not in tasks:raise ValueError('Unexpected task')
        item=tasks[row['task_key']];path=Path(item['path'])
        if digest(path)!=item['sha256']:raise ValueError('Task changed')
        task=json.loads(path.read_text());rp=Path(row['result_path']);ap=Path(row['audit_path'])
        if not rp.resolve().is_relative_to(run) or not ap.resolve().is_relative_to(run):raise ValueError('Evidence path escape')
        if digest(rp)!=row['result_sha256'] or digest(ap)!=row['audit_sha256']:raise ValueError('Evidence changed')
        record=json.loads(rp.read_text());audit=json.loads(ap.read_text())
        if (record['task_sha256']!=content_digest(task) or audit['task_sha256']!=record['task_sha256']
            or audit['source_result_sha256']!=row['result_sha256'] or row['status']!=audit['status']):raise ValueError('Evidence binding mismatch')
        classified=classify_row(row['task_key'],task['historical_replay_status'],record,audit)
        classified.update(result_path=str(rp),result_sha256=row['result_sha256'],audit_path=str(ap),audit_sha256=row['audit_sha256'],
                          source_initial_to_task_start_distance_m=record['source_initial_to_task_start_distance_m'])
        rows.append(classified)
        source_checks.append({'task_key':row['task_key'],'position_replay_error_m':audit['max_position_error_m'],
                              'orientation_replay_error_rad':audit['max_orientation_error_rad'],
                              'actual_actions':audit['executed_actions_replayed']})
    if len(rows)!=len(tasks) or len({r['task_key'] for r in rows})!=len(tasks):raise ValueError('Duplicate/missing executed task')
    for row in manifest['nonexecuted_source_records']:
        if row['task_key'] in tasks:raise ValueError('Source failure overlaps execution')
        rows.append({'task_key':row['task_key'],'historical_official_status':'NO_OFFICIAL_GT',
            'current_strict_status':'NOT_EXECUTED_SOURCE_UNAVAILABLE','failure':'identity_or_adaptation_missing',
            'phase':'source_binding','algorithm_gain_claim':False,'physical_unreachability':'NOT_PROVEN'})
    if len(rows)!=manifest['source_scope_denominator'] or len({r['task_key'] for r in rows})!=len(rows):raise ValueError('Full source denominator mismatch')
    transition=Counter((r['historical_official_status'],r['current_strict_status']) for r in rows)
    summary={'status':'ALL_SOURCE_RECORDS_CLASSIFIED_NOT_PHYSICAL_UNREACHABILITY_PROOF','source_records':len(rows),
        'executed_records':len(tasks),'counts':dict(Counter(r['current_strict_status'] for r in rows)),
        'failure_counts':dict(Counter(r['failure'] for r in rows if r['failure']!='none')),
        'phase_counts':dict(Counter(r['phase'] for r in rows)),
        'historical_to_current':[{'historical':a,'current':b,'count':n} for (a,b),n in sorted(transition.items())],
        'max_position_replay_error_m':max(r['position_replay_error_m'] for r in source_checks),
        'max_orientation_replay_error_rad':max(r['orientation_replay_error_rad'] for r in source_checks),
        'actual_actions':sum(r['actual_actions'] for r in source_checks),
        'source_validation_sha256':digest(run/'validation.json'),'manifest_sha256':digest(run/'manifest.json'),
        'limitations':['Same native-exported geometry and physical formulation still shared between floating and rational checks.',
                       'A positive contact concerns this initial state or action path, not all possible routes.',
                       'Historical initial orientation/profile are preserved; not a paired optimization of the different-start greedy Oracle.']}
    output.mkdir(parents=True,exist_ok=False);_,sources=package_sources();freeze_sources(output,sources)
    write_json(output/'all192-classification.json',rows);write_json(output/'replay-checks.json',source_checks)
    summary['ledger_sha256']=digest(output/'all192-classification.json');summary['classifier_sha256']=digest(__file__)
    write_json(output/'validation.json',summary)
    return summary
