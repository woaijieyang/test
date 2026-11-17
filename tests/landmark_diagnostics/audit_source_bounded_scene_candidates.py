"""Independent bounds, raw identity, source-cylinder and native path audit for proposals."""
import os,sys,json,math,struct,datetime,argparse,time,re
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
P=argparse.ArgumentParser();P.add_argument('--run',required=True);args=P.parse_args();assert re.fullmatch('[A-Za-z0-9-]+',args.run)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
import numpy as np,habitat_sim,psutil
u=psutil.cpu_percent(interval=1,percpu=True);cpu=min([i for i in sorted(os.sched_getaffinity(0))[:64] if i not in [22,24,27,30]],key=lambda i:u[i]);os.sched_setaffinity(0,[cpu])
B=R/'outputs/landmark-connectivity';O=B/args.run;atomic_json(O/'audit-process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':cpu})
while not (O/'validation.json').exists():
 p=json.loads((O/'process.json').read_text());stat=Path('/proc',str(p['pid']),'stat');z=stat.read_text().rsplit(')',1)[1].split() if stat.exists() else [];assert z and z[19]==str(p['start_ticks']) and z[0] not in 'ZX','Producer incomplete';time.sleep(15)
v=json.loads((O/'validation.json').read_text());parent=B/'full-native-v11/manifest.json';assert digest(parent)==v['parent_manifest_sha256'];m=json.loads(parent.read_text());scene=v['scene'];old={t['task_key']:t for t in m['tasks'] if t['scene']==scene};proposals=json.loads((O/'candidate_tasks.json').read_text())['tasks'];new={t['task_key']:t for t in proposals};rows={r['task_key']:r for r in v['rows']};assert len(proposals)==len(old)==v['expected_tasks'] and set(new)==set(old)==set(rows);held=set(json.loads((B/'constraint-blockers.json').read_text())['task_keys']);assert not held.intersection(old)
profilepath=Path(v.get('profile_path',m['profile_path']));assert digest(profilepath)==v['profile_sha256'];profile=json.loads(profilepath.read_text());asset=profile['assets'][f'mp3d/{scene}/{scene}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path']);geo_path=B/f'full-source-native-{scene}-v1/validation.json';assert digest(geo_path)==v['native_geometry_receipt_sha256'];geo=json.loads(geo_path.read_text());gp=Path(geo['native_geometry_path']);assert digest(gp)==geo['native_geometry_sha256'];raw=gp.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);vertices=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=vertices[ix].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1)
native_path=B/'native-mapping.json';identity_path=B/'published-identity-nodes.json';native={(r['scene'],r['node']):r['native_candidates'][0] for r in json.loads(native_path.read_text())['nodes']};identity={(r['scene'],r['node']):r for r in json.loads(identity_path.read_text())['nodes']};seen={};edges={};positive=negative=0;maxdelta=0
for key,t in old.items():
 n=new[key];r=rows[key]
 if r['status']=='NO_SOURCE_CLEAR_COMMON_COMPONENT':assert n==t;negative+=1;continue
 assert r['status']=='SOURCE_CLEAR_TARGETS_COMMON_COMPONENT_PENDING_MOTION';positive+=1;assert {k:v for k,v in n.items() if k not in ['targets','mapping_methods']}=={k:v for k,v in t.items() if k not in ['targets','mapping_methods']};assert len(n['targets'])==len(t['targets'])==len(r['choices'])
 for node,oldq,q,c in zip(t['original_viewpoint_path'],t['targets'],n['targets'],r['choices']):
  src=identity[(scene,node)];anchor=native[(scene,node)] if (scene,node) in native else src['position'] if src['method']!='UNRESOLVED_no_direct_identity' else oldq;kind='official_reference_node' if (scene,node) in native else src['method'] if src['method']!='UNRESOLVED_no_direct_identity' else 'bounded_camera_projection';assert c['anchor']==anchor and c['anchor_kind']==kind and c['position']==q;d=math.dist(q,anchor);assert d<=.5 and abs(d-c['displacement'])<1e-10;maxdelta=max(maxdelta,d)
  if c['rank']==3:assert math.hypot(q[0]-anchor[0],q[2]-anchor[2])<=.350001
  if kind=='bounded_camera_projection':cam=src['camera_position'];assert math.hypot(q[0]-cam[0],q[2]-cam[2])<.5 and 0<=cam[1]-q[1]<=2
  assert pf.is_navigable(q) and math.dist(q,list(pf.snap_point(q)))<=1e-5
  k=tuple(q)
  if k not in seen:
   qv=np.array(q);ids=np.flatnonzero((lo[:,0]<q[0]+.1)&(hi[:,0]>q[0]-.1)&(lo[:,2]<q[2]+.1)&(hi[:,2]>q[2]-.1)&(lo[:,1]<q[1]+1.5)&(hi[:,1]>q[1]+1e-5));hits=[int(j) for j in ids if triangle_linear_sweep_distance(tri[j],qv,qv)<.1-1e-6];assert not hits,(key,node,hits[:5]);seen[k]=True
 for a,b in zip(n['targets'],n['targets'][1:]):
  k=(tuple(a),tuple(b))
  if k not in edges:
   path=habitat_sim.ShortestPath();path.requested_start=a;path.requested_end=b;assert pf.find_path(path) and math.isfinite(path.geodesic_distance);edges[k]=float(path.geodesic_distance)
assert positive+negative==len(old)
atomic_json(O/'independent-static.json',{'status':'PASS_PROPOSAL_IDENTITY_BOUNDS_BODY_AND_CONNECTIVITY_NOT_MOTION','tasks':len(old),'static_source_clear_tasks':positive,'unresolved_tasks_preserved':negative,'unique_source_clear_positions_checked':len(seen),'unique_native_edges_checked':len(edges),'max_source_displacement_m':maxdelta,'input_sha256':digest(O/'validation.json'),'candidate_tasks_sha256':digest(O/'candidate_tasks.json'),'native_mapping_sha256':digest(native_path),'published_identity_sha256':digest(identity_path),'profile_sha256':digest(profilepath),'script_sha256':digest(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Independent zero-motion sweep/body, source bounds, task preservation and native geodesic checks. No actual new-route execution or continuous movement proof, no candidate adoption. Failed task records remain unchanged.'});print('PASS',positive,negative,len(seen))
