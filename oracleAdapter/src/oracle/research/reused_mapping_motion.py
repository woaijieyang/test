"""Fresh affected102 motion test of independently revalidated historical mappings."""
import hashlib,json
from pathlib import Path
from oracle.common.artifacts import content_digest,digest,owned_output,write_json,package_sources,freeze_sources,timestamp
from oracle.common.task_index import merkle_index
from oracle.research.full_worker import load_task
from oracle.research.mapping_factorial import variant_task


def bind_reused_task(original,record,source_digest):
    if (record['status']!='PASS_REUSED_PROPOSAL_RATIONAL_STATIC_NOT_MOTION'
            or not record['potential_strict_endpoint_repair'] or record['task_key']!=original['task_key']
            or record['old_targets']!=original['targets'] or record['original_heading']!=original['raw_heading']
            or record['raw_source_record_sha256']!=original['legacy_source_record_sha256']):
        raise ValueError('Reused proposal does not bind the original task and independent static gate')
    task=variant_task(original,record,True,source_digest,content_digest(record))
    task['cohort']='landmark_D7_existing_bounded102_pure_search'
    task['mapping_study_provenance']['candidate_family']='existing_same_profile_body_bounded'
    return task


def prepare(case_root,output):
    root=Path(case_root).resolve();output=owned_output(root,output);package,sources=package_sources()
    if output.exists():raise FileExistsError(output)
    cfg_path=package/'configs/experiments/reused_mapping_motion_v1.json';cfg=json.loads(cfg_path.read_text())
    audit_path=root/cfg['static_audit'];audit=json.loads(audit_path.read_text())
    if digest(audit_path)!=cfg['static_audit_sha256'] or audit['potential_strict_endpoint_repair']!=102:raise ValueError('Fresh static reuse audit differs')
    records_path=audit_path.parent/'records.json'
    if digest(records_path)!=audit['records_sha256']:raise ValueError('Static records changed')
    records=[r for r in json.loads(records_path.read_text()) if r['potential_strict_endpoint_repair']]
    if len(records)!=102 or len({r['task_key'] for r in records})!=102:raise ValueError('Affected102 coverage differs')
    parent=root/'outputs/oracleAdapter/full-continuous-reference-v1';pm=json.loads((parent/'manifest.json').read_text())
    if digest(parent/'manifest.json')!=cfg['parent_manifest_sha256']:raise ValueError('Parent tasks changed')
    entries={e['record']['task_key']:e for e in json.loads((parent/'index.json').read_text())}
    matrix=root/'outputs/oracleAdapter/dense-mapping-factorial93-v1';mm=json.loads((matrix/'manifest.json').read_text());mv=json.loads((matrix/'validation.json').read_text())
    if not (matrix/'factorial-report/validation.json').exists() or mv['manifest_sha256']!=digest(matrix/'manifest.json'):raise ValueError('Prior matrix not fully reviewed')
    for path in cfg['unchanged_execution_modules']:
        if sources[path]!=mm['sources'][path]:raise ValueError('Execution algorithm changed beyond mapping: '+path)
    spent=mm['old_full_charge_seconds']+mv['charged_cpu_upper_bound_seconds']
    if spent+cfg['total_cpu_budget_hours']*3600>720*3600:raise ValueError('Original720CPUh envelope exceeded')
    prior_candidate=Path(next(a['manifest'] for a in mm['arms'] if a['id']=='candidate_map_cache')).parent
    prior_tasks={t['task_key']:t for t in map(json.loads,(prior_candidate/'tasks.jsonl').read_text().splitlines())}
    cache=json.loads((package/'configs/methods/reference_progress_cache_v1.json').read_text())['planning_query_cache']
    method={**pm['base_method'],'id':'bounded_reference_search_exact_cache_v1','planning_query_cache':cache}
    output.mkdir();compiled=[];overlap=[]
    with (output/'tasks.jsonl').open('xb') as stream:
        for record in sorted(records,key=lambda r:r['task_key']):
            original,_=load_task(root,pm,entries[record['task_key']],parent/'tasks.jsonl')
            task=bind_reused_task(original,record,content_digest(sources))
            if task['task_key'] in prior_tasks:
                old=prior_tasks[task['task_key']]
                overlap.append({'task_key':task['task_key'],'same_numeric_targets':old['targets']==task['targets'],
                    'same_initial_rotation':old['start_rotation']==task['start_rotation'],'prior_task_sha256':content_digest(old)})
            data=(json.dumps(task,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode();offset=stream.tell();stream.write(data)
            compiled.append({'task_key':task['task_key'],'dataset':'landmark_rxr','offset':offset,'bytes':len(data),
                'sha256':hashlib.sha256(data).hexdigest(),'cohort':task['cohort']})
    merkle,index=merkle_index(compiled);write_json(output/'index.json',index)
    config={**pm['config'],'max_workers':4,'per_process_wall_seconds':900,'total_cpu_budget_hours':cfg['total_cpu_budget_hours'],
        'maximum_infrastructure_attempts':1,'expected':{'landmark_rxr':102},'scope':cfg['scope'],'method_config':'explicit_frozen_base_method_in_manifest'}
    manifest={'status':'FROZEN_EXISTING_BOUNDED_MAPPING102_NATIVE_VALIDATION','created_at':timestamp(),'config':config,
        'protocol':pm['protocol'],'base_method':method,'sources':sources,'task_count':102,'datasets':{'landmark_rxr':102},
        'task_merkle_root':merkle,'tasks_file_sha256':digest(output/'tasks.jsonl'),'index_sha256':digest(output/'index.json'),
        'launchers':{str(root/'oracleAdapter/run.py'):digest(root/'oracleAdapter/run.py'),str(root/'scripts/with_runtime.sh'):digest(root/'scripts/with_runtime.sh')},
        'scope':cfg['scope'],'target_scope':'all_original_reference_occurrences_and_strict_endpoint_source_gate',
        'global_landmark_denominator':33954,'static_audit_sha256':digest(audit_path),'parent_manifest_sha256':digest(parent/'manifest.json'),
        'prior_matrix_validation_sha256':digest(matrix/'validation.json'),'prior_full_charge_seconds':spent,
        'overlap_with_dense93':overlap,'official_action_sources':[],
        'comparison_limits':'Fresh evaluation of all102 fixed source-gate-selected historical proposals. Earlier original mapping strict gate failure is historical evidence, not a newly run matched control. Overlap with dense93 is explicitly recorded; never add overlapping recoveries or register a successful-method union.'}
    write_json(output/'manifest.json',manifest);freeze_sources(output,sources);write_json(output/'state.json',{'status':'PREPARED_NOT_RUN','expected':102,'completed':0})
    return manifest


def run_with_review(case_root,manifest_path):
    root=Path(case_root).resolve();mp=Path(manifest_path).resolve();run=owned_output(root,mp.parent)
    if (run/'controller-process.json').exists():raise ValueError('Existing run requires explicit review before resume')
    from oracle.research.full_run import run as execute
    from oracle.research.full_review import review
    from oracle.research.full_report import report
    if not execute(root,mp):raise RuntimeError('Affected102 run stopped; preserve evidence and inspect, do not retry automatically')
    closure=json.loads((run/'source-freeze.json').read_text())
    if closure['status']!='CLOSED' or closure['live_phase_receipts']:raise RuntimeError('Owned phases remain live')
    review(root,run,run/'independent-full-review')
    report(root,run,run/'independent-full-review/validation.json',run/'grouped-report')
    write_json(run/'review-complete.json',dict(status='AFFECTED102_COMPLETE_INDEPENDENT_REVIEW_NOT_GLOBAL_ACCEPTANCE',
        manifest_sha256=digest(mp),report_sha256=digest(run/'grouped-report/validation.json'),global_landmark_denominator=33954,global_acceptance=False))
    write_json(run/'state.json',dict(status='COMPLETE_AFFECTED102_REVIEW_NOT_GLOBAL_ACCEPTANCE',completed=102,expected=102,time=timestamp()),immutable=False)
