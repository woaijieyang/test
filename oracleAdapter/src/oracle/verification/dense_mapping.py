"""Independent source/order/bounds and rational static audit of dense proposals."""
from collections import Counter
import gzip,hashlib,json,math,os,time,zipfile
from pathlib import Path
from oracle.common.artifacts import digest,content_digest,owned_output,write_json,package_sources,freeze_sources,runtime_identity
from oracle.common.offline_audit import identity
from oracle.research.full_worker import load_task
from oracle.verification.source_scene import SourceScene


def verify_selection(occurrences,selected,gt,forward_indices,cfg):
    if len(occurrences)!=len(selected):return ['occurrence_count']
    issues=[];prior=None
    for i,(occ,q) in enumerate(zip(occurrences,selected)):
        j=q['source_index'];a=occ['position'];p=q['position']
        if type(j) is not int or not 0<=j<len(gt):issues.append('invalid_GT_occurrence');continue
        if (q['reference_index']!=i or q['source_viewpoint_id']!=occ['viewpoint_id'] or q['anchor']!=a
                or q['source_position']!=gt[j] or q['source_forward_action_index']!=forward_indices[j]):
            issues.append('source_occurrence_binding')
        if prior is not None:
            allow_same=occurrences[i-1]['position']==a
            if j<prior or (j==prior and not allow_same):issues.append('dense_occurrence_order')
        prior=j
        for x in (gt[j],p):
            if (len(x)!=3 or not all(math.isfinite(v) for v in x) or math.dist(x,a)>cfg['source_sphere_m']
                    or math.hypot(x[0]-a[0],x[2]-a[2])>cfg['extra_horizontal_m']):
                issues.append('source_displacement_bound')
        if not math.isclose(q['cost'],math.dist(p,a)**2,abs_tol=1e-12,rel_tol=1e-12):issues.append('candidate_cost_binding')
    return sorted(set(issues))


def audit(case_root,run_path,output,cpu):
    started=time.perf_counter();root=Path(case_root).resolve();run=owned_output(root,run_path);output=owned_output(root,output)
    if output.exists():raise FileExistsError(output)
    os.sched_setaffinity(0,{cpu});os.nice(15);os.environ['CUDA_VISIBLE_DEVICES']=''
    import habitat_sim
    v=json.loads((run/'validation.json').read_text());closure=json.loads((run/'source-freeze.json').read_text())
    if v['records']!=33954 or v['source_available_blockers']!=2036 or closure['status']!='CLOSED':raise ValueError('Producer incomplete')
    with zipfile.ZipFile(run/'source.zip') as z:
        hashes={n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}
        if content_digest(hashes)!=closure['source_digest']:raise ValueError('Producer source archive drift')
        name='configs/experiments/dense_reference_mapping_v1.json';cfg=json.loads(z.read(name))
        if hashes[name]!=v['configuration_sha256']:raise ValueError('Actual producer configuration differs')
    paths={k:root/r['path'] for k,r in cfg['inputs'].items()}
    for k,p in paths.items():
        if digest(p)!=cfg['inputs'][k]['sha256']:raise ValueError('Frozen source input drift')
    index_path=run/'all33954-index.json'
    if digest(index_path)!=v['full_index_sha256']:raise ValueError('Complete ledger changed')
    full=json.loads(index_path.read_text());lineage={r['task_key']:r for r in json.loads(paths['lineage'].read_text()) if r['contract']['dataset']=='landmark_rxr'}
    if len(full)!=33954 or len({r['task_key'] for r in full})!=33954 or {r['task_key'] for r in full}!=set(lineage):raise ValueError('Full original scope differs')
    records={};record_hashes={}
    for item in full:
        if item['adopted'] or not item['original_record_preserved'] or item['source_receipt_sha256']!=lineage[item['task_key']]['receipt_sha256']:raise ValueError('Original record falsely adopted/changed')
        if item['proposal_path']:
            p=Path(item['proposal_path']).resolve()
            if not p.is_relative_to(run/'tasks'):raise ValueError('Proposal file escaped')
            rec=json.loads(p.read_text());records[item['task_key']]=rec;record_hashes[str(p)]=digest(p)
            if rec['task_key']!=item['task_key'] or rec['status']!=item['status']:raise ValueError('Proposal index mismatch')
    eligible={r['task_key'] for r in json.loads(paths['availability'].read_text()) if r['official_episode_id'] is not None}
    if set(records)!=eligible or len(records)!=2036:raise ValueError('Complete source-available scope differs')
    selected={k:r for k,r in records.items() if r['selected'] is not None}
    refs={r['task_key']:r for r in json.loads(paths['references'].read_text())}
    parent=root/'outputs/oracleAdapter/full-continuous-reference-v1';pm=json.loads((parent/'manifest.json').read_text())
    if digest(parent/'manifest.json')!=cfg['parent_manifest_sha256']:raise ValueError('Original task identity changed')
    task_index={e['record']['task_key']:e for e in json.loads((parent/'index.json').read_text())}
    catalog={r['scene']:r for r in json.loads(paths['catalog'].read_text())['scenes']}
    asset_locks={str(Path(r['path']).resolve()):r['sha256'] for r in json.loads(paths['official_assets'].read_text())['sources']}
    gt_cache={};finders={};scenes={};results=[]
    output.mkdir();_,sources=package_sources();freeze_sources(output,sources)
    for key,rec in sorted(selected.items()):
        task,_=load_task(root,pm,task_index[key],parent/'tasks.jsonl');ref=refs[key]
        if (rec['old_targets']!=task['targets'] or rec['source_record_sha256']!=task['source_record_sha256']
                or rec['original_heading']!=task['raw_heading'] or rec['original_subpath_headings']!=task['raw_subpath_headings']
                or rec['segments']!=task['segments'] or rec['source_binding']!=task['source_binding']
                or rec['source_episode_id']!=ref['episode_id'] or rec['scene']!=task['scene'] or rec['profile_sha256']!=task['profile_sha256']
                or rec['raw_data_modified'] or rec['native_movement_actions']):raise ValueError('Source identity/heading/subinstructions changed')
        gt_source=rec['official_GT_source'];gp=Path(gt_source['path']);split=task['split']
        expected_gp=root/'data/datasets/RxR_VLNCE_v0'/split/f'{split}_guide_gt.json.gz'
        if gp.resolve()!=expected_gp.resolve() or gt_source['sha256']!=asset_locks[str(expected_gp.resolve())]:raise ValueError('Official source path/hash not authorized')
        if split not in gt_cache:
            if digest(gp)!=gt_source['sha256']:raise ValueError('GT source drift')
            with gzip.open(gp,'rt') as f:gt_cache[split]=json.load(f)
        gt=gt_cache[split][ref['episode_id']];positions=gt['locations'];forward=[-1]+[i for i,a in enumerate(gt['actions']) if a==1]
        if content_digest(positions)!=rec['official_locations_sha256']:raise ValueError('GT location binding differs')
        issues=verify_selection(ref['occurrences'],rec['selected'],positions,forward,cfg)
        points=rec['proposed_targets']
        if points!=[q['position'] for q in rec['selected']]:issues.append('proposed_targets_changed')
        scene=task['scene'];geometry=catalog[scene]
        if scene not in finders:
            pp=Path(task['profile_path'])
            if digest(pp)!=task['profile_sha256']:raise ValueError('Navmesh profile drift')
            asset=json.loads(pp.read_text())['assets'][f'mp3d/{scene}/{scene}.glb']
            if digest(asset['navmesh_path'])!=asset['navmesh_sha256']:raise ValueError('Navmesh drift')
            pf=habitat_sim.PathFinder()
            if not pf.load_nav_mesh(asset['navmesh_path']):raise ValueError('Native mesh load failed')
            finders[scene]=pf;scenes[scene]=SourceScene(geometry['receipt_path'],geometry['receipt_sha256'],pm['protocol'],catalog=geometry)
        pf=finders[scene];source=scenes[scene];contacts=[]
        if rec['native_geometry_sha256']!=source.geometry_sha256:raise ValueError('Geometry identity mismatch')
        for i,(q,p) in enumerate(zip(rec['selected'],points)):
            if not pf.is_navigable(p) or math.dist(p,list(pf.snap_point(p)))>1e-5 or math.dist(p,list(pf.snap_point(positions[q['source_index']])))>1e-5:
                issues.append('native_membership_or_projection')
            hit=source.contact(p,p,arithmetic='rational_hull')
            if hit:issues.append('independent_source_contact');contacts.append(dict(reference_index=i,contact=hit))
        for a,b in zip(points,points[1:]):
            for start,end in ((a,b),(b,a)):
                p=habitat_sim.ShortestPath();p.requested_start=start;p.requested_end=end
                if not pf.find_path(p) or not math.isfinite(p.geodesic_distance):issues.append('adjacent_reference_disconnected')
        results.append(dict(task_key=key,status='PASS_INDEPENDENT_STATIC_NOT_MOTION' if not issues else 'STATIC_AUDIT_FAILED_PRESERVED',
            issues=sorted(set(issues)),source_contacts=contacts,proposal_sha256=record_hashes[str((run/'tasks'/f"{key.replace(':','-')}.json").resolve())],
            actual_movement_actions=0))
    write_json(output/'records.json',results)
    write_json(output/'sealed-proposal-hashes.json',record_hashes)
    startup=identity();startup.update(method_category='independent_dense_mapping_static_audit',privileged_information=['source_reference_GT','native_navmesh','native_source_geometry'],task_contract='Validate source/order/bounds/headings and rational static gates; no movement acceptance',environment_limit='Protected CPU native point/path queries and rational source tests; no executed navigation or model evaluation')
    summary=dict(status='COMPLETE_INDEPENDENT_DENSE_PROPOSAL_STATIC_AUDIT_NOT_MOTION',startup=startup,full_records=33954,
        source_available_proposals=2036,selected_proposals=len(selected),results=dict(Counter(r['status'] for r in results)),
        producer_validation_sha256=digest(run/'validation.json'),producer_index_sha256=digest(index_path),
        records_sha256=digest(output/'records.json'),sealed_proposal_hashes_sha256=digest(output/'sealed-proposal-hashes.json'),
        native_environment=runtime_identity(),wall_seconds=time.perf_counter()-started,native_movement_actions=0,
        limits='Hashes of2036proposal files sealed independently after producer completion; producer index originally bound paths but not per-file bytes. All33954 identities accounted; only selected proposals get new rational/static queries. Requires actual uninterrupted motion/replay before recovery claim.')
    write_json(output/'validation.json',summary);return summary
