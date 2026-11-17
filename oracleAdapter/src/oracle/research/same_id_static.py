"""Finite same-ID coordinate seeds, without adopting labels or claiming routes."""
import json,math,os,time,signal
from collections import defaultdict,Counter
from pathlib import Path
from oracle.common.artifacts import content_digest,digest,owned_output,write_json,package_sources,freeze_sources,runtime_identity,timestamp
from oracle.research.full_worker import process_identity
from oracle.adapters.habitat.assets import resolve
from oracle.adapters.landmark_rxr.source_bounded_candidates import collect_candidates,choose_common_component
from oracle.verification.source_scene import SourceScene
from oracle.planners.collision_queries import CachedSourceQueries

PASS='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES'


def validate_seed_source(target,index,seed,source,outcome):
    i=seed['source_reference_index']
    if type(i) is not int or not 0<=i<len(source['targets']):raise ValueError('Invalid source occurrence')
    if (source['task_key']!=seed['source_task_key'] or source['scene']!=target['scene']
            or source['profile_sha256']!=target['profile_sha256']
            or source['geometry_catalog_sha256']!=target['geometry_catalog_sha256']
            or source['original_viewpoint_path'][i]!=target['original_viewpoint_path'][index]
            or source['targets'][i]!=seed['position'] or outcome['receipt_sha256']!=seed['source_receipt_sha256']):
        raise ValueError('Same-ID coordinate provenance mismatch')
    if seed['origin']=='preserved_current_target_NOT_success_prior':
        if source['task_key']!=target['task_key'] or i!=index:raise ValueError('Current position cannot masquerade as another source')
    elif seed['origin']=='strict_success_same_id_prior':
        if outcome['status']!=PASS:raise ValueError('Donor lacks strict acceptance')
    else:raise ValueError('Unknown seed provenance')


def run(case_root,output,cpu):
    import resource
    if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
    root=Path(case_root).resolve();out=owned_output(root,output);package,sources=package_sources()
    cfg=json.loads((package/'configs/experiments/same_id_static_v1.json').read_text())
    budget_path=root/cfg['budget_admission'];budget=json.loads(budget_path.read_text())
    if digest(budget_path)!=cfg['budget_admission_sha256']:raise ValueError('Budget reservation identity changed')
    if (budget['legacy_development_charge_seconds']+budget['next_stage_reservation_seconds']+cfg['cpu_reservation_seconds']>budget['development_limit_seconds']
            or budget['overall_including_next_stage_reservation_seconds']+cfg['cpu_reservation_seconds']>budget['overall_limit_seconds']):
        raise ValueError('Original budget would be exceeded even retaining the previous full reservation')
    if cpu not in sorted(os.sched_getaffinity(0))[:64]:raise ValueError('CPU outside authorized64')
    os.sched_setaffinity(0,{cpu});os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
    resource.setrlimit(resource.RLIMIT_CPU,(895,900))
    def expired(*_):raise TimeoutError('Fixed static probe wall allocation')
    signal.signal(signal.SIGALRM,expired);signal.alarm(895)
    parent=root/cfg['parent_run'];m=json.loads((parent/'manifest.json').read_text())
    if digest(parent/'manifest.json')!=cfg['parent_manifest_sha256'] or json.loads((parent/'source-freeze.json').read_text())['status']!='CLOSED':raise ValueError('Frozen parent differs or is live')
    inp=root/cfg['input_records'];assert digest(inp)==cfg['input_sha256'];rows=json.loads(inp.read_text())
    selected=[r for r in rows if r['all_nodes_bounds_eligible'] and r['has_changed_candidate']]
    if len(rows)!=153 or len(selected)!=69:raise ValueError('Frozen153/69 scope changed')
    assert digest(parent/'index.json')==m['index_sha256']
    index={r['record']['task_key']:r['record'] for r in json.loads((parent/'index.json').read_text())}
    pv=json.loads((parent/'validation.json').read_text());assert digest(parent/'results-index.json')==pv['results_index_sha256']
    outcomes={r['task_key']:r for r in json.loads((parent/'results-index.json').read_text())}
    assert len(index)==len(outcomes)==33954 and set(index)==set(outcomes)
    policy=json.loads((package/'configs/experiments/global_bounded_mapping_v1.json').read_text())
    for k in ['native','published']:
        if digest(root/policy['inputs'][k]['path'])!=policy['inputs'][k]['sha256']:raise ValueError('Original anchor source changed')
    nr=json.loads((root/policy['inputs']['native']['path']).read_text())['nodes']
    if any(len(x['native_candidates'])!=1 for x in nr):raise ValueError('Ambiguous official anchor')
    native={(x['scene'],x['node']):x['native_candidates'][0] for x in nr}
    published={(x['scene'],x['node']):x for x in json.loads((root/policy['inputs']['published']['path']).read_text())['nodes']}
    held=set(json.loads((root/'outputs/landmark-connectivity/constraint-blockers.json').read_text())['task_keys'])
    if any(r['task_key'] in held for r in rows):raise ValueError('Held114 cannot enter proposals')
    cache={};stream=(parent/'tasks.jsonl').open('rb')
    def task(key):
        if key not in cache:
            e=index[key];stream.seek(e['offset']);raw=stream.read(e['bytes'])
            if __import__('hashlib').sha256(raw).hexdigest()!=e['sha256']:raise ValueError('Actual task bytes changed')
            cache[key]=json.loads(raw)
        return cache[key]
    groups=defaultdict(list)
    for r in selected:
        t=task(r['task_key'])
        if t['scene']!=r['scene'] or outcomes[t['task_key']]['failure']!='topology_mapping_error':raise ValueError('Selected target category changed')
        for node in r['nodes']:
            i=node['reference_index'];assert node['current']==t['targets'][i] and node['node_id']==t['original_viewpoint_path'][i]
            for seed in node['eligible']:validate_seed_source(t,i,seed,task(seed['source_task_key']),outcomes[seed['source_task_key']])
        groups[t['scene']].append(r)
    out.mkdir();freeze_sources(out,sources);write_json(out/'controller-process.json',process_identity());write_json(out/'source-freeze.json',dict(status='OPEN'))
    started=time.perf_counter();counts=Counter();results=[];query_counts=Counter()
    try:
        import habitat_sim
        for scene,group in sorted(groups.items()):
            asset,geometry=resolve(root,task(group[0]['task_key']));pf=habitat_sim.PathFinder()
            if not pf.load_nav_mesh(asset['navmesh_path']):raise RuntimeError('Frozen mesh load failed')
            source=SourceScene(geometry['receipt_path'],geometry['receipt_sha256'],m['protocol'],catalog=geometry)
            body=CachedSourceQueries(source,context_digest=content_digest([sources,cfg,scene,m['protocol']]),**cfg['query_cache'])
            reps=[];labels={};body_failures={}
            def connected(a,b):
                query_counts['path']+=1;p=habitat_sim.ShortestPath();p.requested_start=a;p.requested_end=b
                return bool(pf.find_path(p) and math.isfinite(p.geodesic_distance))
            def component(q):
                key=tuple(q)
                if key not in labels:
                    label=next((i for i,p in enumerate(reps) if connected(q,p) and connected(p,q)),None)
                    if label is None:label=len(reps);reps.append(q)
                    labels[key]=label
                return labels[key]
            def contact(q):
                f=body.contact(q,q,certificate=True);r=body.contact(q,q,certificate=True,arithmetic='rational_hull')
                if bool(f)!=bool(r):raise ValueError('Float/rational body disagreement; no checker shopping')
                if r:body_failures[content_digest(q)]={'point':q,'contact':r}
                return r
            def snap(q):query_counts['snap']+=1;return pf.snap_point(q)
            for row in sorted(group,key=lambda x:x['task_key']):
                t=task(row['task_key']);base=[];aug=[];details=[]
                for n in row['nodes']:
                    node=n['node_id'];ident=published[(scene,node)];cur=n['current']
                    if (scene,node) in native:anchor=native[(scene,node)];kind='official_reference_node'
                    elif ident['method']!='UNRESOLVED_no_direct_identity':anchor=ident['position'];kind=ident['method']
                    else:anchor=cur;kind='bounded_camera_projection'
                    if anchor!=n['anchor'] or kind!=n['anchor_kind']:raise ValueError('Numerical source-bound anchor changed')
                    args=dict(anchor=anchor,anchor_kind=kind,camera=ident['camera_position'],current=cur,offsets=[],
                              snap=snap,navigable=pf.is_navigable,contact=contact,component=component,sphere_m=.5,extra_horizontal_m=.350001)
                    before=collect_candidates(**args)
                    seeds=sorted({tuple(x['position']) for x in n['eligible'] if x['origin']=='strict_success_same_id_prior'})
                    after=collect_candidates(**args,extra_seed_points=seeds)
                    base.append(before['options']);aug.append(after['options'])
                    details.append({'reference_index':n['reference_index'],'node_id':node,'source_seeds':n['eligible'],
                                    'base':before,'augmented':after})
                control=choose_common_component(base);choice=choose_common_component(aug)
                points=[x['position'] for x in choice['choices']] if choice else None
                if points is not None and not all(connected(a,b) and connected(b,a) for a,b in zip(points,points[1:])):raise ValueError('Common component did not preserve every adjacent connection')
                status='SAME_ID_PROPOSAL_PENDING_INDEPENDENT_AUDIT' if choice else 'NO_COMMON_COMPONENT_FIXED_CANDIDATES'
                counts[status]+=1;counts['base_control_common_component']+=int(control is not None)
                result=dict(task_key=t['task_key'],scene=scene,status=status,base_common_component=control is not None,
                            old_targets=t['targets'],proposed_targets=points,original_heading=t['raw_heading'],
                            choices=choice['choices'] if choice else None,node_details=details,adopted=False,native_actions=0)
                write_json(out/'tasks'/f"{t['task_key'].replace(':','-')}.json",result)
                results.append({k:result[k] for k in ['task_key','scene','status','base_common_component','adopted','native_actions']})
            write_json(out/'scenes'/f'{scene}.json',dict(components=len(reps),body_rejection_witnesses=body_failures,cache_metrics=body.metrics))
            del pf,source,body
        for row in rows:
            if not row['all_nodes_bounds_eligible'] or not row['has_changed_candidate']:
                results.append(dict(task_key=row['task_key'],scene=row['scene'],status='NUMERICAL_BOUND_FAILURE_PRESERVED_NOT_NATIVE_QUERIED',adopted=False,native_actions=0))
        assert len(results)==153 and len({x['task_key'] for x in results})==153
        write_json(out/'records153.json',results)
        result=dict(status='COMPLETE_FIXED_SAME_ID_STATIC_DIAGNOSTIC_NOT_MAPPING_ACCEPTANCE',time=timestamp(),
                    scope_records=153,native_queried_tasks=69,global_denominator=33954,held114_changed=False,
                    counts=dict(counts),query_counts=dict(query_counts),native_actions=0,adopted_mappings=0,
                    wall_seconds=time.perf_counter()-started,process_cpu_seconds=time.process_time(),native_environment=runtime_identity(),
                    cpu_reservation_seconds=cfg['cpu_reservation_seconds'],budget_admission_sha256=digest(budget_path),
                    parent_manifest_sha256=digest(parent/'manifest.json'),input_sha256=digest(inp),records_sha256=digest(out/'records153.json'),
                    limits='Same-ID candidate seeds, old snap/bounds/body admission, no rings or grid changes. A static common component is not uninterrupted executable motion. Positive proposals require independent audit and fresh real execution/replay; no copiedPASS.')
        write_json(out/'validation.json',result);return result
    except BaseException as error:
        write_json(out/'failure.json',dict(error=repr(error),completed_records=len(results),time=timestamp()));raise
    finally:
        stream.close();signal.alarm(0);write_json(out/'source-freeze.json',dict(status='CLOSED',live_phase_receipts=[]),immutable=False)
