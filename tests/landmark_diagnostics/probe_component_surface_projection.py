"""Deterministic triangle projection inside existing bounds; no extra ring sampling or adoption."""
import os,sys,json,math,datetime,collections
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'.cache/geometry-tools')]
from workspace import atomic_json,digest
import numpy as np,habitat_sim,trimesh,psutil
from scipy.optimize import minimize
u=psutil.cpu_percent(interval=1,percpu=True);avail=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<25];assert avail;os.sched_setaffinity(0,[min(avail,key=lambda i:u[i])])
B=R/'outputs/landmark-connectivity';O=B/'vfua-component-surface-projection-v1';O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});parent=B/'full-native-v11/manifest.json';m=json.loads(parent.read_text());sc='VFuaQ6m2Qom';tasks=[t for t in m['tasks'] if t['scene']==sc];assert len(tasks)==635;profile=json.loads(Path(m['profile_path']).read_text());asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path']);verts=np.asarray(pf.build_navmesh_vertices(),dtype=float);indices=np.asarray(pf.build_navmesh_vertex_indices(),dtype=int).reshape(-1,3);tri=verts[indices];lo=tri.min(axis=1);hi=tri.max(axis=1)
native_path=B/'native-mapping.json';identity_path=B/'published-identity-nodes.json';native={(r['scene'],r['node']):r['native_candidates'][0] for r in json.loads(native_path.read_text())['nodes']};identity={(r['scene'],r['node']):r for r in json.loads(identity_path.read_text())['nodes']};held=set(json.loads((B/'constraint-blockers.json').read_text())['task_keys']);assert not held.intersection(t['task_key'] for t in tasks);reps=[];pcache={};edgecache={};solver_failures=[];catalog={}
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

def options(node,current):
 anchor,kind,info=anchor_for(node,current);key=(node,tuple(current) if current is not None else None)
 if key in catalog:return catalog[key]
 assert anchor is not None,'This selected scene has no missing-camera seed in blocked tasks';a=np.array(anchor);found={};tested=0
 def collect(candidate,method,triangle_index=None,rank=1):
  nonlocal tested
  candidate=np.array(candidate);q=np.array(pf.snap_point(candidate));tested+=1
  if not np.isfinite(q).all() or not pf.is_navigable(q) or np.linalg.norm(q-candidate)>1e-5:return
  d=float(np.linalg.norm(q-a))
  if d>.5:return
  if method!='preserved_current' and math.hypot(q[0]-a[0],q[2]-a[2])>.350001:return
  if kind=='bounded_camera_projection':
   cam=info['camera_position']
   if math.hypot(q[0]-cam[0],q[2]-cam[2])>=.5 or not 0<=cam[1]-q[1]<=2:return
  c=component(q.tolist());item={'position':q.tolist(),'anchor':anchor,'anchor_kind':kind,'source_distance':d,'horizontal_distance':math.hypot(q[0]-a[0],q[2]-a[2]),'method':method,'triangle_index':triangle_index,'rank':rank}
  if c not in found or (rank,d)<(found[c]['rank'],found[c]['source_distance']):found[c]=item
 if current is not None:collect(current,'preserved_current',rank=0)
 delta=np.maximum(np.maximum(lo-a,a-hi),0);ids=np.flatnonzero((np.sum(delta*delta,axis=1)<=.25+1e-12)&(np.sum(delta[:,[0,2]]**2,axis=1)<=.350001**2+1e-12))
 if kind=='bounded_camera_projection':
  # Conservative: current point retained, no extension of camera-domain policy in this experiment.
  result={'node':node,'anchor_kind':kind,'components':found,'triangles_considered':0,'queries':tested,'camera_projection_deferred':True};catalog[key]=result;return result
 if len(ids):
  closest=trimesh.triangles.closest_point(tri[ids],np.repeat(a[None,:],len(ids),axis=0))
  for index,q in zip(ids,closest):
   if not np.isfinite(q).all():continue
   if math.hypot(q[0]-a[0],q[2]-a[2])>.35:
    t=tri[index];E=np.column_stack((t[1]-t[0],t[2]-t[0]));start=np.linalg.lstsq(E,q-t[0],rcond=None)[0];start=np.clip(start,0,1);start=start/max(1,float(start.sum()))
    def obj(uv):d=t[0]+E@uv-a;return float(d@d)
    def grad(uv):return 2*E.T@(t[0]+E@uv-a)
    def radial(uv):d=(t[0]+E@uv-a)[[0,2]];return .35**2-float(d@d)
    sol=minimize(obj,start,jac=grad,bounds=[(0,1),(0,1)],constraints=[{'type':'ineq','fun':lambda uv:1-uv.sum(),'jac':lambda uv:np.array([-1.,-1.])},{'type':'ineq','fun':radial}],method='SLSQP',options={'maxiter':64,'ftol':1e-12})
    if not sol.success:solver_failures.append({'node':node,'triangle':int(index),'message':str(sol.message)});continue
    q=t[0]+E@sol.x
   if np.linalg.norm(q-a)>.5:continue
   collect(q,'triangle_projection',int(index))
   # Interior witness avoids ambiguous boundary membership; it never relaxes any bound.
   collect(q+1e-4*(tri[index].mean(axis=0)-q),'triangle_projection_interior',int(index))
 result={'node':node,'anchor_kind':kind,'components':found,'triangles_considered':len(ids),'queries':tested,'camera_projection_deferred':False};catalog[key]=result;return result
rows=[];candidate_tasks=[];controls=0
for t in tasks:
 if t['status']=='READY_FOR_NATIVE_MOTION':
  for node,p in zip(t['original_viewpoint_path'],t['targets']):
   a,kind,info=anchor_for(node,p);assert math.dist(p,a)<=.5 and pf.is_navigable(p) and math.dist(p,list(pf.snap_point(p)))<=1e-5
  assert all(connected(a,b) for a,b in zip(t['targets'],t['targets'][1:]));controls+=1;candidate_tasks.append(t);rows.append({'task_key':t['task_key'],'status':'UNCHANGED_READY_CONTROL'});continue
 opts=[options(n,p) for n,p in zip(t['original_viewpoint_path'],t['targets'])];common=set.intersection(*(set(x['components']) for x in opts)) if opts else set()
 if common:
  label=min(common,key=lambda c:sum(x['components'][c]['rank']*1000+x['components'][c]['source_distance'] for x in opts));choices=[x['components'][label] for x in opts];points=[x['position'] for x in choices];assert all(connected(a,b) for a,b in zip(points,points[1:]));candidate_tasks.append({**t,'targets':points,'status':'STATIC_CANDIDATE_PENDING_SOURCE_BODY_AND_MOTION'});rows.append({'task_key':t['task_key'],'status':'RECOVERED_STATIC_CANDIDATE_NOT_ACCEPTED','choices':choices})
 else:candidate_tasks.append(t);rows.append({'task_key':t['task_key'],'status':'BLOCKED_PRESERVED','component_counts':[len(x['components']) for x in opts]})
 if len(rows)%50==0:atomic_json(O/'state.json',{'status':'RUNNING','tasks':len(rows),'catalog_entries':len(catalog)})
counts=dict(collections.Counter(r['status'] for r in rows));assert len(rows)==635 and controls==383;atomic_json(O/'candidate_tasks.json',{'tasks':candidate_tasks,'scope':'No actual input replacement; all635 retained'});atomic_json(O/'validation.json',{'status':'COMPLETE_GEOMETRIC_COMPONENT_PROJECTION_NOT_ACCEPTANCE','scene':sc,'tasks':635,'counts':counts,'rows':rows,'candidate_catalog':list(catalog.values()),'constrained_solver_failures':solver_failures,'native_components_seen':len(reps),'native_path_queries':len(edgecache),'parent_manifest_sha256':digest(parent),'profile_sha256':m['profile_sha256'],'mesh_sha256':asset['navmesh_sha256'],'native_mapping_sha256':digest(native_path),'identity_mapping_sha256':digest(identity_path),'trimesh_version':trimesh.__version__,'trimesh_closest_point_source_sha256':digest(Path(trimesh.triangles.__file__)),'script_sha256':digest(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Same<=0.5m source sphere and<=0.350001m horizontal bound for new proposals. Deterministic geometry projection, not expanded sampling. Current READY controls unchanged. Optimizer/numerical misses remain inconclusive; no source-body, floor/landmark semantics or actual-motion acceptance from this file. No annotation/mesh changes.'});atomic_json(O/'state.json',{'status':'COMPLETE','counts':counts,'solver_failures':len(solver_failures)});print(counts,'solver_failures',len(solver_failures))
