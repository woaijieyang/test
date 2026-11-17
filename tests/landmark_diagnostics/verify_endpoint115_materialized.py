"""Independently validate actual immutable endpoint115 files, not virtual copies."""
import collections,copy,datetime,json,math,os,struct,sys,time
from pathlib import Path
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from preflight import SPECS,dataset_base,load,task_key
from cylinder_contact_height import clip_y
from projected_distance_reference import projected_distance
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.nice(15)
import numpy as np,habitat_sim,psutil
u=psutil.cpu_percent(interval=1,percpu=True);idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<10 and i not in [1,2,6,7,8,12,18,20,22,24,27,30]];assert idle;os.sched_setaffinity(0,[min(idle,key=lambda i:u[i])])
B=R/'outputs/connectivity';O=B/'formal-endpoint-repair-preview-v2';source=B/'formal-endpoint-source-v1';proposal=json.loads((O/'validation.json').read_text());old=json.loads((source/'validation.json').read_text());m=json.loads((source/'manifest.json').read_text());assert digest(source/'validation.json')==proposal['audit_sha256']
assert digest(m['profile_path'])==m['profile_sha256'];profile=json.loads(Path(proposal['profile_path']).read_text());assert digest(proposal['profile_path'])==proposal['profile_sha256'];catalog={r['scene']:r for r in json.loads((R/'outputs/landmark-connectivity/native-source-catalog-v1/catalog.json').read_text())['scenes']}
changes={(r['task_key'],r['kind']):r for r in proposal['changes']};assert len(changes)==106
derivative=R/'data/derived/annotations/awarevln-endpoint115-v1';bound=json.loads((derivative/'manifest.json').read_text());protocol=json.loads((derivative/'protocol.json').read_text());assert digest(derivative/'protocol.json')==bound['protocol_sha256'];assert all(digest(p)==h for p,h in bound['derived_files'].items());assert all(digest(p)==h for p,h in bound['source_files_unchanged'].items())
virtual={};groundtruth={};input_hashes={}
for dataset,spec in SPECS.items():
    base=R/protocol['dataset_roots'][dataset]/'val_unseen';p=base/spec[1];g=base/spec[2];groundtruth[dataset]=load(g);input_hashes[str(p)]=digest(p);input_hashes[str(g)]=digest(g)
    for ep in load(p)['episodes']:
        if dataset=='rxr' and ep['instruction']['language']!='en-US':continue
        key=task_key(dataset,ep);assert key not in virtual;virtual[key]=(dataset,ep)
assert set(virtual)==set(m['expected_tasks'])
counts=collections.Counter();failures=[];repaired_keys=[];body_cache={}
for scene in old['scenes']:
    data=json.loads(Path(scene['receipt_path']).read_text());assert digest(scene['receipt_path'])==scene['receipt_sha256'];name=scene['scene'];native=catalog[name];receipt=json.loads(Path(native['receipt_path']).read_text());gp=Path(receipt['native_geometry_path']);assert digest(gp)==data['native_geometry_sha256'];raw=gp.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);vs=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=vs[ix].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1)
    asset=profile['assets'][f'mp3d/{name}/{name}.glb'];pf=habitat_sim.PathFinder();assert digest(asset['navmesh_path'])==asset['navmesh_sha256'] and pf.load_nav_mesh(asset['navmesh_path'])
    def body(p):
        key=(name,tuple(p))
        if key in body_cache:return body_cache[key]
        p=np.asarray(p,dtype=float);indices=np.flatnonzero((lo[:,0]<p[0]+.1)&(hi[:,0]>p[0]-.1)&(lo[:,2]<p[2]+.1)&(hi[:,2]>p[2]-.1)&(lo[:,1]<p[1]+1.5)&(hi[:,1]>p[1]+1e-5));hit=None
        for j in indices:
            poly=clip_y(clip_y(list(tri[j]),p[1]+1e-5,True),p[1]+1.5,False)
            if poly:
                distance=projected_distance(poly,p)
                if distance<.1-1e-6:hit={'triangle':int(j),'distance':float(distance)};break
        body_cache[key]=hit;return hit
    for row in data['records']:
        change=changes.get((row['task_key'],row['kind']));ep=virtual[row['task_key']][1];point=ep['start_position'] if row['kind']=='start' else ep['goals'][int(row['kind'].split(':')[1])]['position'];assert point==(row['position'] if change is None else change['proposed']);hit=body(point);quantized=np.array(point,dtype=np.float32).astype(float).tolist();native_hit=body(quantized);navigable=pf.is_navigable(point)
        counts['endpoints_checked']+=1;counts['raw_source_contacts']+=hit is not None;counts['float32_source_contacts']+=native_hit is not None;counts['offmesh_endpoints']+=not navigable
        if change is not None and change['proposed'] is not None:
            assert math.dist(point,row['position'])<=.5 and math.hypot(point[0]-row['position'][0],point[2]-row['position'][2])<=.350001
            assert hit is None and native_hit is None and navigable and math.dist(point,list(pf.snap_point(point)))<=1e-5
            repaired_keys.append((row['task_key'],row['kind']))
        if hit is not None or native_hit is not None:failures.append({'task_key':row['task_key'],'kind':row['kind'],'position':point,'raw_contact':hit,'float32_contact':native_hit})
    for key,(dataset,ep) in virtual.items():
        if ep['scene_id']!=f'mp3d/{name}/{name}.glb':continue
        goals=[g['position'] for g in ep['goals']];paths=[[ep['start_position'],*groundtruth[dataset][str(ep['episode_id'])]['locations'],*goals],[ep['start_position'],*ep.get('reference_path',[]),*goals]]
        for points in paths:
            for p in points:
                for goal in goals:
                    q=habitat_sim.ShortestPath();q.requested_start=p;q.requested_end=goal;counts['reference_to_goal_queries']+=1
                    assert pf.find_path(q) and math.isfinite(q.geodesic_distance),('reference_unreachable',key)
            for start,end in zip(points,points[1:]):
                q=habitat_sim.ShortestPath();q.requested_start=start;q.requested_end=end;counts['reference_adjacent_queries']+=1
                assert pf.find_path(q) and math.isfinite(q.geodesic_distance),('reference_segment_unreachable',key)
        counts['tasks_checked']+=1
assert counts['tasks_checked']==3062 and counts['endpoints_checked']==6124 and len(repaired_keys)==sum(r['proposed'] is not None for r in proposal['changes'])
assert all(digest(p)==h for p,h in input_hashes.items())
output=R/'outputs/connectivity/endpoint115-materialized-v1/independent-static-validation.json';assert not output.exists()
atomic_json(output,{'status':'FAIL_MATERIALIZED_ENDPOINTS' if failures else 'PASS_MATERIALIZED_ENDPOINTS_AND_REFERENCE_CONNECTIVITY','counts':dict(counts),'resolved_endpoint_changes':len(repaired_keys),'remaining_failures':failures,'resolved_keys':repaired_keys,'derivative_manifest_sha256':digest(derivative/'manifest.json'),'protocol_sha256':digest(derivative/'protocol.json'),'proposal_sha256':digest(O/'validation.json'),'field_diff_sha256':digest(O/'field-diff.json'),'script_sha256':digest(__file__),'body_clipping_sha256':digest(R/'tests/landmark_diagnostics/cylinder_contact_height.py'),'projected_distance_sha256':digest(R/'tests/landmark_diagnostics/projected_distance_reference.py'),'input_hashes_unchanged':input_hashes,'time':datetime.datetime.now().astimezone().isoformat(),'limits':'Actual materialized endpoint115 annotation and GT files loaded from disk; original and parent files remain byte-identical. All6124 endpoints and both dense/sparse reference connectivity checked. Source clipping is independent of zero-segment sweep; no actual model run, complete route body proof, or protocol adoption.'})
print(dict(counts),'resolved',len(repaired_keys),'remaining',len(failures))

