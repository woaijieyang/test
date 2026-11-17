"""Freeze a finite Landmark-only three-arm comparison; sealed baselines excluded."""
import hashlib,json
from pathlib import Path
from oracle.common.artifacts import content_digest,digest,owned_output,write_json,package_sources,freeze_sources,timestamp
from oracle.research.full_worker import load_task


def prepare(case_root,output):
    root=Path(case_root).resolve();output=owned_output(root,output);package,sources=package_sources()
    cfg=json.loads((package/'configs/experiments/reference_progress_development_v1.json').read_text())
    evidence=root/cfg['lineage'];assert digest(evidence)==cfg['lineage_sha256']
    rows=json.loads(evidence.read_text());parent=root/'outputs/oracleAdapter/full-continuous-reference-v1'
    pm=json.loads((parent/'manifest.json').read_text())
    index={e['record']['task_key']:e for e in json.loads((parent/'index.json').read_text())}
    groups={k:[] for k in cfg['selection_counts']};seen=set()
    for row in sorted(rows,key=lambda r:r['task_key']):
        c=row['contract']
        if c['dataset']!='landmark_rxr' or c['split']!='train' or c['official_policy']!='guard_then_search' or not row['failure_explanation']['endpoint_source_gate']:
            continue
        if row['status']=='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES':role='success_control'
        elif row['failure']=='search_budget_exhausted' and 'source_exhausted' in row['switch_reasons']:role='source_exhausted_budget_failure'
        elif row['failure']=='search_budget_exhausted' and 'proposal_rejected' in row['switch_reasons']:role='proposal_rejected_budget_failure'
        else:continue
        if len(groups[role])>=cfg['selection_counts'][role]:continue
        task,_=load_task(root,pm,index[row['task_key']],parent/'tasks.jsonl')
        physical=content_digest([task['scene'],task['targets'],task['start_rotation']])
        if physical in seen:continue
        seen.add(physical);groups[role].append((row,task))
    if any(len(groups[k])!=n for k,n in cfg['selection_counts'].items()):
        raise ValueError('Insufficient fixed distinct Landmark development tasks: '+str({k:len(v) for k,v in groups.items()}))
    cache_gate=root/cfg['cache_gate'];gate=json.loads(cache_gate.read_text())
    if gate['status']!='ALL71_RECORDED_QUERY_CACHE_EQUIVALENCE_PASS_NOT_NAVIGATION' or gate['scenes']!=71:
        raise ValueError('Complete cache equivalence gate required')
    tuning=json.loads((package/'configs/methods/reference_progress_cache_v1.json').read_text())
    base={**pm['base_method'],'official_policy':'guard_then_search'}
    methods=[{**base,'id':'unchanged_control'},
             {**base,'id':'cache_only','planning_query_cache':tuning['planning_query_cache']},
             {**base,'id':'cache_plus_reference_progress','planning_query_cache':tuning['planning_query_cache'],
              'reference_progress_guard':tuning['reference_progress_guard']}]
    output.mkdir(parents=True,exist_ok=False);items=[]
    for role,pairs in groups.items():
        for row,task in pairs:
            original=content_digest(task);task['module_source_sha256']=content_digest(sources)
            task['cohort']='landmark_train_same_official_information::'+role
            task['selection_role']=role
            p=output/'inputs'/(hashlib.sha256(task['task_key'].encode()).hexdigest()[:24]+'.json')
            write_json(p,task);items.append(dict(task_key=task['task_key'],path=str(p),sha256=digest(p),
                cohort=task['cohort'],selection_role=role,source_task_sha256=original,
                source_receipt_sha256=row['receipt_sha256']))
    manifest=dict(status='FROZEN_LANDMARK_ONLY_PROGRESS_CACHE_DEVELOPMENT',created_at=timestamp(),
        config=cfg,protocol=pm['protocol'],sources=sources,methods=methods,tasks=items,
        expected_tasks=len(items),expected_executions=len(items)*len(methods),source_scope_denominator=33954,
        cache_gate_sha256=digest(cache_gate),lineage_sha256=digest(evidence),parent_manifest_sha256=digest(parent/'manifest.json'),
        experimental_factor='Three arms isolate cache acceleration from the added reference-progress switch. Same actual privileged inputs and physical tasks. No new source mapping.',
        scope=cfg['scope'],launchers={str(root/'oracleAdapter/run.py'):digest(root/'oracleAdapter/run.py'),
              str(root/'scripts/with_runtime.sh'):digest(root/'scripts/with_runtime.sh')})
    write_json(output/'manifest.json',manifest);freeze_sources(output,sources)
    write_json(output/'state.json',dict(status='PREPARED',expected=manifest['expected_executions']))
    return manifest
