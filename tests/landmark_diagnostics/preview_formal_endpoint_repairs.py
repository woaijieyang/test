"""Bounded repair proposal for all endpoint contacts; does not change any annotation."""
import ast,collections,datetime,json,math,os,struct,sys,time
from pathlib import Path
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from preflight import SPECS,dataset_base,load,task_key
from swept_cylinder_reference import triangle_linear_sweep_distance
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
import numpy as np,habitat_sim,psutil
while True:
    u=psutil.cpu_percent(interval=1,percpu=True);idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<10 and i not in [1,2,6,7,8,12,18,20,22,24,27,30]]
    if idle:os.sched_setaffinity(0,[min(idle,key=lambda i:u[i])]);break
    time.sleep(30)
B=R/'outputs/connectivity';source=B/'formal-endpoint-source-v1';O=B/'formal-endpoint-repair-preview-v1';O.mkdir(exist_ok=False)
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':list(os.sched_getaffinity(0))})
def note(status,**kw):atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**kw})
try:
    audit=json.loads((source/'validation.json').read_text());m=json.loads((source/'manifest.json').read_text());assert digest(source/'manifest.json')==audit['manifest_sha256']
    profile=json.loads(Path(m['profile_path']).read_text());assert digest(m['profile_path'])==m['profile_sha256']
    catalog={r['scene']:r for r in json.loads((R/'outputs/landmark-connectivity/native-source-catalog-v1/catalog.json').read_text())['scenes']}
    episodes={}
    for dataset,spec in SPECS.items():
        p=dataset_base(dataset)/spec[1];assert digest(p)==m['datasets'][dataset]['annotation_sha256']
        for ep in load(p)['episodes']:
            if dataset=='rxr' and ep['instruction']['language']!='en-US':continue
            episodes[task_key(dataset,ep)]=ep
    assert set(episodes)==set(m['expected_tasks'])
    helper=R/'tests/landmark_diagnostics/audit_prb_step_interpretations.py';assert digest(helper)==m['sweep_traversal_sha256'];functions=[n for n in ast.parse(helper.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='sweep'];assert len(functions)==1;exec(compile(ast.Module(body=functions,type_ignores=[]),str(helper),'exec'),globals())
    proposals=[];changes=[]
    for scene in audit['scenes']:
        data=json.loads(Path(scene['receipt_path']).read_text());assert digest(scene['receipt_path'])==scene['receipt_sha256']
        grouped=collections.defaultdict(list)
        for row in data['records']:
            if row['raw_contact'] is not None or row['float32_contact'] is not None:grouped[tuple(row['position'])].append(row)
        if not grouped:continue
        name=scene['scene'];native=catalog[name];receipt=json.loads(Path(native['receipt_path']).read_text());gp=Path(receipt['native_geometry_path']);assert digest(gp)==data['native_geometry_sha256'];raw=gp.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);vertices=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);indices=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=vertices[indices].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);cache={};regions={}
        asset=profile['assets'][f'mp3d/{name}/{name}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path'])
        for original,rows in sorted(grouped.items()):
            candidates=set();counts=collections.Counter()
            for radius in [0.]+[i*.025 for i in range(1,15)]:
                for angle in ([0.] if radius==0 else [i*2*math.pi/48 for i in range(48)]):
                    query=np.array(original)+[radius*math.cos(angle),0,radius*math.sin(angle)];p=tuple(float(v) for v in pf.snap_point(query))
                    if all(math.isfinite(v) for v in p):candidates.add(p)
            chosen=None
            for p in sorted(candidates,key=lambda p:(math.dist(p,original),p)):
                if math.dist(p,original)>.5 or math.hypot(p[0]-original[0],p[2]-original[2])>.350001:counts['source_bounds']+=1;continue
                if not pf.is_navigable(p):counts['offmesh']+=1;continue
                if sweep(p,p) is not None:counts['source_contact']+=1;continue
                connected=True
                for row in rows:
                    ep=episodes[row['task_key']];others=[g['position'] for g in ep['goals']] if row['kind']=='start' else [ep['start_position']]
                    for other in others:
                        for start,end in [(p,other),(other,p)]:
                            q=habitat_sim.ShortestPath();q.requested_start=start;q.requested_end=end
                            if not pf.find_path(q) or not math.isfinite(q.geodesic_distance):connected=False;break
                        if not connected:break
                    if not connected:break
                if not connected:counts['disconnected']+=1;continue
                chosen=p;break
            item={'scene':name,'old_position':list(original),'proposed_position':None if chosen is None else list(chosen),'affected_endpoint_count':len(rows),'candidate_pool_unique':len(candidates),'preceding_rejections':dict(counts),'displacement_m':None if chosen is None else math.dist(chosen,original),'status':'NO_LEGAL_CANDIDATE_IN_FIXED_POOL' if chosen is None else 'SOURCE_CLEAR_NAVIGABLE_CONNECTED_PREVIEW_ONLY','native_geometry_sha256':data['native_geometry_sha256'],'navmesh_sha256':asset['navmesh_sha256']}
            proposals.append(item)
            for row in rows:changes.append({'task_key':row['task_key'],'dataset':row['dataset'],'kind':row['kind'],'scene':name,'old':list(original),'proposed':None if chosen is None else list(chosen),'status':item['status']})
            note('BUILDING_BOUNDED_PREVIEW',positions_checked=len(proposals),unresolved=sum(p['proposed_position'] is None for p in proposals))
    assert len(changes)==audit['counts']['raw_source_contacts']==106 and len(proposals)==21
    atomic_json(O/'validation.json',{'status':'COMPLETE_PROSPECTIVE_REPAIR_NOT_APPLIED','unique_positions':21,'affected_tasks':106,'changes':changes,'positions':proposals,'resolved_positions':sum(p['proposed_position'] is not None for p in proposals),'audit_sha256':digest(source/'validation.json'),'manifest_sha256':digest(source/'manifest.json'),'script_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat(),'limits':'Original/derived annotations, GT, links, frozen runtime and active runs untouched. Candidate is minimum displacement only within this finite predeclared pool, not global optimum. Requires independent prospective full6124source/static check and any needed protocol authorization; no motion or model success claim.'})
    note('COMPLETE_PROSPECTIVE_REPAIR_NOT_APPLIED',resolved_positions=sum(p['proposed_position'] is not None for p in proposals),positions=21,affected_tasks=106)
except Exception as error:note('FAILED_PREVIEW_PRESERVED',error=repr(error));raise

