"""Independent full-index and rational static audit of global bounded proposals."""
from collections import Counter,defaultdict
import gc,hashlib,json,math,os,time,zipfile
from pathlib import Path
from oracle.common.artifacts import digest,content_digest,owned_output,write_json,package_sources,freeze_sources,runtime_identity
from oracle.common.offline_audit import identity
from oracle.verification.source_scene import SourceScene
from oracle.verification.existing_bounded_mapping import check_choice_bounds


def verify_index(index,parent,blocked,held):
    if len(index)!=len(parent) or len({r['task_key'] for r in index})!=len(index) or {r['task_key'] for r in index}!=set(parent):
        raise ValueError('Full original task coverage changed')
    for r in index:
        k=r['task_key']
        if r['adopted'] or r['legacy_source_record_sha256']!=parent[k]['source_record_sha256']:raise ValueError('Original identity changed or premature adoption')
        if k in held:
            if r['status']!='HELD114_ORIGINAL_AND_FAILURE_PRESERVED' or r['proposal_path'] or r['proposal_sha256']:raise ValueError('Held record changed')
        elif k not in blocked:
            if r['status']!='UNCHANGED_BASELINE_NO_MAPPING_FAULT' or r['proposal_path'] or r['proposal_sha256']:raise ValueError('Non-fault baseline changed')
        elif not r['proposal_path'] or not r['proposal_sha256']:raise ValueError('Blocker evidence missing')


def audit(case_root,run_path,output,cpu):
    started=time.perf_counter();root=Path(case_root).resolve();run=owned_output(root,run_path);output=owned_output(root,output)
    if output.exists():raise FileExistsError(output)
    if cpu not in sorted(os.sched_getaffinity(0))[:64]:raise ValueError('CPU outside64')
    os.sched_setaffinity(0,{cpu});os.nice(15);os.environ['CUDA_VISIBLE_DEVICES']=''
    import habitat_sim
    v=json.loads((run/'validation.json').read_text());closure=json.loads((run/'source-freeze.json').read_text())
    if v['records']!=33954 or v['original_blockers']!=6274 or closure['status']!='CLOSED':raise ValueError('Producer not complete')
    with zipfile.ZipFile(run/'source.zip') as z:
        hashes={n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}
        if content_digest(hashes)!=closure['source_digest']:raise ValueError('Producer source snapshot changed')
        c='configs/experiments/global_bounded_mapping_v1.json'
        if hashes[c]!=v['configuration_sha256']:raise ValueError('Producer config changed')
        cfg=json.loads(z.read(c));protocol=json.loads(z.read('configs/protocols/current_linear.json'))
    if cfg['rings']!=[[.1,18],[.15,30],[.2,36],[.25,48],[.3,60],[.35,72]]:raise ValueError('Historical seed family was changed')
    paths={k:root/r['path'] for k,r in cfg['inputs'].items()}
    for k,p in paths.items():
        if digest(p)!=cfg['inputs'][k]['sha256']:raise ValueError('Frozen source changed: '+k)
    m=json.loads(paths['parent'].read_text());parent={t['task_key']:t for t in m['tasks']}
    held=set(json.loads(paths['held'].read_text())['task_keys']);blocked={r['task_key'] for r in json.loads(paths['blockers'].read_text())}
    if len(parent)!=33954 or len(held)!=114 or len(blocked)!=6274:raise ValueError('Declared complete scopes differ')
    index_path=run/'all33954-index.json'
    if digest(index_path)!=v['full_index_sha256']:raise ValueError('Producer index changed')
    index=json.loads(index_path.read_text());verify_index(index,parent,blocked,held)
    published={(r['scene'],r['node']):r for r in json.loads(paths['published'].read_text())['nodes']}
    native={(r['scene'],r['node']):r['native_candidates'][0] for r in json.loads(paths['native'].read_text())['nodes']}
    catalog={r['scene']:r for r in json.loads(paths['catalog'].read_text())['scenes']}
    d7=json.loads(paths['D7_audit'].read_text());d7_path=paths['D7_audit'].parent/'records.json'
    if digest(d7_path)!=d7['records_sha256']:raise ValueError('D7 reuse chain changed')
    d7_rows={r['task_key']:r for r in json.loads(d7_path.read_text())}
    groups=defaultdict(list);rows=[]
    for item in index:
        key=item['task_key']
        if item['proposal_path'] is None:
            rows.append({'task_key':key,'status':item['status'],'proposed_targets':None,'native_movement_actions':0});continue
        p=Path(item['proposal_path']).resolve()
        if not p.is_relative_to(run/'tasks') or digest(p)!=item['proposal_sha256']:raise ValueError('Proposal escaped or changed')
        r=json.loads(p.read_text());t=parent[key]
        if (r['task_key']!=key or r['old_targets']!=t['targets'] or r['original_heading']!=t['heading']
                or r['legacy_source_record_sha256']!=t['source_record_sha256'] or r['status']!=item['status'] or r['adopted'] or r['native_movement_actions']):raise ValueError('Original proposal identity changed')
        if r['scene']==d7['scene']:
            old=d7_rows[key]
            if r['reuse_source_sha256']!=digest(paths['D7_audit']) or r['proposed_targets']!=old['proposed_targets']:raise ValueError('Reused D7 coordinates changed')
        if r['proposed_targets'] is None:
            rows.append({'task_key':key,'status':r['status'],'proposed_targets':None,'proposal_sha256':digest(p),'native_movement_actions':0});continue
        if len(r['proposed_targets'])!=len(t['targets']) or len(r['choices'])!=len(t['targets']):raise ValueError('Reference occurrence dropped')
        groups[t['scene']].append((t,r,digest(p)))
    pp=Path(m['profile_path'])
    if digest(pp)!=m['profile_sha256']:raise ValueError('Current profile changed')
    profile=json.loads(pp.read_text());output.mkdir();_,sources=package_sources();freeze_sources(output,sources)
    startup=identity();startup.update(method_category='independent_global_bounded_static_audit',task_contract='Full33954identity/retention and proposed-coordinate source/rational/native gates; no motion acceptance',privileged_information=['source_node_identity','native_mesh','source_geometry'],environment_limit='Protected static native geometry queries only')
    startup['native_environment']=runtime_identity()
    write_json(output/'startup.json',startup)
    rings=[(rad*math.cos(i*2*math.pi/n),rad*math.sin(i*2*math.pi/n)) for rad,n in cfg['rings'] for i in range(n)]
    for scene,items in sorted(groups.items()):
        g=catalog[scene];asset=profile['assets'][f'mp3d/{scene}/{scene}.glb']
        if digest(asset['navmesh_path'])!=asset['navmesh_sha256']:raise ValueError('Navmesh changed')
        pf=habitat_sim.PathFinder()
        if not pf.load_nav_mesh(asset['navmesh_path']):raise ValueError('Native mesh load failed')
        source=SourceScene(g['receipt_path'],g['receipt_sha256'],protocol,catalog=g)
        source_points={};origins={};edges={};camera_seeds={}
        def camera_seed(node,cam):
            if node not in camera_seeds:
                candidates={}
                for i in range(101):
                    q=[float(x) for x in pf.snap_point([cam[0],cam[1]-.02*i,cam[2]])]
                    if not all(math.isfinite(x) for x in q) or not pf.is_navigable(q):continue
                    h=math.hypot(q[0]-cam[0],q[2]-cam[2]);drop=cam[1]-q[1]
                    if h<.5 and 0<=drop<=2 and math.dist(q,list(pf.snap_point(q)))<=1e-5:candidates[tuple(q)]=(h,-drop,q)
                camera_seeds[node]=min(candidates.values())[2] if candidates else None
            return camera_seeds[node]
        for t,r,sha in items:
            issues=[];contacts=[]
            for node,current,p,c in zip(t['original_viewpoint_path'],t['targets'],r['proposed_targets'],r['choices']):
                node_source=published[(scene,node)];anchor=native.get((scene,node));base=current
                if anchor is None and node_source['method']=='UNRESOLVED_no_direct_identity' and current is None:
                    base=camera_seed(node,node_source['camera_position'])
                issues.extend(check_choice_bounds(node_source,anchor,base,c))
                if p!=c['position']:issues.append('choice_position_binding')
                if not pf.is_navigable(p) or math.dist(p,list(pf.snap_point(p)))>1e-5:issues.append('native_point_membership')
                origin=(node,c['rank'],tuple(c['anchor']),tuple(p),None if current is None else tuple(current))
                if origin not in origins:
                    if c['rank']==0:seeds=[current]
                    elif c['rank']==2:seeds=[c['anchor']]
                    elif c['rank']==3:
                        a=c['anchor'];seeds=[[a[0]+dx,a[1],a[2]+dz] for dx,dz in rings]
                    else:seeds=[]
                    origins[origin]=any(q is not None and math.dist(p,list(pf.snap_point(q)))<=1e-5 for q in seeds)
                if not origins[origin]:issues.append('frozen_seed_origin')
                key=tuple(p)
                if key not in source_points:source_points[key]=source.contact(p,p,arithmetic='rational_hull')
                if source_points[key]:issues.append('rational_source_contact');contacts.append(source_points[key])
            for a,b in zip(r['proposed_targets'],r['proposed_targets'][1:]):
                for x,y in ((a,b),(b,a)):
                    k=(tuple(x),tuple(y))
                    if k not in edges:
                        path=habitat_sim.ShortestPath();path.requested_start=x;path.requested_end=y
                        edges[k]=bool(pf.find_path(path) and math.isfinite(path.geodesic_distance))
                    if not edges[k]:issues.append('reference_adjacency_disconnected')
            rows.append({'task_key':t['task_key'],'status':'PASS_GLOBAL_PROPOSAL_RATIONAL_STATIC_NOT_MOTION' if not issues else 'GLOBAL_PROPOSAL_AUDIT_FAILED_PRESERVED',
                'issues':sorted(set(issues)),'contacts':contacts,'proposal_sha256':sha,'proposed_targets':r['proposed_targets'],
                'old_targets':t['targets'],'original_heading':t['heading'],'legacy_source_record_sha256':t['source_record_sha256'],'native_movement_actions':0})
        write_json(output/'scenes'/f'{scene}.json',{'scene':scene,'proposals':len(items),'unique_points':len(source_points),'directed_edges':len(edges)})
        del pf,source;gc.collect()
    if len(rows)!=33954 or len({r['task_key'] for r in rows})!=33954:raise ValueError('Independent coverage incomplete')
    rows.sort(key=lambda r:r['task_key']);write_json(output/'all33954-records.json',rows)
    summary={'status':'COMPLETE_GLOBAL_PROPOSAL_STATIC_AUDIT_NOT_MOTION','startup':startup,'records':33954,
        'counts':dict(Counter(r['status'] for r in rows)),'held114_preserved':len(held),'original_blockers':len(blocked),
        'native_movement_actions':0,'producer_validation_sha256':digest(run/'validation.json'),'producer_index_sha256':digest(index_path),
        'source_hashes':{k:digest(p) for k,p in paths.items()},'records_sha256':digest(output/'all33954-records.json'),
        'native_environment':runtime_identity(),'wall_seconds':time.perf_counter()-started,
        'startup_sha256':digest(output/'startup.json'),
        'limits':'Static-only checks; all failures and untouched originals retained. Positive proposals require native execution/replay. Shared native inputs/physics model remain limits; no global reachability theorem or copied navigationPASS.'}
    write_json(output/'validation.json',summary);return summary
