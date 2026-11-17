"""Deterministic triangle projection inside existing bounds; no extra ring sampling or adoption."""
import os,sys,json,math,datetime,collections,argparse,re
from pathlib import Path
P=argparse.ArgumentParser();P.add_argument('--scene',required=True);P.add_argument('--cpu',type=int,required=True);args=P.parse_args();assert re.fullmatch('[A-Za-z0-9]{11}',args.scene);
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics'),str(R/'.cache/geometry-tools')]
from workspace import atomic_json,digest
import numpy as np,habitat_sim,trimesh,psutil
from bounded_triangle_projection import closest_in_horizontal_disk
assert args.cpu in sorted(os.sched_getaffinity(0))[:64];os.sched_setaffinity(0,[args.cpu])
B=R/'outputs/landmark-connectivity';O=B/'bounded-component-surface-batch-v2'/args.scene;O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});parent=B/'full-native-v11/manifest.json';m=json.loads(parent.read_text());sc=args.scene;tasks=[t for t in m['tasks'] if t['scene']==sc];expected_count=len(tasks);expected_controls=sum(t['status']=='READY_FOR_NATIVE_MOTION' for t in tasks);assert expected_count>0;profile=json.loads(Path(m['profile_path']).read_text());asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path']);verts=np.asarray(pf.build_navmesh_vertices(),dtype=float);indices=np.asarray(pf.build_navmesh_vertex_indices(),dtype=int).reshape(-1,3);tri=verts[indices];lo=tri.min(axis=1);hi=tri.max(axis=1)
native_path=B/'native-mapping.json';identity_path=B/'published-identity-nodes.json';native={(r['scene'],r['node']):r['native_candidates'][0] for r in json.loads(native_path.read_text())['nodes']};identity={(r['scene'],r['node']):r for r in json.loads(identity_path.read_text())['nodes']};held=set(json.loads((B/'constraint-blockers.json').read_text())['task_keys']);source_v1=json.loads((B/'full-native-v1/manifest.json').read_text());prior_tasks={t['task_key']:t for t in source_v1['tasks'] if t['scene']==sc};reps=[];pcache={};edgecache={};solver_failures=[];catalog={}
def connected(a,b):
 key=(tuple(a),tuple(b))
 if key not in edgecache:
  q=habitat_sim.ShortestPath();q.requested_start=a;q.requested_end=b;edgecache[key]=bool(pf.find_path(q) and math.isfinite(q.geodesic_distance))
 return edgecache[key]
def component(p):
 key=tuple(p)
 if key in pcache:return pcache[key]
 for i,r in enumerate(reps):
  f=connected(p,r);back=connected(r,p);assert f==back,'Asymmetric connectivity requires separate review'
  if f:pcache[key]=i;return i
 reps.append(p);pcache[key]=len(reps)-1;return len(reps)-1

def anchor_for(node,current):
 info=identity[(sc,node)]
 if (sc,node) in native:return native[(sc,node)],'official_reference_node',info
 if info['method']!='UNRESOLVED_no_direct_identity':return info['position'],info['method'],info
 return current,'bounded_camera_projection',info

def options(node,current,previous):
 anchor,kind,info=anchor_for(node,current);key=(node,tuple(current) if current is not None else None,tuple(previous) if previous is not None else None)
 if key in catalog:return catalog[key]
 if anchor is None:
  result={'node':node,'anchor_kind':kind,'components':{},'triangles_considered':0,'queries':0,'camera_projection_deferred':True};catalog[key]=result;return result
 a=np.array(anchor);found={};tested=0
 def collect(candidate,method,triangle_index=None,rank=1):
  nonlocal tested
  candidate=np.array(candidate);q=np.array(pf.snap_point(candidate));tested+=1
  if not np.isfinite(q).all() or not pf.is_navigable(q) or np.linalg.norm(q-candidate)>1e-5:return
  d=float(np.linalg.norm(q-a))
  if d>.5:return
  if method not in ['preserved_current','current_projection','prior_projection','anchor_projection'] and math.hypot(q[0]-a[0],q[2]-a[2])>.350001:return
  if kind=='bounded_camera_projection':
   cam=info['camera_position']
   if math.hypot(q[0]-cam[0],q[2]-cam[2])>=.5 or not 0<=cam[1]-q[1]<=2:return
  c=component(q.tolist());item={'position':q.tolist(),'anchor':anchor,'anchor_kind':kind,'source_distance':d,'horizontal_distance':math.hypot(q[0]-a[0],q[2]-a[2]),'method':method,'triangle_index':triangle_index,'rank':rank}
  if c not in found or (rank,d)<(found[c]['rank'],found[c]['source_distance']):found[c]=item
 if current is not None:collect(pf.snap_point(current),'current_projection',rank=0)
 if previous is not None:collect(pf.snap_point(previous),'prior_projection',rank=0)
 collect(pf.snap_point(anchor),'anchor_projection',rank=2)
 delta=np.maximum(np.maximum(lo-a,a-hi),0);ids=np.flatnonzero((np.sum(delta*delta,axis=1)<=.25+1e-12)&(np.sum(delta[:,[0,2]]**2,axis=1)<=.350001**2+1e-12))
 if kind=='bounded_camera_projection':
  # Conservative: current point retained, no extension of camera-domain policy in this experiment.
  result={'node':node,'anchor_kind':kind,'components':found,'triangles_considered':0,'queries':tested,'camera_projection_deferred':True};catalog[key]=result;return result
 if len(ids):
  for index in ids:
   q=closest_in_horizontal_disk(tri[index],a,.35)
   if q is None or np.linalg.norm(q-a)>.5:continue
   collect(q,'triangle_projection',int(index))
   collect(q+1e-4*(tri[index].mean(axis=0)-q),'triangle_projection_interior',int(index))
 result={'node':node,'anchor_kind':kind,'components':found,'triangles_considered':len(ids),'queries':tested,'camera_projection_deferred':False};catalog[key]=result;return result
rows=[];candidate_tasks=[];controls=0
for t in tasks:
 if t['task_key'] in held:
  candidate_tasks.append(t);rows.append({'task_key':t['task_key'],'status':'HELD114_UNMODIFIED'});continue
 if t['status']=='READY_FOR_NATIVE_MOTION':
  for node,p in zip(t['original_viewpoint_path'],t['targets']):
   a,kind,info=anchor_for(node,p);assert math.dist(p,a)<=.5 and pf.is_navigable(p) and math.dist(p,list(pf.snap_point(p)))<=1e-5
  assert all(connected(a,b) for a,b in zip(t['targets'],t['targets'][1:]));controls+=1;candidate_tasks.append(t);rows.append({'task_key':t['task_key'],'status':'UNCHANGED_READY_CONTROL'});continue
 assert len(prior_tasks[t['task_key']]['targets'])==len(t['targets']);opts=[options(n,p,old) for n,p,old in zip(t['original_viewpoint_path'],t['targets'],prior_tasks[t['task_key']]['targets'])];common=set.intersection(*(set(x['components']) for x in opts)) if opts else set()
 if common:
  label=min(common,key=lambda c:sum(x['components'][c]['rank']*1000+x['components'][c]['source_distance'] for x in opts));choices=[x['components'][label] for x in opts];points=[x['position'] for x in choices];assert all(connected(a,b) for a,b in zip(points,points[1:]));candidate_tasks.append({**t,'targets':points,'status':'STATIC_CANDIDATE_PENDING_SOURCE_BODY_AND_MOTION'});rows.append({'task_key':t['task_key'],'status':'RECOVERED_STATIC_CANDIDATE_NOT_ACCEPTED','choices':choices})
 else:candidate_tasks.append(t);rows.append({'task_key':t['task_key'],'status':'BLOCKED_PRESERVED','component_counts':[len(x['components']) for x in opts]})
 if len(rows)%50==0:atomic_json(O/'state.json',{'status':'RUNNING','tasks':len(rows),'catalog_entries':len(catalog)})
counts=dict(collections.Counter(r['status'] for r in rows));assert len(rows)==expected_count and controls==expected_controls;atomic_json(O/'candidate_tasks.json',{'tasks':candidate_tasks,'scope':'No actual input replacement; all original scene records retained'});atomic_json(O/'validation.json',{'status':'COMPLETE_GEOMETRIC_COMPONENT_PROJECTION_NOT_ACCEPTANCE','scene':sc,'tasks':expected_count,'counts':counts,'rows':rows,'candidate_catalog':list(catalog.values()),'constrained_solver_failures':solver_failures,'native_components_seen':len(reps),'native_path_queries':len(edgecache),'parent_manifest_sha256':digest(parent),'profile_sha256':m['profile_sha256'],'mesh_sha256':asset['navmesh_sha256'],'native_mapping_sha256':digest(native_path),'identity_mapping_sha256':digest(identity_path),'trimesh_version':trimesh.__version__,'trimesh_closest_point_source_sha256':digest(Path(trimesh.triangles.__file__)),'projection_helper_sha256':digest(R/'tests/landmark_diagnostics/bounded_triangle_projection.py'),'script_sha256':digest(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Same<=0.5m source sphere and<=0.350001m horizontal bound for new proposals. Deterministic geometry projection, not expanded sampling. Current READY controls unchanged. Optimizer/numerical misses remain inconclusive; no source-body, floor/landmark semantics or actual-motion acceptance from this file. No annotation/mesh changes.'});atomic_json(O/'state.json',{'status':'COMPLETE','counts':counts,'solver_failures':len(solver_failures)});print(counts,'solver_failures',len(solver_failures))
