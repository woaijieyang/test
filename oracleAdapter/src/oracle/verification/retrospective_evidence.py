"""Read-only consistency checks; never upgrade missing historical attestation."""
import json
from pathlib import Path
from oracle.adapters.habitat.native import NativeState
from oracle.common.artifacts import content_digest,digest,write_json
from oracle.verification.execution_evidence import initial_contract_errors,check_trace_stream


def audit(case_root,config,output):
    root=Path(case_root).resolve();output=Path(output).resolve()
    if not output.is_relative_to(root/'outputs/oracleAdapter') or output.exists():raise ValueError('Fresh owned output required')
    rows=[];run_receipts=[]
    for name in config['runs']:
        run=root/name;m=json.loads((run/'manifest.json').read_text());v=json.loads((run/'validation.json').read_text())
        if not v['complete'] or v['manifest_sha256']!=digest(run/'manifest.json'):raise ValueError('Run incomplete or changed')
        tasks={t['task_key']:t for t in m['tasks']};seen=set()
        for row in v['results']:
            pair=(row['task_key'],row['method'])
            if pair in seen:raise ValueError('Duplicate task/method')
            seen.add(pair);item=tasks[row['task_key']]
            if digest(item['path'])!=item['sha256'] or digest(row['result_path'])!=row['result_sha256']:raise ValueError('Task/result changed')
            task=json.loads(Path(item['path']).read_text());record=json.loads(Path(row['result_path']).read_text())
            if record['task_sha256']!=content_digest(task):raise ValueError('Input binding changed')
            stream=check_trace_stream(record,Path(row['result_path']).with_name('executed.jsonl'),require_hash=False)
            errors=initial_contract_errors(NativeState(task['targets'][0],task['start_rotation']),
                        NativeState(record['positions'][0],record['rotations'][0]),m['protocol'])
            rows.append({'run':str(run),'task_key':row['task_key'],'method':row['method'],
                         'result_sha256':row['result_sha256'],'initial_errors':errors,**stream})
        if len(seen)!=m['expected_executions']:raise ValueError('Incomplete method coverage')
        run_receipts.append({'run':str(run),'manifest_sha256':digest(run/'manifest.json'),'validation_sha256':digest(run/'validation.json')})
    if len(rows)!=config['expected_records']:raise ValueError('Retrospective scope mismatch')
    output.mkdir(parents=True,exist_ok=False);write_json(output/'per-execution-binding.json',rows)
    summary={'status':'CURRENT_STREAM_AND_INPUT_CONSISTENT_HISTORICAL_HASH_LIMIT_RETAINED' if not any(r['initial_errors'] for r in rows) else 'INPUT_STATE_DISAGREEMENT',
        'records':len(rows),'initial_pose_errors':sum(bool(r['initial_errors']) for r in rows),
        'raw_actions_checked':sum(r['actions'] for r in rows),
        'producer_trace_hash_present':sum(r['producer_hash_present'] for r in rows),
        'native_actions_executed_now':0,'sources':run_receipts,'ledger_sha256':digest(output/'per-execution-binding.json'),
        'limits':'Historical producers did not necessarily record raw trace hashes or measured restore counters. This verifies current recorded stream/input consistency, not retroactive original-time attestation, and does not rewrite prior results.'}
    write_json(output/'validation.json',summary);return summary
