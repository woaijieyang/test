"""Matched physical tasks with privileged action suggestions genuinely removed."""
import copy
import json
from pathlib import Path
from oracle.common.artifacts import content_digest,digest,freeze_sources,owned_output,package_sources,timestamp,write_json


def physical_identity(task):
    return content_digest({k:task[k] for k in ['scene','targets','start_rotation','profile_path','profile_sha256',
        'geometry_catalog_sha256','purpose','objective']})


def remove_action_information(task):
    result=copy.deepcopy(task)
    result.pop('official_demonstration',None);result.pop('historical_replay_status',None)
    result['privileges']=[p for p in result['privileges'] if p!='official_actions']
    if physical_identity(result)!=physical_identity(task):raise ValueError('Physical task changed')
    return result


def prepare(case_root,output):
    root=Path(case_root).resolve();output=owned_output(root,output);package,sources=package_sources()
    config=json.loads((package/'configs/experiments/search_ablation.json').read_text())
    prior=root/config['source_run'];old=json.loads((prior/'manifest.json').read_text());checked=json.loads((prior/'validation.json').read_text())
    if not checked['complete'] or checked['manifest_sha256']!=digest(prior/'manifest.json'):raise ValueError('Parent not complete or changed')
    public=json.loads((package/config['shared_public_method_config']).read_text())
    if public['common_method']!=old['config']['common_method']:raise ValueError('Public and frozen comparison budgets differ')
    protocol=json.loads((package/config['protocol_config']).read_text())
    if protocol!=old['protocol']:raise ValueError('Physical acceptance changed')
    if len(old['tasks'])!=config['expected_tasks']:raise ValueError('Matched scope changed')
    method={**public['common_method'],'id':config['method_id'],'official_policy':'none'}
    method.pop('source_turn_degrees')
    output.mkdir(parents=True,exist_ok=False);tasks=[]
    for item in old['tasks']:
        p=Path(item['path'])
        if digest(p)!=item['sha256']:raise ValueError('Source task changed')
        parent_task=json.loads(p.read_text());task=remove_action_information(parent_task)
        task['module_source_sha256']=content_digest(sources);task['cohort']='matched_initial_search_without_official_actions'
        task['parent_physical_identity']=physical_identity(parent_task)
        task['parent_task_sha256']=item['sha256']
        target=output/'inputs'/p.name;write_json(target,task)
        tasks.append({'task_key':task['task_key'],'path':str(target),'sha256':digest(target),
                      'cohort':task['cohort'],'physical_identity':physical_identity(task),
                      'selection_role':'all_matched133_no_outcome_selection'})
    manifest={'status':'FROZEN_BEFORE_MATCHED_SEARCH_ABLATION','created_at':timestamp(),
        'config':config,'protocol':protocol,'sources':sources,'methods':[method],'tasks':tasks,
        'expected_tasks':len(tasks),'expected_executions':len(tasks),
        'parent_source_scope_denominator':old['source_scope_denominator'],
        'parent_reference_source_unavailable_records':old['nonexecuted_source_records'],
        'not_executed_parent_records_reason':'Not in matched133 development cohort; not failures of this pure-search method',
        'prior_manifest_sha256':digest(prior/'manifest.json'),'prior_validation_sha256':digest(prior/'validation.json'),
        'scope':config['scope'],'experimental_factor':'Official action payload and privilege absent; physical task and ceilings unchanged. Separate information-condition table.',
        'launchers':{str(root/'oracleAdapter/run.py'):digest(root/'oracleAdapter/run.py'),str(root/'scripts/with_runtime.sh'):digest(root/'scripts/with_runtime.sh')}}
    write_json(output/'manifest.json',manifest);freeze_sources(output,sources)
    write_json(output/'state.json',{'status':'PREPARED','expected':len(tasks),'parent_scope':old['source_scope_denominator']})
    return manifest
