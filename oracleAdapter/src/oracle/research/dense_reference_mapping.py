"""Source-bound dense CE trace candidates with global occurrence/component order.

Writes proposals only. Original task labels, baseline files and navmeshes are
never overwritten. Static path queries are not executed navigation actions.
"""
from collections import Counter,defaultdict
import gc,gzip,json,math,os,time
from pathlib import Path
from oracle.common.artifacts import digest,content_digest,owned_output,write_json,package_sources,freeze_sources,runtime_identity
from oracle.common.offline_audit import identity
from oracle.research.full_worker import load_task
from oracle.verification.source_scene import SourceScene
from oracle.planners.collision_queries import CachedSourceQueries
from oracle.adapters.landmark_rxr.ordered_candidates import align_connected_candidates


def within_bounds(point,anchor,sphere,horizontal):
    return (len(point)==3 and all(math.isfinite(v) for v in point)
            and math.dist(point,anchor)<=sphere
            and math.hypot(point[0]-anchor[0],point[2]-anchor[2])<=horizontal)


def prepare(case_root,output,cpu):
    started=time.perf_counter();cpu_started=time.process_time()
    root=Path(case_root).resolve();output=owned_output(root,output);package,sources=package_sources()
    if output.exists():raise FileExistsError(output)
    cfg_path=package/'configs/experiments/dense_reference_mapping_v1.json';cfg=json.loads(cfg_path.read_text())
    if cpu not in sorted(os.sched_getaffinity(0))[:64]:raise ValueError('CPU outside authorized64')
    os.sched_setaffinity(0,{cpu});os.nice(15);os.environ['CUDA_VISIBLE_DEVICES']=''
    import numpy as np
    import habitat_sim
    paths={k:root/v['path'] for k,v in cfg['inputs'].items()}
    for key,p in paths.items():
        if digest(p)!=cfg['inputs'][key]['sha256']:raise ValueError('Source drift: '+key)
    output.mkdir();freeze_sources(output,sources)
    write_json(output/'controller-process.json',dict(pid=os.getpid(),start_ticks=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]))
    write_json(output/'source-freeze.json',dict(status='OPEN',source_digest=content_digest(sources)))
    write_json(output/'state.json',dict(status='READING_FROZEN_SOURCES',native_movement_actions=0))
    availability=json.loads(paths['availability'].read_text())
    lineage={r['task_key']:r for r in json.loads(paths['lineage'].read_text())}
    references={r['task_key']:r for r in json.loads(paths['references'].read_text())}
    target_keys={r['task_key'] for r in availability if r['official_episode_id'] is not None}
    if len(availability)!=6274 or len(target_keys)!=2036:raise ValueError('Frozen blocker/source scope differs')
    parent=root/'outputs/oracleAdapter/full-continuous-reference-v1';pm=json.loads((parent/'manifest.json').read_text())
    if digest(parent/'manifest.json')!=cfg['parent_manifest_sha256']:raise ValueError('Parent identity changed')
    indexes={r['record']['task_key']:r for r in json.loads((parent/'index.json').read_text())}
    tasks={};scene_tasks=defaultdict(list);needed=defaultdict(set)
    for key in sorted(target_keys):
        task,_=load_task(root,pm,indexes[key],parent/'tasks.jsonl');ref=references[key]
        if (task['dataset']!='landmark_rxr' or ref['status']!='IDENTITY_AND_ORDINAL_REFERENCE_ACCOUNTED'
                or task['scene']!=ref['scene'] or task['path_id']!=ref['path_id']
                or task['original_viewpoint_path']!=[r['viewpoint_id'] for r in ref['occurrences']]
                or len(task['targets'])!=len(ref['occurrences'])):
            raise ValueError('Stable reference identity/occurrence mismatch')
        tasks[key]=task;scene_tasks[task['scene']].append(key)
        needed[task['split']].add(ref['episode_id'])
    asset_receipt=json.loads(paths['official_assets'].read_text())
    locks={str(Path(r['path']).resolve()):r['sha256'] for r in asset_receipt['sources']}
    gt_records={};gt_sources={}
    for split,ids in sorted(needed.items()):
        p=root/'data/datasets/RxR_VLNCE_v0'/split/f'{split}_guide_gt.json.gz'
        expected=locks[str(p.resolve())]
        if digest(p)!=expected:raise ValueError('Official GT changed')
        with gzip.open(p,'rt') as f:data=json.load(f)
        for eid in ids:
            row=data[eid];positions=row['locations'];actions=row['actions']
            if (len(positions)!=1+sum(a==1 for a in actions) or not actions or actions[-1]!=0
                    or any(type(a) is not int or a not in (0,1,2,3) for a in actions)
                    or any(len(p)!=3 or not all(type(v) in (int,float) and math.isfinite(v) for v in p) for p in positions)):
                raise ValueError('Official pose/action occurrence schema mismatch')
            forward_indices=[-1]+[i for i,a in enumerate(actions) if a==1]
            gt_records[(split,eid)]=(positions,forward_indices)
        gt_sources[split]=dict(path=str(p),sha256=expected);del data;gc.collect()
    catalog={r['scene']:r for r in json.loads(paths['catalog'].read_text())['scenes']}
    protocol=pm['protocol']
    startup=identity();startup.update(method_category='ordered_source_bound_mapping_proposal',
        task_contract='Preserve source IDs/headings/subinstructions and all33954; derive only source-available blocked mapping proposals',
        privileged_information=['official_ce_reference_and_GT','native_navmesh','source_geometry','recorded_task_identity'],
        environment_limit='CPU native path/point queries; no movement actions, no model evaluation')
    startup['native_environment']=runtime_identity()
    results={};total_queries=Counter()
    for scene,keys in sorted(scene_tasks.items()):
        geometry=catalog[scene];profile_path=Path(tasks[keys[0]]['profile_path'])
        if digest(profile_path)!=tasks[keys[0]]['profile_sha256']:raise ValueError('Navmesh profile changed')
        profile=json.loads(profile_path.read_text());asset=profile['assets'][f'mp3d/{scene}/{scene}.glb']
        if digest(asset['navmesh_path'])!=asset['navmesh_sha256']:raise ValueError('Navmesh changed')
        pf=habitat_sim.PathFinder()
        if not pf.load_nav_mesh(asset['navmesh_path']):raise ValueError('Navmesh loading failed')
        source=SourceScene(geometry['receipt_path'],geometry['receipt_sha256'],protocol,catalog=geometry)
        body=CachedSourceQueries(source,context_digest=content_digest([scene,cfg,geometry,protocol,sources]),**cfg['query_cache'])
        representatives=[];components={}
        def connected(a,b):
            total_queries['path']+=1;q=habitat_sim.ShortestPath();q.requested_start=a;q.requested_end=b
            return pf.find_path(q) and math.isfinite(q.geodesic_distance)
        def component(p):
            key=tuple(float(v) for v in p)
            if key in components:return components[key]
            for i,r in enumerate(representatives):
                if connected(p,r) and connected(r,p):components[key]=i;return i
            i=len(representatives);representatives.append(p);components[key]=i;return i
        for key in keys:
            if time.perf_counter()-started>cfg['wall_seconds_cap']:raise RuntimeError('Mapping proposal wall cap; partial evidence retained')
            task=tasks[key];ref=references[key];anchors=[r['position'] for r in ref['occurrences']]
            positions,forward_indices=gt_records[(task['split'],ref['episode_id'])]
            if math.dist(positions[0],anchors[0])>1e-5:raise ValueError('GT initial pose/reference source differs')
            array=np.asarray(positions,dtype=float);layers=[];rejections=Counter();contacts=[]
            for occurrence,anchor in enumerate(anchors):
                delta=array-np.asarray(anchor)
                nearby=np.flatnonzero((np.sum(delta*delta,axis=1)<=cfg['source_sphere_m']**2)
                    &(np.sum(delta[:,[0,2]]**2,axis=1)<=cfg['extra_horizontal_m']**2))
                candidates=[]
                for j in nearby:
                    total_queries['snap']+=1;q=[float(v) for v in pf.snap_point(positions[j])]
                    if not within_bounds(q,anchor,cfg['source_sphere_m'],cfg['extra_horizontal_m']):
                        rejections['source_bound_after_snap']+=1;continue
                    if not pf.is_navigable(q) or math.dist(q,list(pf.snap_point(q)))>1e-5:
                        rejections['not_exact_native_point']+=1;continue
                    hit=body.contact(q,q,certificate=True)
                    if hit:
                        rejections['source_body_contact']+=1
                        if len(contacts)<cfg['max_contact_examples_per_task']:
                            contacts.append(dict(reference_index=occurrence,source_index=int(j),contact=hit))
                        continue
                    candidates.append(dict(source_index=int(j),source_forward_action_index=forward_indices[j],
                        source_position=positions[j],position=q,reference_index=occurrence,
                        source_viewpoint_id=ref['occurrences'][occurrence]['viewpoint_id'],anchor=anchor,
                        cost=math.dist(q,anchor)**2,component=component(q),snap_displacement_m=math.dist(q,positions[j])))
                layers.append(candidates)
            equal=[a==b for a,b in zip(anchors,anchors[1:])]
            aligned=align_connected_candidates(layers,equal);selected=aligned['selected']
            if selected is not None:
                points=[c['position'] for c in selected]
                if not all(connected(a,b) for a,b in zip(points,points[1:])):raise ValueError('Chosen whole route disconnected')
                status='ORDERED_SOURCE_BOUNDED_STATIC_CANDIDATE_PENDING_INDEPENDENT_AUDIT'
            else:points=None;status='NO_COMPLETE_ORDERED_DENSE_GT_CANDIDATE_PRESERVED'
            rec=dict(task_key=key,status=status,scene=scene,source_episode_id=ref['episode_id'],
                source_record_sha256=task['source_record_sha256'],source_binding=task['source_binding'],
                original_heading=task['raw_heading'],original_subpath_headings=task['raw_subpath_headings'],
                segments=task['segments'],old_targets=task['targets'],proposed_targets=points,
                selected=selected,candidate_counts=[len(x) for x in layers],rejections=dict(rejections),contact_examples=contacts,
                zero_length_edge_rules=equal,profile_sha256=task['profile_sha256'],native_geometry_sha256=source.geometry_sha256,
                official_GT_source=gt_sources[task['split']],official_locations_sha256=content_digest(positions),
                raw_data_modified=False,native_movement_actions=0,
                semantic_limit='CE references have ordinal IDs from stable complete-source matching, not author per-viewpoint conversion receipts. All ordered original reference occurrences retained; candidate positions must still be independently audited and actually executed.')
            results[key]=rec;write_json(output/'tasks'/f"{key.replace(':','-')}.json",rec)
        write_json(output/'scenes'/f'{scene}.json',dict(scene=scene,tasks=len(keys),components=len(representatives),query_cache=body.metrics))
        write_json(output/'state.json',dict(status='GENERATING_ORDERED_PROPOSALS',completed=len(results),expected=2036,scene=scene,native_movement_actions=0),immutable=False)
        del pf,source,body;gc.collect()
    if set(results)!=target_keys:raise ValueError('Incomplete source-available coverage')
    full=[]
    for key,row in sorted(lineage.items()):
        if row['contract']['dataset']!='landmark_rxr':continue
        rec=results.get(key);full.append(dict(task_key=key,source_receipt_sha256=row['receipt_sha256'],
            proposal_path=str(output/'tasks'/f"{key.replace(':','-')}.json") if rec else None,
            status=rec['status'] if rec else 'UNCHANGED_BASELINE_PRESERVED_NO_NEW_CANDIDATE',
            adopted=False,original_record_preserved=True))
    if len(full)!=33954:raise ValueError('Full Landmark denominator changed')
    write_json(output/'all33954-index.json',full)
    summary=dict(status='COMPLETE_DENSE_GT_ORDERED_MAPPING_PROPOSALS_NOT_MOTION_ACCEPTANCE',startup=startup,
        records=33954,source_available_blockers=2036,proposal_counts=dict(Counter(r['status'] for r in results.values())),
        native_queries=dict(total_queries),native_movement_actions=0,source_hashes={k:digest(p) for k,p in paths.items()},
        configuration_sha256=digest(cfg_path),full_index_sha256=digest(output/'all33954-index.json'),
        wall_seconds=time.perf_counter()-started,process_cpu_seconds=time.process_time()-cpu_started,
        limits='No original data/navmesh changes, no adopted mapping, no R2R/RxR execution. No all-connected or route PASS claim; unchanged4238blocked records andheld114 remain in original full denominator.')
    write_json(output/'validation.json',summary)
    write_json(output/'source-freeze.json',dict(status='CLOSED',source_digest=content_digest(sources)),immutable=False)
    write_json(output/'state.json',dict(status=summary['status'],completed=2036,expected=2036,records=33954,native_movement_actions=0),immutable=False)
    return summary
