"""Final dataset coverage and source/worker/raw-evidence reconciliation."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import zipfile

from oracle.common.artifacts import content_digest,digest,owned_output,write_json,package_sources,freeze_sources
from oracle.common.task_index import verify_entry
from oracle.research.full_worker import load_task,effective_method
from oracle.verification.execution_evidence import check_trace_stream


def review(case_root,run_path,output):
    root=Path(case_root).resolve();run=owned_output(root,run_path);output=owned_output(root,output)
    manifest=json.loads((run/'manifest.json').read_text());closure=json.loads((run/'validation.json').read_text())
    msha=digest(run/'manifest.json')
    for name,key in [('tasks.jsonl','tasks_file_sha256'),('index.json','index_sha256')]:
        if digest(run/name)!=manifest[key]:raise ValueError('Frozen input identity changed')
    if closure['manifest_sha256']!=msha or closure['results_index_sha256']!=digest(run/'results-index.json'):raise ValueError('Closure binding mismatch')
    with zipfile.ZipFile(run/'source.zip') as source:
        if set(source.namelist())!=set(manifest['sources']):raise ValueError('Source set changed')
        for name,sha in manifest['sources'].items():
            if hashlib.sha256(source.read(name)).hexdigest()!=sha:raise ValueError('Archived source corrupted')
    entries=json.loads((run/'index.json').read_text());index={e['record']['task_key']:e for e in entries}
    rows=json.loads((run/'results-index.json').read_text())
    if len(rows)!=manifest['task_count'] or len({r['task_key'] for r in rows})!=len(rows) or {r['task_key'] for r in rows}!=set(index):
        raise ValueError('Incomplete/duplicate/unexpected task coverage')
    counts=Counter();groups=defaultdict(Counter);failures=defaultdict(Counter);actual=replayed=0;missing_worker_stamps=0
    evidence=[]
    for row in rows:
        task,entry=load_task(root,manifest,index[row['task_key']],run/'tasks.jsonl')
        path=Path(row['receipt']).resolve()
        if not path.is_relative_to(run) or digest(path)!=row['receipt_sha256']:raise ValueError('Final receipt changed or escaped')
        receipt=json.loads(path.read_text());start=json.loads(path.with_name('start.json').read_text())
        method=effective_method(task,manifest)
        if receipt['task_sha256']!=content_digest(task) or receipt['manifest_sha256']!=msha or receipt['method']!=method:
            raise ValueError('Actual task/method identity mismatch')
        for key in ('status','failure','task_key','dataset','cohort','actual_actions','replayed_actions'):
            if receipt[key]!=row[key]:raise ValueError('Index differs from actual receipt: '+key)
        if start['manifest_sha256']!=msha or start['task_sha256']!=content_digest(task):raise ValueError('Worker startup mismatch')
        for field,relative in [('teacher','teachers/ordered.py'),('auditor','verification/route_replay.py')]:
            if start[field]['sha256']!=manifest['sources'][relative]:raise ValueError('Actual import hash mismatch')
        if 'worker' in start:
            if start['worker']['sha256']!=manifest['sources']['research/full_worker.py']:raise ValueError('Actual phase worker mismatch')
        else:
            missing_worker_stamps+=1
            if 'worker' in manifest['config']:raise ValueError('Required actual phase binding absent')
        static=path.with_name('preflight.json')
        if digest(static)!=receipt['preflight_sha256']:raise ValueError('Static audit changed')
        pre=json.loads(static.read_text());execution=path.parent.parent/'execute'
        if digest(execution/'start.json')!=receipt['execution_start_sha256']:raise ValueError('Execution launch changed')
        if receipt['result_sha256'] is not None:
            rp=execution/'motion/result.json';ap=path.with_name('motion-audit.json')
            if digest(rp)!=receipt['result_sha256'] or digest(ap)!=receipt['motion_audit_sha256']:raise ValueError('Motion evidence changed')
            result=json.loads(rp.read_text());audit=json.loads(ap.read_text())
            check_trace_stream(result,rp.with_name('executed.jsonl'))
            if (audit['source_result_sha256']!=digest(rp) or audit['task_sha256']!=content_digest(task)
                or audit['issues'] or result['initialization_count']!=1):raise ValueError('Motion/replay evidence invalid')
            expected='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES' if audit['full_route_accepted'] and pre['endpoint_source_gate'] else 'ROUTE_WITNESS_ONLY_ENDPOINT_SOURCE_GATE_FAIL' if audit['full_route_accepted'] else 'FAILURE_PRESERVED'
            if receipt['status']!=expected:raise ValueError('Combined motion/endpoint verdict differs')
        elif pre['native_ready'] or receipt['status']!='STATIC_FAILURE_PRESERVED':raise ValueError('Unexecuted task falsely accepted')
        counts[task['dataset']]+=1;groups[task['cohort']][receipt['status']]+=1
        if receipt['failure']:failures[task['cohort']][receipt['failure']]+=1
        actual+=receipt['actual_actions'];replayed+=receipt['replayed_actions']
        evidence.append({'task_key':task['task_key'],'receipt_sha256':row['receipt_sha256'],'task_sha256':content_digest(task)})
    if dict(counts)!=manifest['datasets'] or actual!=replayed:raise ValueError('Dataset or replay count mismatch')
    output.mkdir(parents=True,exist_ok=False);_,sources=package_sources();freeze_sources(output,sources)
    write_json(output/'task-evidence.json',evidence)
    summary={'status':'FULL_ACCOUNTING_AND_EVIDENCE_VALID_NOT_ALL_NAVIGATION_PASSED','datasets':dict(counts),'records':len(rows),
        'information_condition_groups':{k:dict(v) for k,v in groups.items()},'failure_classes':{k:dict(v) for k,v in failures.items()},
        'actual_actions':actual,'independently_replayed_actions':replayed,
        'all_navigation_gates_passed':all(r['status']=='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES' for r in rows),
        'legacy_phase_binding_not_captured':missing_worker_stamps,'manifest_sha256':msha,
        'task_evidence_sha256':digest(output/'task-evidence.json'),'scope':manifest['scope'],
        'limits':'No model score or publication approval. Shared native engine and geometric formulation remain limitations. Finite failures are not physical unreachability proofs.'}
    write_json(output/'validation.json',summary);return summary
