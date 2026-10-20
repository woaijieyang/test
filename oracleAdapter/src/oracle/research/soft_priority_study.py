"""One frozen soft-priority candidate; reuse the full execution/audit controller."""
import copy
import hashlib
import json
from pathlib import Path
from oracle.common.artifacts import (content_digest,digest,owned_output,write_json,
    package_sources,freeze_sources,timestamp)
from oracle.common.task_index import merkle_index
from oracle.research.full_worker import validate_launchers
from oracle.research.priority_study import make_task
from oracle.planners.soft_duplicate import validate_config


def method_pair(base,penalty):
    validate_config(penalty)
    if base.get('state_key')!='lossless_pose' or base.get('search_priority_weight',1.)!=1. or 'soft_duplicate_priority' in base:
        raise ValueError('Expected unmodified exact-key priority1 control')
    a=copy.deepcopy(base);a['id']='soft_priority_control'
    b=copy.deepcopy(base);b.update(id='soft_priority_candidate',soft_duplicate_priority=copy.deepcopy(penalty))
    return [a,b]


def prepare(case_root,output):
    root=Path(case_root).resolve();out=owned_output(root,output);package,sources=package_sources()
    cfg=json.loads((package/'configs/experiments/soft_priority_study_v1.json').read_text())
    bp=root/cfg['budget_receipt'];budget=json.loads(bp.read_text())
    if (digest(bp)!=cfg['budget_sha256'] or budget['new_stage_reserved_seconds']!=21600
            or budget['development_after_new_reservation_seconds']>86400 or budget['overall_after_new_reservation_seconds']>2592000):
        raise ValueError('Original cumulative budget admission failed')
    for name in cfg['closed_runs']:
        if json.loads((root/name/'source-freeze.json').read_text())['status']!='CLOSED':raise ValueError('Owned previous run not closed')
    selected_path=root/cfg['selection'];assert digest(selected_path)==cfg['selection_sha256']
    selected=json.loads(selected_path.read_text());assert len(selected)==16
    parent=root/cfg['parent_run'];mp=parent/'manifest.json';m=json.loads(mp.read_text())
    assert digest(mp)==cfg['parent_manifest_sha256'] and digest(parent/'tasks.jsonl')==m['tasks_file_sha256']
    original={t['task_key']:t for t in map(json.loads,(parent/'tasks.jsonl').read_text().splitlines())}
    tasks=[make_task(original[x['task_key']],content_digest(sources)) for x in selected]
    assert len({t['task_key'] for t in tasks})==16 and len(tasks)==len(original)
    out.mkdir();freeze_sources(out,sources);arms=[]
    for method in method_pair(m['base_method'],cfg['soft_duplicate_priority']):
        folder=out/'runs'/method['id'];folder.mkdir(parents=True);entries=[]
        with (folder/'tasks.jsonl').open('xb') as stream:
            for task in tasks:
                raw=(json.dumps(task,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode();offset=stream.tell();stream.write(raw)
                entries.append(dict(task_key=task['task_key'],dataset='landmark_rxr',offset=offset,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),cohort=task['cohort']))
        merkle,index=merkle_index(entries);write_json(folder/'index.json',index)
        am={**m,'status':'FROZEN_FIXED16_SOFT_PRIORITY_ARM','created_at':timestamp(),'sources':sources,
            'config':{**m['config'],'max_workers':32,'total_cpu_budget_hours':3.,'maximum_infrastructure_attempts':1,'scope':cfg['scope']},
            'base_method':method,'tasks_file_sha256':digest(folder/'tasks.jsonl'),'index_sha256':digest(folder/'index.json'),
            'task_merkle_root':merkle,'scope':cfg['scope'],'limits':'Fixed known-train development only; occupancy hint changes priority, never identity or legality.',
            'launchers':{str(p):digest(p) for p in [root/'oracleAdapter/run.py',root/'scripts/with_runtime.sh']}}
        validate_launchers(root,am);write_json(folder/'manifest.json',am);freeze_sources(folder,sources)
        arms.append(dict(id=method['id'],manifest=str(folder/'manifest.json'),manifest_sha256=digest(folder/'manifest.json')))
    outer=dict(status='FROZEN_SOFT_PRIORITY_FIXED16',created_at=timestamp(),comparison_kind='soft_priority',sources=sources,
        config=cfg,selected=selected,arms=arms,maximum_cpu_seconds=2*3*3600-3605,budget_receipt_sha256=digest(bp),
        expected_tasks=16,expected_executions=32,global_landmark_denominator=33954)
    write_json(out/'manifest.json',outer);return outer
