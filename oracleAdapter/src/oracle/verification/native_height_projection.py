"""Fixed finite PathFinder queries; no executed route or modified annotation."""
import json,math,os,signal,time
from pathlib import Path
from oracle.common.artifacts import digest,owned_output,write_json,package_sources,freeze_sources,runtime_identity
from oracle.verification.source_scene import SourceScene


def source_bound(point,original,anchor):
    return math.dist(point,anchor)<=.5 and (point==original or math.hypot(point[0]-anchor[0],point[2]-anchor[2])<=.350001)


def bounded_projection(initial,step,limit):
    if type(limit) is not int or not 1<=limit<=3:raise ValueError('Only declared1-3queries supported')
    current=list(initial);steps=[]
    for _ in range(limit):
        raw=[float(v) for v in step(current)]
        finite=len(raw)==3 and all(math.isfinite(v) for v in raw)
        steps.append({'before':current,'after':[v if math.isfinite(v) else None for v in raw]})
        if not finite:return dict(position=None,fixed=False,steps=steps,failure='nonfinite_native_query')
        if raw==current:return dict(position=raw,fixed=True,steps=steps,failure=None)
        current=raw
    return dict(position=current,fixed=False,steps=steps,failure='fixed_point_not_reached_within_bound')


def run(case_root,output):
    import resource,psutil
    if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
    os.environ['CUDA_VISIBLE_DEVICES']=''
    import habitat_sim
    root=Path(case_root).resolve();out=owned_output(root,output);package,sources=package_sources()
    cfg=json.loads((package/'configs/experiments/native_height_projection_v1.json').read_text())
    budget_path=root/cfg['budget_admission'];assert digest(budget_path)==cfg['budget_sha256'];budget=json.loads(budget_path.read_text())
    assert budget['development_after_new_reservation_seconds']+240+600<=86400
    assert budget['overall_after_new_reservation_seconds']+240+600<=2592000
    resource.setrlimit(resource.RLIMIT_CPU,(599,600))
    def expired(*_):raise TimeoutError('Fixed600second wall cap')
    signal.signal(signal.SIGALRM,expired);signal.alarm(600)
    usage=psutil.cpu_percent(interval=1,percpu=True);idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i]<15]
    if not idle:raise RuntimeError('No idle CPU; no query launched')
    cpu=min(idle,key=lambda i:usage[i]);os.sched_setaffinity(0,{cpu});os.nice(15)
    parent=root/cfg['parent'];assert digest(parent/'manifest.json')==cfg['parent_manifest_sha256'];m=json.loads((parent/'manifest.json').read_text())
    spec=root/cfg['contacts'];audit=json.loads(spec.read_text());assert audit['records']==61 and audit['examined_occurrences']==209
    policy=json.loads((package/'configs/experiments/global_bounded_mapping_v1.json').read_text())
    data={}
    for key in ('native','published','catalog','held'):
        p=root/policy['inputs'][key]['path'];assert digest(p)==policy['inputs'][key]['sha256'];data[key]=json.loads(p.read_text())
    native={(x['scene'],x['node']):x['native_candidates'] for x in data['native']['nodes']}
    published={(x['scene'],x['node']):x for x in data['published']['nodes']}
    catalog={x['scene']:x for x in data['catalog']['scenes']}
    attribution_path=root/cfg['attribution'];records={x['task_key']:x for x in json.loads(attribution_path.read_text())}
    assert len(records)==209 and not set(records)&set(data['held']['task_keys'])
    pp=root/cfg['profile'];assert digest(pp)==cfg['profile_sha256'];profile=json.loads(pp.read_text())
    out.mkdir();freeze_sources(out,sources);started=time.process_time();reports=[];queries=0
    write_json(out/'manifest.json',dict(config=cfg,sources=sources,cpu=cpu,environment=runtime_identity(),
        contacts_sha256=digest(spec),attribution_sha256=digest(attribution_path),protocol=m['protocol']))
    for scene in sorted({x['scene'] for x in audit['reports']}):
        geo=catalog[scene];source=SourceScene(geo['receipt_path'],geo['receipt_sha256'],m['protocol'],catalog=geo)
        asset=profile['assets']['mp3d/'+scene+'/'+scene+'.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256']
        pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path'])
        for item in [x for x in audit['reports'] if x['scene']==scene]:
            before=item['foot'];rec=records[item['task_key']];proposal=Path(rec['proposal']);assert digest(proposal)==rec['proposal_sha256']
            pr=json.loads(proposal.read_text());i=item['reference_index'];assert pr['old_targets'][i]==before;node=pr['original_viewpoint_path'][i]
            identity=published[(scene,node)];kind=identity['method']
            if (scene,node) in native:
                assert len(native[(scene,node)])==1;anchor=native[(scene,node)][0];kind='official_reference_node'
            elif kind!='UNRESOLVED_no_direct_identity':anchor=identity['position']
            else:anchor=before;kind='bounded_camera_projection'
            probe=bounded_projection(before,lambda p:pf.try_step(p,p),cfg['maximum_zero_step_queries']);queries+=len(probe['steps']);q=probe['position']
            report=dict(scene=scene,node=node,task_key=item['task_key'],original=before,probe=probe,source_anchor=anchor,anchor_kind=kind,
                covered_occurrences=item['covered_occurrences'],adopted=False,all_point_checks=False)
            if q is not None:
                snap=[float(v) for v in pf.snap_point(q)];queries+=1
                floating=source.contact(q,q,certificate=True);rational=source.contact(q,q,arithmetic='rational_hull')
                path=habitat_sim.ShortestPath();path.requested_start=before;path.requested_end=q;linked=bool(pf.find_path(path) and math.isfinite(path.geodesic_distance));queries+=1
                bound=source_bound(q,before,anchor)
                camera=identity['camera_position']
                if kind=='bounded_camera_projection':bound=bound and math.hypot(q[0]-camera[0],q[2]-camera[2])<.5 and 0<=camera[1]-q[1]<=2
                checks=dict(navigable=bool(pf.is_navigable(q)),snap_fixed=all(math.isfinite(v) for v in snap) and math.dist(q,snap)<=1e-5,
                    zero_step_fixed=probe['fixed'],float_clear=floating is None,rational_clear=rational is None,same_component=linked,source_bound=bound)
                report.update(checks=checks,all_point_checks=all(checks.values()),delta_y=q[1]-before[1],displacement_m=math.dist(q,before),
                    snap=snap,float_contact=floating,rational_contact=rational,
                    source_bound_class='preserved_current_rank0' if q==before else 'new_extra_seed')
            reports.append(report)
    result=dict(status='COMPLETE61_NATIVE_HEIGHT_QUERY_DIAGNOSTIC_NOT_MOVEMENT',records=len(reports),occurrences=209,queries=queries,
        point_check_passes=sum(x['all_point_checks'] for x in reports),covered_occurrences_with_point_pass=sum(len(x['covered_occurrences']) for x in reports if x['all_point_checks']),
        whole_route_passes=0,native_movement_actions=0,targets_modified=0,reserved_cpu_seconds=600,process_cpu_seconds=time.process_time()-started,
        manifest_sha256=digest(out/'manifest.json'),reports=reports)
    assert len(reports)==61;write_json(out/'validation.json',result);signal.alarm(0);return result
