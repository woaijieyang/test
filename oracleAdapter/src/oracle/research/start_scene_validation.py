"""Whole affected-scene validation after a fixed initial-point proposal."""
import copy,hashlib,json,math,os
from collections import Counter
from pathlib import Path
from oracle.common.artifacts import content_digest,digest,owned_output,write_json,package_sources,freeze_sources,timestamp
from oracle.common.task_index import merkle_index
from oracle.research.full_worker import load_task,validate_launchers
from oracle.research.start_pose_proposals import frozen_anchor,fixed_ring_offsets


def repaired_task(original,proposal,source_digest):
    if original['dataset']!='landmark_rxr' or original['scene']!='oLBMNvg9in8':raise ValueError('Wrong affected scene or sealed dataset')
    if ('official_demonstration' in original or original['method_selection']['official_policy']!='none'):
        raise ValueError('Cannot silently alter an official-action information condition')
    if (proposal['old_targets']!=original['targets'] or proposal['proposed_targets'][1:]!=original['targets'][1:]
            or proposal['original_heading']!=original['raw_heading'] or proposal['start_rotation']!=original['start_rotation']):
        raise ValueError('Repair changed more than the declared initial coordinate')
    t=copy.deepcopy(original);t['targets']=copy.deepcopy(proposal['proposed_targets']);t['module_source_sha256']=source_digest
    t['cohort']=original['cohort']+'::actuation_safe_initial'
    t['initial_repair_provenance']={'old_initial':original['targets'][0],'original_anchor':proposal['original_anchor'],
                                    'proposal_sha256':content_digest(proposal),'original_task_sha256':content_digest(original)}
    return t


def prepare(case_root,output,cpu):
    if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
    root=Path(case_root).resolve();out=owned_output(root,output);package,sources=package_sources()
    cfg=json.loads((package/'configs/experiments/start_scene_validation_v1.json').read_text())
    parent=root/cfg['parent_run'];pm=json.loads((parent/'manifest.json').read_text());pv=json.loads((parent/'validation.json').read_text())
    if digest(parent/'manifest.json')!=cfg['parent_manifest_sha256'] or json.loads((parent/'source-freeze.json').read_text())['status']!='CLOSED':raise ValueError('Parent identity/closure drift')
    if digest(parent/'index.json')!=pm['index_sha256'] or digest(parent/'tasks.jsonl')!=pm['tasks_file_sha256']:raise ValueError('Parent task stream changed')
    proposal_run=root/cfg['proposal_run'];proposal_validation=json.loads((proposal_run/'validation.json').read_text())
    if digest(proposal_run/'validation.json')!=cfg['proposal_validation_sha256'] or proposal_validation['proposed']!=27:raise ValueError('Fixed27 proposals not complete')
    if digest(proposal_run/'records27.json')!=proposal_validation['records_sha256']:raise ValueError('Proposal records changed')
    proposals={r['task_key']:r for r in json.loads((proposal_run/'records27.json').read_text())}
    legacy_path=root/cfg['legacy_manifest'];legacy=json.loads(legacy_path.read_text())
    if digest(legacy_path)!=cfg['legacy_manifest_sha256']:raise ValueError('Scene selection source changed')
    scene_keys={t['task_key'] for t in legacy['tasks'] if t['scene']=='oLBMNvg9in8'}
    if len(scene_keys)!=741 or not set(proposals)<=scene_keys:raise ValueError('Complete741 scene scope changed')
    held=set(json.loads((root/'outputs/landmark-connectivity/constraint-blockers.json').read_text())['task_keys'])
    if held&set(proposals):raise ValueError('Held records cannot change')
    previous=pm['prior_full_charge_seconds']+pv['charged_cpu_upper_bound_seconds']
    if previous+24*3600+cfg['total_cpu_budget_hours']*3600>720*3600:raise ValueError('Original full budget exhausted')
    if cpu not in sorted(os.sched_getaffinity(0))[:64]:raise ValueError('CPU outside64')
    os.sched_setaffinity(0,{cpu});os.environ['CUDA_VISIBLE_DEVICES']=''
    index={r['record']['task_key']:r for r in json.loads((parent/'index.json').read_text())}
    tasks={k:load_task(root,pm,index[k],parent/'tasks.jsonl')[0] for k in sorted(scene_keys)}
    if any(t['scene']!='oLBMNvg9in8' for t in tasks.values()):raise ValueError('Scene mapping mismatch')
    from oracle.adapters.habitat.assets import resolve
    from oracle.verification.source_scene import SourceScene
    import habitat_sim
    asset,geometry=resolve(root,next(iter(tasks.values())));pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path'])
    source=SourceScene(geometry['receipt_path'],geometry['receipt_sha256'],pm['protocol'],catalog=geometry)
    policy=json.loads((package/'configs/experiments/global_bounded_mapping_v1.json').read_text());offsets=fixed_ring_offsets(policy['rings'])
    pubpath=root/policy['inputs']['published']['path'];assert digest(pubpath)==policy['inputs']['published']['sha256']
    published={(x['scene'],x['node']):x for x in json.loads(pubpath.read_text())['nodes']}
    audit_path=root/'outputs/oracleAdapter/global-bounded-static-audit-v2/validation.json';av=json.loads(audit_path.read_text());ap=audit_path.parent/'all33954-records.json'
    assert digest(audit_path)==pm['input_hashes']['global_audit'] and digest(ap)==av['records_sha256']
    prior_records={x['task_key']:x for x in json.loads(ap.read_text())};audit=[]
    def connected(a,b):
        p=habitat_sim.ShortestPath();p.requested_start=a;p.requested_end=b
        return bool(pf.find_path(p) and math.isfinite(p.geodesic_distance))
    for key,p in proposals.items():
        t=tasks[key];oldpath=root/'outputs/oracleAdapter/global-bounded-mapping-v1/tasks'/f"{key.replace(':','-')}.json"
        if digest(oldpath)!=prior_records[key]['proposal_sha256']:raise ValueError('Original anchor evidence changed')
        anchor=frozen_anchor(t,json.loads(oldpath.read_text()))
        if anchor!=p['original_anchor']:raise ValueError('Cumulative anchor drift')
        candidate=repaired_task(t,p,content_digest(sources));q=candidate['targets'][0];choice=p['choice'];seed=choice['seed_position']
        allowed=([t['targets'][0]] if choice['rank']==0 else [anchor] if choice['rank']==2 else [[anchor[0]+dx,anchor[1],anchor[2]+dz] for dx,dz in offsets] if choice['rank']==3 else [])
        if not any(math.dist(seed,a)<=1e-12 for a in allowed):raise ValueError('Candidate not from the frozen old seed family')
        if math.dist(q,list(pf.snap_point(seed)))>1e-5 or math.dist(q,list(pf.snap_point(q)))>1e-5 or not pf.is_navigable(q):raise ValueError('Native candidate cannot be independently reproduced')
        if math.dist(q,anchor)>.5 or (choice['rank']>=3 and math.hypot(q[0]-anchor[0],q[2]-anchor[2])>.350001):raise ValueError('Original source bounds violated')
        cam=p['raw_camera']
        if cam!=published[(t['scene'],t['original_viewpoint_path'][0])]['camera_position']:raise ValueError('Original camera identity differs')
        if math.hypot(q[0]-cam[0],q[2]-cam[2])>=.5 or not 0<=cam[1]-q[1]<=2:raise ValueError('Original camera domain violated')
        if any(source.contact(v,v,certificate=True,arithmetic='rational_hull') for v in candidate['targets']):raise ValueError('Independent source body gate failed')
        z=[float(v) for v in pf.try_step(q,q)]
        if (not pf.is_navigable(z) or math.hypot(z[0]-q[0],z[2]-q[2])>pm['protocol']['horizontal_tolerance_m']
                or abs(z[1]-q[1])>pm['protocol']['maximum_vertical_transition_m']
                or not connected(q,z) or not connected(z,q)
                or source.contact(q,z,certificate=True,arithmetic='rational_hull')):raise ValueError('Independent initial filter gate failed')
        if not all(connected(a,b) and connected(b,a) for a,b in zip(candidate['targets'],candidate['targets'][1:])):raise ValueError('Reference connectivity failed')
        audit.append(dict(task_key=key,old_initial=t['targets'][0],new_initial=q,original_anchor=anchor,
                          displacement_from_current=math.dist(q,t['targets'][0]),displacement_from_anchor=math.dist(q,anchor),
                          source_proposal_sha256=content_digest(p),status='INDEPENDENT_STATIC_AND_INITIAL_FILTER_PASS_NOT_MOTION'))
    out.mkdir();entries=[];selections=[];counts=Counter();splits=Counter()
    with (out/'tasks.jsonl').open('xb') as stream:
        for key,t in tasks.items():
            if key in proposals:new=repaired_task(t,proposals[key],content_digest(sources))
            else:
                new=copy.deepcopy(t);new['module_source_sha256']=content_digest(sources)
                assert {k:v for k,v in new.items() if k!='module_source_sha256'}=={k:v for k,v in t.items() if k!='module_source_sha256'}
            raw=(json.dumps(new,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode();offset=stream.tell();stream.write(raw)
            entries.append(dict(task_key=key,dataset='landmark_rxr',offset=offset,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),cohort=new['cohort']))
            selections.append(dict(task_key=key,initial_changed=key in proposals,old_task_sha256=content_digest(t),new_task_sha256=content_digest(new)))
            counts[new['cohort']]+=1;splits[new['split']]+=1
    merkle,idx=merkle_index(entries);write_json(out/'index.json',idx);write_json(out/'selection741.json',selections);write_json(out/'input-proposal-audit.json',audit)
    config={**pm['config'],'max_workers':cfg['max_workers'],'total_cpu_budget_hours':cfg['total_cpu_budget_hours'],'expected':{'landmark_rxr':741},'scope':cfg['scope']}
    manifest={'status':'FROZEN_COMPLETE741_SCENE_WITH27_INITIAL_REPAIRS','created_at':timestamp(),'config':config,'protocol':pm['protocol'],
        'base_method':pm['base_method'],'sources':sources,'task_count':741,'datasets':{'landmark_rxr':741},'splits':dict(splits),
        'information_mapping_groups':dict(counts),'task_merkle_root':merkle,'tasks_file_sha256':digest(out/'tasks.jsonl'),'index_sha256':digest(out/'index.json'),
        'selection_sha256':digest(out/'selection741.json'),'input_audit_sha256':digest(out/'input-proposal-audit.json'),
        'changed_initials':27,'unchanged_controls':714,'held_records_in_scene':len(scene_keys&held),'global_denominator_retained':33954,
        'scope':cfg['scope'],'target_scope':pm['target_scope'],'official_action_sources':pm['official_action_sources'],
        'launchers':{str(p):digest(p) for p in [root/'oracleAdapter/run.py',root/'scripts/with_runtime.sh']},
        'parent_run':str(parent),'parent_manifest_sha256':digest(parent/'manifest.json'),'prior_full_charge_seconds':previous,
        'original_full_budget_hours':720,'full_development_budget_reserved_hours':24,'proposal_validation_sha256':digest(proposal_run/'validation.json')}
    validate_launchers(root,manifest);write_json(out/'manifest.json',manifest);freeze_sources(out,sources);return manifest


def run_with_review(case_root,manifest_path):
    root=Path(case_root).resolve();mp=owned_output(root,manifest_path);run=mp.parent;m=json.loads(mp.read_text())
    if (run/'controller-process.json').exists():raise ValueError('Existing scene run requires review, not restart')
    from oracle.research.full_run import run as execute
    if not execute(root,mp):raise RuntimeError('Scene run stopped; preserve all outcomes')
    from oracle.research.full_review import review
    from oracle.research.full_report import report
    review(root,run,run/'independent-full-review');report(root,run,run/'independent-full-review/validation.json',run/'grouped-report')
    old={r['task_key']:r for r in json.loads((Path(m['parent_run'])/'results-index.json').read_text())}
    new={r['task_key']:r for r in json.loads((run/'results-index.json').read_text())}
    selection=json.loads((run/'selection741.json').read_text());assert len(new)==741 and set(new)=={r['task_key'] for r in selection}
    result={};passed='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES'
    for label,changed in [('repaired_initials',True),('unchanged_controls',False)]:
        keys={r['task_key'] for r in selection if r['initial_changed']==changed};a={k for k in keys if old[k]['status']==passed};b={k for k in keys if new[k]['status']==passed}
        result[label]=dict(tasks=len(keys),old_pass=len(a),new_pass=len(b),recovered=sorted(b-a),regressed=sorted(a-b),retained_pass=len(a&b))
    independent=json.loads((run/'independent-full-review/validation.json').read_text())
    write_json(run/'scene-comparison.json',dict(status='COMPLETE741_SCENE_COMPARISON_NOT_GLOBAL_ACCEPTANCE',groups=result,
        actual_actions=independent['actual_actions'],replayed_actions=independent['independently_replayed_actions'],
        global_denominator=33954,all_global_gates_passed=False,manifest_sha256=digest(mp)))
    write_json(run/'review-complete.json',dict(status='COMPLETE741_WITH_INDEPENDENT_REVIEW_AND_COMPARISON',manifest_sha256=digest(mp),comparison_sha256=digest(run/'scene-comparison.json'),all_global_gates_passed=False))
    write_json(run/'state.json',dict(status='COMPLETE741_REVIEW',completed=741,expected=741,time=timestamp()),immutable=False)
