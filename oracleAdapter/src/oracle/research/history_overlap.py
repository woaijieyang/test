"""Descriptive old/new evidence overlap, explicitly not a matched-method ablation."""
from collections import Counter,defaultdict
import gzip
import json
import math
from pathlib import Path
from oracle.common.artifacts import digest,content_digest,owned_output,write_json,package_sources,freeze_sources
from oracle.common.offline_audit import identity
from oracle.research.full_worker import load_task
from oracle.research.full_report import resolve_evidence
from oracle.verification.motion import orientation_error


def overlap_label(previous,current):
    return 'both_pass' if previous and current else 'historical_only_pass' if previous else 'current_only_pass' if current else 'both_failed'


def compare(case_root,output):
    startup=identity();root=Path(case_root).resolve();output=owned_output(root,output)
    if output.exists():raise FileExistsError(output)
    meta_path=root/'outputs/oracleAdapter/endpoint-history-metadata-v1/metadata.json.gz'
    meta=json.loads(gzip.decompress(meta_path.read_bytes()))
    run=root/'outputs/oracleAdapter/full-continuous-reference-v1';snapshot=root/'outputs/oracleAdapter/endpoint-cohort-snapshot-v1'
    review_path=root/'outputs/oracleAdapter/endpoint-cohort-review-v1/validation.json';review=json.loads(review_path.read_text())
    if review['records']!=3062 or review['status']!='ENDPOINT_COHORT_RECEIPTS_VERIFIED_PARENT_RUN_NOT_COMPLETE':raise ValueError('Endpoint cohort not independently reconciled')
    m=json.loads((run/'manifest.json').read_text());msha=digest(run/'manifest.json')
    if msha!=meta['new_manifest_sha256'] or msha!=review['parent_manifest_sha256']:raise ValueError('Current parent identity differs')
    old_cache=root/'outputs/oracleAdapter/reference-cache/endpoint115-v3-history'
    if digest(old_cache/'manifest.json')!=meta['old_manifest_sha256'] or digest(old_cache/'validation.json')!=meta['old_validation_sha256']:
        raise ValueError('Historical metadata provenance differs')
    current={r['task_key']:r for r in json.loads((snapshot/'selected-results.json').read_text())}
    entries={r['record']['task_key']:r for r in json.loads((run/'index.json').read_text())}
    verified={r['task_key']:r for r in json.loads((review_path.parent/'task-evidence.json').read_text())}
    if len(meta['records'])!=3062 or {r['task_key'] for r in meta['records']}!=set(current):raise ValueError('Unmatched task denominator')
    rows=[];groups=defaultdict(Counter);mismatches=Counter()
    for previous in meta['records']:
        key=previous['task_key'];row=current[key];task,_=load_task(root,m,entries[key],run/'tasks.jsonl')
        rp=resolve_evidence(row['receipt'],run,meta['records'][0]['old_index']['result_path'].split('/outputs/')[0]+'/outputs/oracleAdapter/'+run.name)
        if digest(rp)!=row['receipt_sha256'] or digest(rp)!=verified[key]['receipt_sha256'] or content_digest(task)!=verified[key]['task_sha256']:
            raise ValueError('Current task/receipt identity differs')
        receipt=json.loads(rp.read_text());result_path=rp.parent.parent/'execute/motion/result.json'
        if digest(result_path)!=receipt['result_sha256']:raise ValueError('Current result changed')
        result=json.loads(result_path.read_text());old=previous['old_result'];oi=previous['old_input'];oa=previous['old_audit']
        checks={
            'source_input_bytes':task['source_binding']['sha256']==previous['old_input_sha256'],
            'source_manifest':task['source_binding']['manifest_sha256']==meta['old_manifest_sha256'],
            'ordered_targets':task['targets']==oi['targets']==old['targets'],
            'source_start_rotation':task['start_rotation']==oi['start_rotation'],
            'historical_rotation_equivalent':orientation_error(task['start_rotation'],old['rotation'])<=m['protocol']['maximum_orientation_error_rad'],
            'executed_start_position':math.dist(result['positions'][0],previous['old_initial_position'])<=m['protocol']['maximum_prediction_error_m'],
            'profile_identity':task['profile_sha256']==meta['old_profile_sha256'],
            'native_geometry_bytes':result['geometry_sha256']==old['native_geometry_sha256'],
            'historical_linear_sweep':oa.get('strict_sweep')=='exact_continuous_linear',
        }
        for name,passed in checks.items():mismatches[name]+=not passed
        previous_pass=previous['old_index']['status']=='PASS_STRICT_MOTION_REPLAY'
        current_pass=row['status']=='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES'
        if previous_pass and (oa['status']!='PASS_STRICT_MOTION_REPLAY' or oa['source_alerts'] or oa['max_replay_error']>m['protocol']['maximum_replay_error_m'] or not oa['independent_replay']):
            raise ValueError('Historical success contradicts its stored audit')
        label=overlap_label(previous_pass,current_pass);groups[task['cohort']][label]+=1
        rows.append(dict(task_key=key,cohort=task['cohort'],overlap=label,identity_checks=checks,
            old_result_sha256=previous['old_index']['result_sha256'],old_audit_sha256=previous['old_index']['audit_sha256'],
            current_receipt_sha256=row['receipt_sha256'],old_status=previous['old_index']['status'],current_status=row['status'],
            current_failure=row['failure'],current_detail=result['detail'],
            historical_witness_retained_not_recounted=previous_pass and not current_pass))
    output.mkdir();_,sources=package_sources();freeze_sources(output,sources);write_json(output/'all3062-overlap.json',rows)
    summary=dict(status='DESCRIPTIVE_HISTORICAL_OVERLAP_NOT_SAME_BUDGET_ALGORITHM_EFFECT',startup=startup,records=len(rows),
        groups={k:dict(v) for k,v in groups.items()},identity_mismatches=dict(mismatches),
        old_protocol_text=meta['old_protocol_text'],current_budget=m['base_method'],
        source_metadata_sha256=digest(meta_path),current_review_sha256=digest(review_path),
        output_sha256=digest(output/'all3062-overlap.json'),
        limits=['Only listed inputs/geometry and stored witness fields were compared; not a proof of identical complete simulator/planner state.',
                'Historical wall/CPU and complete privilege ledger not reconstructed; no same-budget causal comparison.',
                'Old PASS is not copied as current PASS; no union registered as an Oracle method.',
                'No new native execution or revalidation of historical actions; original audits remain their original evidence.',
                'Current finite failures with historical witnesses must not be labelled data physically unreachable.'])
    write_json(output/'validation.json',summary);return summary
