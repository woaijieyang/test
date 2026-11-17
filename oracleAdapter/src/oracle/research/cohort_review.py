"""Completed endpoint cohort audit, preserving the full parent identity and scope."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path,PurePosixPath
import zipfile

from oracle.common.artifacts import content_digest,digest,owned_output,write_json,package_sources,freeze_sources
from oracle.common.offline_audit import identity
from oracle.common.task_index import verify_entry
from oracle.research.full_worker import load_task,effective_method,compare_preflight
from oracle.research.full_report import resolve_evidence,failure_explanation
from oracle.verification.execution_evidence import check_trace_stream


def read_prefix(files):
    seq=0;previous='0'*64;records={}
    for path in files:
        for raw in path.read_bytes().splitlines(keepends=True):
            if not raw.endswith(bytes([10])):raise ValueError('Snapshot contains an incomplete frame')
            entry=json.loads(raw);core={k:v for k,v in entry.items() if k!='entry_sha256'}
            if (entry['seq']!=seq+1 or entry['prev']!=previous or content_digest(core)!=entry['entry_sha256']
                    or entry['key'] in records or entry['payload']['task_key']!=entry['key']):
                raise ValueError('Journal snapshot identity/chain mismatch')
            seq+=1;previous=entry['entry_sha256'];records[entry['key']]=entry['payload']
    return records,seq,previous


def selected_entries(entries,counts):
    selected={};actual=Counter()
    for entry in entries:
        record=entry['record']
        if record['dataset'] not in counts:continue
        if record['task_key'] in selected:raise ValueError('Duplicate selected task')
        selected[record['task_key']]=entry;actual[record['dataset']]+=1
    if dict(actual)!=counts:raise ValueError('Selected input coverage differs')
    return selected


def review(case_root,snapshot_path,output,*,scope=None):
    startup=identity();root=Path(case_root).resolve();snapshot=owned_output(root,snapshot_path);output=owned_output(root,output)
    if output.exists():raise FileExistsError(output)
    config_path=Path(__file__).resolve().parents[1]/'configs/tasks/endpoint_cohort_review.json'
    config=json.loads(config_path.read_text()) if scope is None else scope
    if scope is not None and scope.get('mode')!='sealed_completed_prefix':raise ValueError('Unknown explicit review scope')
    meta=json.loads((snapshot/'snapshot.json').read_text())
    source_run=PurePosixPath(meta['source_run_root']);run=root/'outputs/oracleAdapter'/source_run.name
    for relative,sha in meta['files_sha256'].items():
        p=(root/relative).resolve()
        if not p.is_relative_to(run) or digest(p)!=sha:raise ValueError('Exported evidence identity mismatch')
    m=json.loads((run/'manifest.json').read_text());msha=digest(run/'manifest.json')
    if (msha!=config['parent_manifest_sha256'] or msha!=meta['parent_manifest_sha256']
        or m['task_count']!=config['parent_task_count']):raise ValueError('Parent identity changed')
    if digest(run/'index.json')!=m['index_sha256'] or digest(run/'tasks.jsonl')!=m['tasks_file_sha256']:
        raise ValueError('Frozen input changed')
    with zipfile.ZipFile(run/'source.zip') as z:
        if set(z.namelist())!=set(m['sources']):raise ValueError('Frozen source set changed')
        for name,sha in m['sources'].items():
            if hashlib.sha256(z.read(name)).hexdigest()!=sha:raise ValueError('Frozen source differs')
    prefix,seq,previous=read_prefix(sorted(snapshot.glob('segment-*.jsonl.snapshot')))
    if seq!=meta['journal_frames'] or previous!=meta['journal_last_hash']:raise ValueError('Snapshot prefix differs')
    all_entries=json.loads((run/'index.json').read_text())
    if scope is None:
        entries=selected_entries(all_entries,config['datasets'])
    else:
        keys=set(config['selection_keys'])
        if len(keys)!=len(config['selection_keys']) or keys!=set(prefix):raise ValueError('Sealed prefix selection differs from complete journal')
        entries={e['record']['task_key']:e for e in all_entries if e['record']['task_key'] in keys}
        if set(entries)!=keys or dict(Counter(e['record']['dataset'] for e in entries.values()))!=config['datasets']:
            raise ValueError('Sealed prefix input coverage differs')
    rows=json.loads((snapshot/'selected-results.json').read_text())
    if len(rows)!=len(entries) or {r['task_key'] for r in rows}!=set(entries):raise ValueError('Selected result coverage differs')
    groups=defaultdict(Counter);failure_counts=defaultdict(Counter);evidence=[];failures=[];actual=replayed=0;position=angle=0.;physical_alerts=0
    expected_module=source_run.parents[2]/'oracleAdapter/src/oracle'
    for row in rows:
        if prefix.get(row['task_key'])!=row:raise ValueError('Selected row differs from journal')
        task,_=load_task(root,m,entries[row['task_key']],run/'tasks.jsonl')
        verify_entry(entries[row['task_key']],m['task_merkle_root'],m['task_count'])
        p=resolve_evidence(row['receipt'],run,source_run)
        if digest(p)!=row['receipt_sha256']:raise ValueError('Receipt differs from journal')
        receipt=json.loads(p.read_text());method=effective_method(task,m);exe=p.parent.parent/'execute'
        if receipt['task_sha256']!=content_digest(task) or receipt['manifest_sha256']!=msha or receipt['method']!=method:
            raise ValueError('Task/method binding differs')
        for label in ('status','failure','task_key','dataset','cohort','actual_actions','replayed_actions'):
            if receipt[label]!=row[label]:raise ValueError('Final row semantics differ')
        for directory,role in ((p.parent,'audit'),(exe,'execute')):
            start=json.loads((directory/'start.json').read_text())
            if (start['manifest_sha256']!=msha or start['task_sha256']!=content_digest(task)
                or start['method_sha256']!=content_digest(method) or start['role']!=role):raise ValueError('Phase startup binding differs')
            for field,relative in (('teacher','teachers/ordered.py'),('auditor','verification/route_replay.py'),('worker','research/full_worker.py')):
                if (start[field]['sha256']!=m['sources'][relative]
                    or PurePosixPath(start[field]['actual_path'])!=expected_module/relative):raise ValueError('Actual import differs')
        if digest(exe/'start.json')!=receipt['execution_start_sha256']:raise ValueError('Execution startup receipt changed')
        if digest(p.with_name('preflight.json'))!=receipt['preflight_sha256']:raise ValueError('Independent preflight changed')
        pre=json.loads(p.with_name('preflight.json').read_text());compare_preflight(json.loads((exe/'preflight.json').read_text()),pre)
        result=audit=None
        if receipt['result_sha256'] is not None:
            rp=exe/'motion/result.json';ap=p.with_name('motion-audit.json')
            if digest(rp)!=receipt['result_sha256'] or digest(ap)!=receipt['motion_audit_sha256']:raise ValueError('Motion evidence changed')
            result=json.loads(rp.read_text());audit=json.loads(ap.read_text());stream=check_trace_stream(result,rp.with_name('executed.jsonl'))
            if (audit['source_result_sha256']!=digest(rp) or audit['task_sha256']!=content_digest(task) or audit['issues']
                or result['task_sha256']!=content_digest(task) or result['method']!=method or result['protocol']!=m['protocol']
                or result['initialization_count']!=1 or audit['replay_explicit_initialization_count']!=1):raise ValueError('Motion/replay identity differs')
            if len(result['actions'])!=receipt['actual_actions'] or audit['executed_actions_replayed']!=receipt['replayed_actions']:
                raise ValueError('Action counts differ')
            expected=('PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES' if audit['full_route_accepted'] and pre['endpoint_source_gate'] else
                      'ROUTE_WITNESS_ONLY_ENDPOINT_SOURCE_GATE_FAIL' if audit['full_route_accepted'] else 'FAILURE_PRESERVED')
            if expected!=receipt['status']:raise ValueError('Acceptance differs')
            position=max(position,audit['max_position_error_m']);angle=max(angle,audit['max_orientation_error_rad'])
            physical_alerts+=len(audit['physical_alerts'])
        elif pre['native_ready'] or receipt['status']!='STATIC_FAILURE_PRESERVED':raise ValueError('Missing execution evidence')
        actual+=receipt['actual_actions'];replayed+=receipt['replayed_actions'];groups[task['cohort']][receipt['status']]+=1
        if receipt['failure']:
            failure_counts[task['cohort']][receipt['failure']]+=1
            failures.append(dict(task_key=task['task_key'],cohort=task['cohort'],receipt=str(p.relative_to(run)),
                receipt_sha256=digest(p),explanation=failure_explanation(task,receipt,pre,result,audit)))
        evidence.append(dict(task_key=task['task_key'],task_sha256=content_digest(task),receipt_sha256=digest(p)))
    if actual!=replayed:raise ValueError('Replay count differs')
    output.mkdir();_,sources=package_sources();freeze_sources(output,sources)
    write_json(output/'task-evidence.json',evidence);write_json(output/'failures.json',failures)
    summary=dict(status='ENDPOINT_COHORT_RECEIPTS_VERIFIED_PARENT_RUN_NOT_COMPLETE' if scope is None else 'SEALED_PREFIX_RECEIPTS_VERIFIED_PARENT_RUN_INCOMPLETE',startup=startup,datasets=config['datasets'],
        records=len(rows),parent_task_count=m['task_count'],parent_manifest_sha256=msha,
        groups={k:dict(v) for k,v in groups.items()},failure_classes={k:dict(v) for k,v in failure_counts.items()},
        actual_actions=actual,independently_replayed_actions=replayed,max_replay_position_error_m=position,
        max_replay_orientation_error_rad=angle,replay_physical_alerts=physical_alerts,
        all_selected_navigation_gates_passed=not failures,parent_full_acceptance=False,
        snapshot_sha256=digest(snapshot/'snapshot.json'),configuration_sha256=digest(config_path) if scope is None else content_digest(scope),
        output_hashes={p.name:digest(p) for p in output.glob('*.json')},
        limits=['No new native execution or replay; this reconciles the existing per-task separate-process replay evidence.',
                'Original parent37016 input and source identity unchanged; Landmark remains pending, not excluded.',
                'Different information branches separate; no model SR or prior-protocol improvement claim.',
                'Replay engine and geometry assumptions are shared with prior audits; finite failure is not physical impossibility.'])
    write_json(output/'validation.json',summary);return summary
