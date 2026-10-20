"""Freeze the same source-available cohort before evaluating a fixed fallback."""
import json
from pathlib import Path
from oracle.common.artifacts import content_digest,digest,freeze_sources,owned_output,package_sources,timestamp,write_json


def prepare(case_root,output):
    root=Path(case_root).resolve();output=owned_output(root,output)
    package,sources=package_sources()
    config=json.loads((package/'configs/experiments/guarded_portfolio.json').read_text())
    prior=root/config['source_run'];old=json.loads((prior/'manifest.json').read_text())
    validated=json.loads((prior/'validation.json').read_text())
    if not validated['complete'] or validated['manifest_sha256']!=digest(prior/'manifest.json'):
        raise ValueError('Source plan binding run incomplete or changed')
    protocol=json.loads((package/config['protocol_config']).read_text())
    if protocol!=old['protocol']:raise ValueError('Motion acceptance cannot change between demonstrations and portfolio')
    if len(old['tasks'])!=config['expected_tasks']:raise ValueError('Unexpected development denominator')
    output.mkdir(parents=True,exist_ok=False);tasks=[]
    for item in old['tasks']:
        path=Path(item['path'])
        if digest(path)!=item['sha256']:raise ValueError('Source task drift')
        task=json.loads(path.read_text());task['module_source_sha256']=content_digest(sources)
        task['cohort']='same_information_guarded_official_prefix'
        task['prior_source_task_sha256']=item['sha256']
        target=output/'inputs'/path.name;write_json(target,task)
        tasks.append({**item,'path':str(target),'sha256':digest(target),'cohort':task['cohort']})
    methods=[{**config['common_method'],**method} for method in config['methods']]
    manifest={'status':'FROZEN_BEFORE_GUARDED_PORTFOLIO_EXECUTION','created_at':timestamp(),
        'config':config,'protocol':protocol,'sources':sources,'methods':methods,'tasks':tasks,
        'expected_tasks':len(tasks),'expected_executions':len(tasks)*len(methods),
        'source_scope_denominator':old['source_scope_denominator'],'nonexecuted_source_records':old['nonexecuted_source_records'],
        'prior_manifest_sha256':digest(prior/'manifest.json'),'prior_validation_sha256':digest(prior/'validation.json'),
        'experimental_factor':'Same source information and precheck; fixed fallback enabled versus disabled. No mapping/body/initial-state changes.',
        'scope':config['scope'],'launchers':{str(root/'oracleAdapter/run.py'):digest(root/'oracleAdapter/run.py'),
                                          str(root/'scripts/with_runtime.sh'):digest(root/'scripts/with_runtime.sh')}}
    if manifest['expected_executions']!=config['expected_executions']:raise ValueError('Execution matrix mismatch')
    write_json(output/'manifest.json',manifest);freeze_sources(output,sources)
    write_json(output/'state.json',{'status':'PREPARED','expected':manifest['expected_executions'],
                                  'source_scope_denominator':manifest['source_scope_denominator']})
    return manifest
