"""One declared real integration gate for stronger evidence, no outcome tuning."""
import json
from pathlib import Path
from oracle.common.artifacts import content_digest,digest,freeze_sources,owned_output,package_sources,timestamp,write_json


def prepare(case_root,output):
    root=Path(case_root).resolve();output=owned_output(root,output);package,sources=package_sources()
    config=json.loads((package/'configs/experiments/execution_gate.json').read_text())
    prior=root/config['source_run'];parent=json.loads((prior/'manifest.json').read_text());validation=json.loads((prior/'validation.json').read_text())
    if not validation['complete'] or validation['manifest_sha256']!=digest(prior/'manifest.json'):raise ValueError('Parent binding changed')
    old=next(t for t in parent['tasks'] if t['task_key']==config['task_key'])
    if digest(old['path'])!=old['sha256']:raise ValueError('Parent input changed')
    task=json.loads(Path(old['path']).read_text());task['module_source_sha256']=content_digest(sources)
    task['cohort']='engineering_execution_evidence_gate'
    method=next(m for m in parent['methods'] if m['id']==config['method_id'])
    output.mkdir(parents=True,exist_ok=False);p=output/'inputs'/'task.json';write_json(p,task)
    manifest={'status':'FROZEN_ENGINEERING_GATE','created_at':timestamp(),'config':config,'sources':sources,
        'methods':[method],'protocol':parent['protocol'],'tasks':[{'task_key':task['task_key'],'path':str(p),'sha256':digest(p),'cohort':task['cohort']}],
        'expected_tasks':1,'expected_executions':1,'scope':config['scope'],
        'parent_manifest_sha256':digest(prior/'manifest.json'),
        'launchers':{str(root/'oracleAdapter/run.py'):digest(root/'oracleAdapter/run.py'),str(root/'scripts/with_runtime.sh'):digest(root/'scripts/with_runtime.sh')}}
    write_json(output/'manifest.json',manifest);freeze_sources(output,sources)
    write_json(output/'state.json',{'status':'PREPARED','expected':1});return manifest
