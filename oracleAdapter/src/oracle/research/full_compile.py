"""Compile a complete executable stream from immutable inventory and sources."""
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path

from oracle.common.artifacts import content_digest,digest,freeze_sources,owned_output,package_sources,timestamp,write_json
from oracle.common.task_index import merkle_index
from oracle.teachers.official import expand_actions
from oracle.adapters.unified_inventory import pose_relation


def compile_run(case_root,output,engineering=False):
    root=Path(case_root).resolve();output=owned_output(root,output);package,sources=package_sources()
    config=json.loads((package/'configs/experiments/full_validation.json').read_text())
    source_expected=dict(config['expected'])
    if engineering:config.update(json.loads((package/'configs/experiments/full_validation_gate.json').read_text()))
    inventory=root/config['inventory'];receipt=json.loads((inventory/'validation.json').read_text())
    if receipt['datasets']!=source_expected:raise ValueError('Inventory scope differs')
    if digest(inventory/'tasks.jsonl')!=receipt['targets_file_sha256'] or digest(inventory/'index.json')!=receipt['index_sha256']:
        raise ValueError('Inventory bytes changed')
    index=json.loads((inventory/'index.json').read_text());protocol=json.loads((package/config['protocol_config']).read_text())
    method=json.loads((package/config['method_config']).read_text())['common_method']
    assets=json.loads((root/config['official_asset_receipt']).read_text())
    locks={str(Path(s['path']).resolve()):s['sha256'] for s in assets['sources']}
    needed={};tasks=[]
    with (inventory/'tasks.jsonl').open('rb') as stream:
        for entry in index:
            stream.seek(entry['offset']);data=stream.read(entry['bytes'])
            if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Indexed inventory record changed')
            task=json.loads(data)
            if task['task_key']!=entry['task_key']:raise ValueError('Inventory index identity mismatch')
            tasks.append(task)
    if engineering:
        ordered=sorted(tasks,key=lambda t:t['task_key'])
        conditions=[lambda t:t['dataset']=='landmark_rxr' and not t['coordinates_complete'],
                    lambda t:t['dataset']=='r2r',
                    lambda t:t['dataset']=='rxr' and t['coordinates_complete'] and t['reference_action_pose_relation']['numeric_initial_pose_match'],
                    lambda t:t['dataset']=='landmark_rxr' and t['coordinates_complete'] and bool(t.get('legacy_static_errors'))]
        tasks=[next(t for t in ordered if condition(t)) for condition in conditions]
    for task in tasks:
        if task['reference_action_pose_relation']['numeric_initial_pose_match'] and task['coordinates_complete']:
            needed.setdefault(task['split'],set()).add(task['reference_action_pose_relation']['source_episode_id'])
    plans={};plan_sources=[];ce=root/'data/datasets/RxR_VLNCE_v0'
    for split,ids in needed.items():
        ep=ce/split/f'{split}_guide.json.gz';gt=ce/split/f'{split}_guide_gt.json.gz'
        for p in (ep,gt):
            if digest(p)!=locks[str(p.resolve())]:raise ValueError('Official source drift')
        with gzip.open(ep,'rt') as stream:episodes=json.load(stream)['episodes']
        metadata={str(e['episode_id']):{'instruction_id':str(e['instruction']['instruction_id']),
            'scene':Path(e['scene_id']).parent.name,'language':e['instruction']['language'],
            'path_id':str(e['trajectory_id']),'start_position':e['start_position'],'start_rotation':e['start_rotation']}
            for e in episodes if str(e['episode_id']) in ids}
        del episodes
        with gzip.open(gt,'rt') as stream:rows=json.load(stream)
        for eid in ids:
            actions=rows[eid]['actions'];expand_actions(actions)
            plans[(split,eid)]={**metadata[eid],'actions':actions,'actions_sha256':content_digest(actions),
                'source_gt_sha256':locks[str(gt.resolve())],'source_annotation_sha256':locks[str(ep.resolve())],
                'episode_id':eid,'source_turn_degrees':30,'source_step_m':.25,
                'scope':'Untrusted reference suggestions, not cached successful execution'}
        plan_sources.extend([{'path':str(p),'sha256':locks[str(p.resolve())]} for p in (ep,gt)])
        del rows
    output.mkdir(parents=True,exist_ok=False);entries=[];counts=Counter();branches=Counter()
    with (output/'tasks.jsonl').open('xb') as stream:
        for task in tasks:
            task.pop('execution_source_binding_pending',None)
            task['module_source_sha256']=content_digest(sources)
            relation=task['reference_action_pose_relation'];key=(task['split'],relation.get('source_episode_id'))
            eligible=task['coordinates_complete'] and relation['numeric_initial_pose_match'] and key in plans
            if eligible:
                plan=plans[key]
                if plan['source_annotation_sha256']!=relation['source_annotation_sha256']:raise ValueError('Pose source and action source differ')
                if plan['instruction_id']!=task['instruction_id'] or plan['scene']!=task['scene'] or plan['language']!=task['language']:
                    raise ValueError('Official instruction/scene/language differs')
                if task.get('path_id') is not None and task['path_id']!=plan['path_id']:raise ValueError('Official path identity differs')
                verified=pose_relation(task,{'start_position':plan['start_position'],'quaternion_xyzw':plan['start_rotation']},
                    protocol['maximum_prediction_error_m'],protocol['maximum_orientation_error_rad'])
                if not verified['numeric_initial_pose_match']:raise ValueError('Source pose compatibility not reproduced')
                task['official_demonstration']=plan
                task['privileges']=[*task['privileges'],'official_actions']
            task['method_selection']={'official_policy':'guard_then_search' if eligible else 'none',
                'reason':'source_identity_and_initial_pose_match' if eligible else relation['status'],
                'rule_sha256':digest(package/'configs/experiments/full_validation.json')}
            task['cohort']=task['dataset']+('::matched_official_actions' if eligible else '::no_compatible_action_prior')
            data=(json.dumps(task,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode()
            offset=stream.tell();stream.write(data)
            entries.append({'task_key':task['task_key'],'dataset':task['dataset'],'offset':offset,'bytes':len(data),
                            'sha256':hashlib.sha256(data).hexdigest(),'cohort':task['cohort']})
            counts[task['dataset']]+=1;branches[task['cohort']]+=1
        stream.flush();os.fsync(stream.fileno())
    if dict(counts)!=config['expected'] or len({e['task_key'] for e in entries})!=len(entries):raise ValueError('Compiled coverage mismatch')
    merkle,proofs=merkle_index(entries);write_json(output/'index.json',proofs)
    manifest={'status':'FROZEN_FULL_CONTINUOUS_REFERENCE_VALIDATION','created_at':timestamp(),'config':config,
        'protocol':protocol,'base_method':method,'sources':sources,'task_count':len(entries),
        'datasets':dict(counts),'information_branches':dict(branches),'task_merkle_root':merkle,
        'tasks_file_sha256':digest(output/'tasks.jsonl'),'index_sha256':digest(output/'index.json'),
        'inventory_validation_sha256':digest(inventory/'validation.json'),'official_action_sources':plan_sources,
        'launchers':{str(root/'oracleAdapter/run.py'):digest(root/'oracleAdapter/run.py'),str(root/'scripts/with_runtime.sh'):digest(root/'scripts/with_runtime.sh')},
        'scope':config['scope'],'target_scope':config['target_scope']}
    write_json(output/'manifest.json',manifest);freeze_sources(output,sources)
    write_json(output/'state.json',{'status':'PREPARED_NOT_RUN','expected':len(entries),'completed':0})
    return manifest
