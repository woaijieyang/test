"""Revalidate historical bounded coordinates, never reuse historical PASS labels."""
from collections import Counter
import json,math,os,time
from pathlib import Path
from oracle.common.artifacts import digest,owned_output,write_json,package_sources,freeze_sources,runtime_identity
from oracle.common.offline_audit import identity
from oracle.verification.source_scene import SourceScene


def check_record_invariants(old,new):
    issues=[];allowed={'targets','mapping_methods'}
    if {k:v for k,v in old.items() if k not in allowed}!={k:v for k,v in new.items() if k not in allowed}:
        issues.append('non_mapping_field_changed')
    if len(old['targets'])!=len(new['targets']):issues.append('reference_count_changed')
    return issues


def check_choice_bounds(source,official_anchor,current,choice):
    issues=[]
    if official_anchor is not None:anchor=official_anchor;kind='official_reference_node'
    elif source['method']!='UNRESOLVED_no_direct_identity':anchor=source['position'];kind=source['method']
    else:anchor=current;kind='bounded_camera_projection'
    if anchor is None:return ['unresolved_source_anchor']
    q=choice['position'];rank=choice['rank']
    if choice['anchor']!=anchor or choice['anchor_kind']!=kind:issues.append('source_anchor_identity')
    if type(rank) is not int or rank not in (0,2,3):issues.append('unverified_extra_seed')
    if len(q)!=3 or not all(math.isfinite(v) for v in q):return issues+['nonfinite_position']
    delta=math.dist(q,anchor)
    if delta>.5:issues.append('source_sphere_bound')
    if not math.isclose(delta,choice['displacement'],rel_tol=0,abs_tol=1e-10):issues.append('source_displacement_binding')
    if rank>=3 and math.hypot(q[0]-anchor[0],q[2]-anchor[2])>.350001:issues.append('extra_horizontal_bound')
    if kind=='bounded_camera_projection':
        cam=source['camera_position']
        if math.hypot(q[0]-cam[0],q[2]-cam[2])>=.5 or not 0<=cam[1]-q[1]<=2:issues.append('camera_bound')
    return issues


def audit(case_root,output,cpu):
    started=time.perf_counter();root=Path(case_root).resolve();output=owned_output(root,output);package,sources=package_sources()
    if output.exists():raise FileExistsError(output)
    if cpu not in sorted(os.sched_getaffinity(0))[:64]:raise ValueError('CPU outside allowed64')
    os.sched_setaffinity(0,{cpu});os.nice(15);os.environ['CUDA_VISIBLE_DEVICES']=''
    import habitat_sim
    cfg_path=package/'configs/experiments/existing_bounded_mapping_audit_v1.json';cfg=json.loads(cfg_path.read_text())
    prior=root/cfg['producer'];paths={k:root/v['path'] for k,v in cfg['inputs'].items()}
    for k,p in paths.items():
        if digest(p)!=cfg['inputs'][k]['sha256']:raise ValueError('Historical source changed: '+k)
    producer=json.loads(paths['producer_validation'].read_text());old_audit=json.loads(paths['historical_audit'].read_text())
    if old_audit['input_sha256']!=digest(paths['producer_validation']) or old_audit['candidate_tasks_sha256']!=digest(paths['candidate_tasks']):raise ValueError('Historical chain differs')
    if producer['extra_seeds_path'] is not None:raise ValueError('Extra seed identity not supported by this fixed reuse audit')
    parent_path=root/'outputs/landmark-connectivity/full-native-v11/manifest.json';parent=json.loads(parent_path.read_text())
    if digest(parent_path)!=producer['parent_manifest_sha256'] or parent['profile_sha256']!=producer['profile_sha256']:raise ValueError('Reuse is not same frozen parent/profile')
    scene=producer['scene'];old={t['task_key']:t for t in parent['tasks'] if t['scene']==scene}
    proposed_list=json.loads(paths['candidate_tasks'].read_text())['tasks'];proposed={t['task_key']:t for t in proposed_list}
    states={r['task_key']:r for r in producer['rows']}
    if len(proposed_list)!=len(proposed) or set(proposed)!=set(old) or set(states)!=set(old) or len(old)!=cfg['expected_scene_tasks']:raise ValueError('Full scene task coverage differs')
    identity_path=root/'outputs/landmark-connectivity/published-identity-nodes.json'
    native_path=root/'outputs/landmark-connectivity/native-mapping.json'
    if digest(identity_path)!=old_audit['published_identity_sha256'] or digest(native_path)!=old_audit['native_mapping_sha256']:raise ValueError('Source node identity changed')
    identities={(r['scene'],r['node']):r for r in json.loads(identity_path.read_text())['nodes']}
    official={(r['scene'],r['node']):r['native_candidates'][0] for r in json.loads(native_path.read_text())['nodes']}
    profile_path=Path(parent['profile_path'])
    if digest(profile_path)!=parent['profile_sha256']:raise ValueError('Profile changed')
    asset=json.loads(profile_path.read_text())['assets'][f'mp3d/{scene}/{scene}.glb']
    if digest(asset['navmesh_path'])!=asset['navmesh_sha256']:raise ValueError('Native mesh changed')
    geometry_path=Path(producer['native_geometry_receipt_path'])
    if digest(geometry_path)!=producer['native_geometry_receipt_sha256']:raise ValueError('Geometry receipt changed')
    protocol_path=package/'configs/protocols/current_linear.json';protocol=json.loads(protocol_path.read_text())
    source=SourceScene(geometry_path,digest(geometry_path),protocol)
    pf=habitat_sim.PathFinder()
    if not pf.load_nav_mesh(asset['navmesh_path']):raise ValueError('Native mesh load failed')
    lineage={r['task_key']:r for r in json.loads(paths['strict_lineage'].read_text())}
    output.mkdir();freeze_sources(output,sources);rows=[];source_checks={};origin_checks={};paths_checked={}
    rings=[(radius*math.cos(i*2*math.pi/n),radius*math.sin(i*2*math.pi/n))
        for radius,n in ((.1,18),(.15,30),(.2,36),(.25,48),(.3,60),(.35,72)) for i in range(n)]
    for key,t in sorted(old.items()):
        new=proposed[key];row=states[key];issues=check_record_invariants(t,new)
        offered=row['status']=='SOURCE_CLEAR_TARGETS_COMMON_COMPONENT_PENDING_MOTION'
        contacts=[]
        if offered:
            if len(row['choices'])!=len(t['targets']):raise ValueError('Source choice coverage differs')
            for node,current,q,choice in zip(t['original_viewpoint_path'],t['targets'],new['targets'],row['choices']):
                src=identities[(scene,node)];anchor=official.get((scene,node))
                issues.extend(check_choice_bounds(src,anchor,current,choice))
                if q!=choice['position']:issues.append('target_choice_binding')
                if not pf.is_navigable(q) or math.dist(q,list(pf.snap_point(q)))>1e-5:issues.append('native_point_membership')
                origin_key=(node,choice['rank'],tuple(choice['anchor']),tuple(q))
                if origin_key not in origin_checks:
                    if choice['rank']==0:seeds=[current]
                    elif choice['rank']==2:seeds=[choice['anchor']]
                    elif choice['rank']==3:
                        a=choice['anchor'];seeds=[[a[0]+dx,a[1],a[2]+dz] for dx,dz in rings]
                    else:seeds=[]
                    origin_checks[origin_key]=any(seed is not None and math.dist(q,list(pf.snap_point(seed)))<=1e-5 for seed in seeds)
                if not origin_checks[origin_key]:issues.append('not_from_frozen_seed_family')
                qkey=tuple(q)
                if qkey not in source_checks:source_checks[qkey]=source.contact(q,q,arithmetic='rational_hull')
                if source_checks[qkey]:issues.append('independent_source_contact');contacts.append(source_checks[qkey])
            for a,b in zip(new['targets'],new['targets'][1:]):
                for start,end in ((a,b),(b,a)):
                    pkey=(tuple(start),tuple(end))
                    if pkey not in paths_checked:
                        path=habitat_sim.ShortestPath();path.requested_start=start;path.requested_end=end
                        paths_checked[pkey]=bool(pf.find_path(path) and math.isfinite(path.geodesic_distance))
                    if not paths_checked[pkey]:issues.append('native_adjacency_disconnected')
        elif new!=t:issues.append('unresolved_record_changed')
        passed=offered and not issues
        rows.append(dict(task_key=key,status='PASS_REUSED_PROPOSAL_RATIONAL_STATIC_NOT_MOTION' if passed else 'AUDIT_FAILED_PRESERVED' if issues else 'UNRESOLVED_ORIGINAL_PRESERVED',
            issues=sorted(set(issues)),source_contacts=contacts,proposed_targets=new['targets'] if passed else None,
            source_choices=row.get('choices') if passed else None,old_targets=t['targets'],
            raw_source_record_sha256=t['source_record_sha256'],original_heading=t['heading'],
            current_endpoint_source_gate=lineage[key]['failure_explanation']['endpoint_source_gate'],
            potential_strict_endpoint_repair=passed and not lineage[key]['failure_explanation']['endpoint_source_gate'],
            current_receipt_sha256=lineage[key]['receipt_sha256'],adopted=False,native_movement_actions=0))
    write_json(output/'records.json',rows)
    startup=identity();startup.update(method_category='historical_source_bounded_proposal_revalidation',
        task_contract='All frozen scene records, source identities and headings retained; no copied motion PASS',
        privileged_information=['published_same_ID_nodes','official_ordinal_reference_nodes','native_navmesh','source_geometry'],
        environment_limit='Protected native point/path and rational geometry checks only; no movement execution')
    result=dict(status='COMPLETE_SAME_PROFILE_PROPOSAL_REVALIDATION_NOT_MOTION',startup=startup,scene=scene,
        full_scene_records=len(rows),global_landmark_denominator=33954,counts=dict(Counter(r['status'] for r in rows)),
        potential_strict_endpoint_repair=sum(r['potential_strict_endpoint_repair'] for r in rows),
        independent_source_points=len(source_checks),independent_directed_edges=len(paths_checked),
        source_hashes={k:digest(p) for k,p in paths.items()},parent_manifest_sha256=digest(parent_path),
        profile_sha256=parent['profile_sha256'],native_geometry_sha256=source.geometry_sha256,
        configuration_sha256=digest(cfg_path),records_sha256=digest(output/'records.json'),
        native_environment=runtime_identity(),native_movement_actions=0,wall_seconds=time.perf_counter()-started,
        limits='Existing same-profile proposal coordinates only; freshly recomputed static gates do not prove uninterrupted motion or recovery. Other scenes andheld114 remain unresolved; no original assets modified.')
    write_json(output/'validation.json',result);return result
