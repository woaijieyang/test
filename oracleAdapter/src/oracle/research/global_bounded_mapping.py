"""Global fixed-profile/body-aware proposals; preserve every original task.

The frozen legacy seed family is reused without parameter search. Existing
same-profile D7 evidence is referenced instead of resampling that scene.
"""
from collections import Counter,defaultdict
import gc,json,math,os,time
from pathlib import Path
from oracle.common.artifacts import digest,content_digest,owned_output,write_json,package_sources,freeze_sources,runtime_identity
from oracle.common.offline_audit import identity
from oracle.verification.source_scene import SourceScene
from oracle.planners.collision_queries import CachedSourceQueries
from oracle.adapters.landmark_rxr.source_bounded_candidates import collect_candidates,choose_common_component


def prepare(case_root,output,cpu):
    started=time.perf_counter();root=Path(case_root).resolve();output=owned_output(root,output);package,sources=package_sources()
    if output.exists():raise FileExistsError(output)
    if cpu not in sorted(os.sched_getaffinity(0))[:64]:raise ValueError('CPU outside64')
    os.sched_setaffinity(0,{cpu});os.nice(15);os.environ['CUDA_VISIBLE_DEVICES']=''
    import habitat_sim
    cfg_path=package/'configs/experiments/global_bounded_mapping_v1.json';cfg=json.loads(cfg_path.read_text())
    paths={k:root/v['path'] for k,v in cfg['inputs'].items()}
    for k,p in paths.items():
        if digest(p)!=cfg['inputs'][k]['sha256']:raise ValueError('Source changed: '+k)
    parent=json.loads(paths['parent'].read_text());tasks={t['task_key']:t for t in parent['tasks']}
    blocked={r['task_key'] for r in json.loads(paths['blockers'].read_text())};held=set(json.loads(paths['held'].read_text())['task_keys'])
    if len(tasks)!=33954 or len(blocked)!=6274 or len(held)!=114 or not held<=blocked<=set(tasks):raise ValueError('Full frozen coverage differs')
    published={(r['scene'],r['node']):r for r in json.loads(paths['published'].read_text())['nodes']}
    native={}
    for r in json.loads(paths['native'].read_text())['nodes']:
        if len(r['native_candidates'])!=1:raise ValueError('Official node source is not unique')
        native[(r['scene'],r['node'])]=r['native_candidates'][0]
    catalog={r['scene']:r for r in json.loads(paths['catalog'].read_text())['scenes']}
    d7=json.loads(paths['D7_audit'].read_text());d7_records_path=paths['D7_audit'].parent/'records.json'
    if digest(d7_records_path)!=d7['records_sha256']:raise ValueError('Revalidated D7 records changed')
    d7_rows={r['task_key']:r for r in json.loads(d7_records_path.read_text())}
    if d7['profile_sha256']!=parent['profile_sha256']:raise ValueError('D7 reuse profile differs')
    profile_path=Path(parent['profile_path'])
    if digest(profile_path)!=parent['profile_sha256']:raise ValueError('Profile changed')
    profile=json.loads(profile_path.read_text());protocol_path=package/'configs/protocols/current_linear.json';protocol=json.loads(protocol_path.read_text())
    groups=defaultdict(list)
    for key in sorted(blocked-held):groups[tasks[key]['scene']].append(key)
    output.mkdir();freeze_sources(output,sources)
    process={'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':cpu}
    write_json(output/'controller-process.json',process)
    write_json(output/'source-freeze.json',{'status':'OPEN','source_digest':content_digest(sources)})
    write_json(output/'state.json',{'status':'RUNNING_STATIC_PROPOSALS','processed_blockers':114,'expected_blockers':6274})
    results={k:dict(task_key=k,status='HELD114_ORIGINAL_AND_FAILURE_PRESERVED',proposed_targets=None,adopted=False) for k in held}
    offsets=[(radius*math.cos(i*2*math.pi/n),radius*math.sin(i*2*math.pi/n)) for radius,n in cfg['rings'] for i in range(n)]
    query_counts=Counter();all_rejections=Counter()
    for scene,keys in sorted(groups.items()):
        if scene==d7['scene']:
            for key in keys:
                r=d7_rows[key];t=tasks[key]
                if r['old_targets']!=t['targets'] or r['raw_source_record_sha256']!=t['source_record_sha256']:raise ValueError('Reused D7 task changed')
                passed=r['status']=='PASS_REUSED_PROPOSAL_RATIONAL_STATIC_NOT_MOTION'
                rec=dict(task_key=key,scene=scene,status='REUSED_REVALIDATED_STATIC_PROPOSAL_PENDING_MOTION' if passed else 'REUSED_UNRESOLVED_SOURCE_FAMILY_NEGATIVE_NOT_RESEARCHED',
                    proposed_targets=r['proposed_targets'] if passed else None,choices=r['source_choices'] if passed else None,
                    old_targets=t['targets'],original_heading=t['heading'],legacy_source_record_sha256=t['source_record_sha256'],
                    reuse_source_sha256=digest(paths['D7_audit']),adopted=False,native_movement_actions=0)
                results[key]=rec;write_json(output/'tasks'/f"{key.replace(':','-')}.json",rec)
            continue
        geometry=catalog[scene];asset=profile['assets'][f'mp3d/{scene}/{scene}.glb']
        if digest(asset['navmesh_path'])!=asset['navmesh_sha256']:raise ValueError('Navmesh changed')
        pf=habitat_sim.PathFinder()
        if not pf.load_nav_mesh(asset['navmesh_path']):raise ValueError('Native mesh load failed')
        source=SourceScene(geometry['receipt_path'],geometry['receipt_sha256'],protocol,catalog=geometry)
        body=CachedSourceQueries(source,context_digest=content_digest([cfg,sources,scene,parent['profile_sha256']]),**cfg['query_cache'])
        representatives=[];component_cache={};base_cache={};expanded_cache={};camera_cache={}
        def connected(a,b):
            query_counts['path']+=1;p=habitat_sim.ShortestPath();p.requested_start=a;p.requested_end=b
            return bool(pf.find_path(p) and math.isfinite(p.geodesic_distance))
        def component(p):
            key=tuple(p)
            if key in component_cache:return component_cache[key]
            for i,r in enumerate(representatives):
                if connected(p,r) and connected(r,p):component_cache[key]=i;return i
            i=len(representatives);representatives.append(p);component_cache[key]=i;return i
        def snap(p):query_counts['snap']+=1;return pf.snap_point(p)
        def camera_anchor(node,cam):
            if node not in camera_cache:
                candidates=[]
                for i in range(101):
                    p=list(snap([cam[0],cam[1]-.02*i,cam[2]]))
                    if not all(math.isfinite(v) for v in p) or not pf.is_navigable(p):continue
                    horizontal=math.hypot(p[0]-cam[0],p[2]-cam[2]);drop=cam[1]-p[1]
                    if horizontal<.5 and 0<=drop<=2 and math.dist(p,list(snap(p)))<=1e-5:candidates.append((horizontal,-drop,p))
                camera_cache[node]=min(candidates)[2] if candidates else None
            return camera_cache[node]
        def options(node,current,expanded):
            identity=published[(scene,node)]
            if (scene,node) in native:anchor=native[(scene,node)];kind='official_reference_node'
            elif identity['method']!='UNRESOLVED_no_direct_identity':anchor=identity['position'];kind=identity['method']
            else:anchor=current if current is not None else camera_anchor(node,identity['camera_position']);kind='bounded_camera_projection'
            key=(node,None if current is None else tuple(current),None if anchor is None else tuple(anchor),kind)
            cache=expanded_cache if expanded else base_cache
            if key not in cache:
                value=collect_candidates(anchor=anchor,anchor_kind=kind,camera=identity['camera_position'],current=current,
                    offsets=offsets if expanded else [],snap=snap,navigable=pf.is_navigable,contact=lambda p:body.contact(p,p),
                    component=component,sphere_m=.5,extra_horizontal_m=.350001)
                cache[key]=value;all_rejections.update(value['rejections'])
            return cache[key]
        for key in keys:
            if time.perf_counter()-started>cfg['wall_seconds_cap']:raise RuntimeError('Fixed global static proposal wall cap exceeded; partial evidence preserved')
            t=tasks[key];node_ids=t['original_viewpoint_path']
            base_options=[options(node,p,False) for node,p in zip(node_ids,t['targets'])]
            choice=choose_common_component([r['options'] for r in base_options]);expanded=False
            if choice is None:
                expanded=True;base_options=[options(node,p,True) for node,p in zip(node_ids,t['targets'])]
                choice=choose_common_component([r['options'] for r in base_options])
            points=[r['position'] for r in choice['choices']] if choice else None
            if points is not None and not all(connected(a,b) for a,b in zip(points,points[1:])):raise ValueError('Joint choice disconnected')
            rec=dict(task_key=key,scene=scene,status='SOURCE_BOUNDED_BODY_AWARE_PROPOSAL_PENDING_INDEPENDENT_AUDIT' if points is not None else 'UNRESOLVED_FIXED_SOURCE_FAMILY_PRESERVED',
                old_targets=t['targets'],proposed_targets=points,choices=choice['choices'] if choice else None,
                original_heading=t['heading'],legacy_source_record_sha256=t['source_record_sha256'],
                original_viewpoint_path=node_ids,expanded_fixed_rings=expanded,
                per_reference_component_counts=[len(r['options']) for r in base_options],
                missing_candidate_indices=[i for i,r in enumerate(base_options) if not r['options']],
                profile_sha256=parent['profile_sha256'],native_geometry_sha256=source.geometry_sha256,
                adopted=False,native_movement_actions=0)
            results[key]=rec;write_json(output/'tasks'/f"{key.replace(':','-')}.json",rec)
        write_json(output/'scenes'/f'{scene}.json',{'scene':scene,'tasks':len(keys),'components':len(representatives),'base_contexts':len(base_cache),'expanded_contexts':len(expanded_cache),'cache_metrics':body.metrics})
        write_json(output/'state.json',{'status':'RUNNING_STATIC_PROPOSALS','processed_blockers':len(results),'expected_blockers':6274,'last_scene':scene},immutable=False)
        del pf,source,body;gc.collect()
    if set(results)!=blocked:raise ValueError('Some original blockers were omitted')
    full=[]
    for key,t in sorted(tasks.items()):
        r=results.get(key);path=output/'tasks'/f"{key.replace(':','-')}.json"
        full.append({'task_key':key,'legacy_source_record_sha256':t['source_record_sha256'],
            'status':r['status'] if r else 'UNCHANGED_BASELINE_NO_MAPPING_FAULT',
            'proposal_path':str(path) if path.exists() else None,'proposal_sha256':digest(path) if path.exists() else None,'adopted':False})
    write_json(output/'all33954-index.json',full)
    startup=identity();startup.update(method_category='global_source_bounded_body_aware_proposals',
        task_contract='Preserve all33954/held114; finite old seed family and current profile, no motion or adoption',
        privileged_information=['native_mesh','source_geometry','source_bound_node_identity'],environment_limit='Protected static native queries only')
    result=dict(status='COMPLETE_GLOBAL_BOUNDED_PROPOSALS_NOT_NAVIGATION_ACCEPTANCE',startup=startup,
        records=33954,original_blockers=6274,held114_preserved=114,counts=dict(Counter(r['status'] for r in results.values())),
        native_queries=dict(query_counts),unique_context_rejections=dict(all_rejections),native_movement_actions=0,
        source_hashes={k:digest(p) for k,p in paths.items()},configuration_sha256=digest(cfg_path),
        full_index_sha256=digest(output/'all33954-index.json'),native_environment=runtime_identity(),wall_seconds=time.perf_counter()-started,
        limits='No new grid/radii/body/action/scene changes; no original data writes. D7 existing same-family positive and negative evidence is explicitly reused; negatives are unresolved, not a physical impossibility proof. All new positives require independent source/rational/native static audit and actual execution/replay before adoption.')
    write_json(output/'validation.json',result)
    write_json(output/'source-freeze.json',{'status':'CLOSED','source_digest':content_digest(sources)},immutable=False)
    write_json(output/'state.json',{'status':result['status'],'processed_blockers':6274,'records':33954},immutable=False)
    return result
