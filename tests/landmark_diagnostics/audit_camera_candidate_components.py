"""Compare camera surface candidates with the unchanged legacy seed/ring components."""
import os,sys,json,math,collections,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'));from workspace import atomic_json,digest
import habitat_sim,psutil
u=psutil.cpu_percent(interval=1,percpu=True);cpus=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<25];assert cpus;os.sched_setaffinity(0,[min(cpus,key=lambda i:u[i])])
B=R/'outputs/landmark-connectivity';O=B/'camera-candidate-components-v1';O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});surface_path=B/'camera-surface-domain-v1/validation.json';surface=json.loads(surface_path.read_text());catalog={(r['scene'],r['node']):r for r in surface['rows']};parent=B/'full-native-v11/manifest.json';m=json.loads(parent.read_text());first_path=B/'full-native-v1/manifest.json';prior={t['task_key']:t for t in json.loads(first_path.read_text())['tasks']};profile=json.loads(Path(m['profile_path']).read_text());assert m['profile_sha256']==surface['profile_sha256'];held=set(json.loads((B/'constraint-blockers.json').read_text())['task_keys']);groups={}
for t in m['tasks']:
 old=prior[t['task_key']];assert len(t['targets'])==len(old['targets'])
 for node,current,previous in zip(t['original_viewpoint_path'],t['targets'],old['targets']):
  if (t['scene'],node) not in catalog:continue
  k=(t['scene'],node,tuple(current) if current is not None else None,tuple(previous) if previous is not None else None);groups.setdefault(k,[]).append({'task_key':t['task_key'],'status':t['status'],'held114':t['task_key'] in held})
rings=[(r*math.cos(i*2*math.pi/n),r*math.sin(i*2*math.pi/n)) for r,n in ((.1,18),(.15,30),(.2,36),(.25,48),(.3,60),(.35,72)) for i in range(n)];finders={};edges={};rows=[]
for (sc,node,current,previous),tasks in sorted(groups.items(),key=lambda x:repr(x[0])):
 if sc not in finders:
  asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path']);finders[sc]=pf
 pf=finders[sc];info=catalog[(sc,node)];cam=info['raw_camera_position'];anchor=current if current is not None else previous if previous is not None else info['old_vertical_query_seed'];old_reps=[];new_reps=[]
 def connected(a,b):
  key=(sc,tuple(a),tuple(b))
  if key not in edges:
   q=habitat_sim.ShortestPath();q.requested_start=a;q.requested_end=b;edges[key]=bool(pf.find_path(q) and math.isfinite(q.geodesic_distance))
  return edges[key]
 def valid(q,ring):
  if anchor is None or not all(math.isfinite(v) for v in q) or not pf.is_navigable(q) or math.dist(q,list(pf.snap_point(q)))>1e-5:return False
  if math.dist(q,anchor)>.5 or (ring and math.hypot(q[0]-anchor[0],q[2]-anchor[2])>.350001):return False
  return math.hypot(q[0]-cam[0],q[2]-cam[2])<.5 and 0<=cam[1]-q[1]<=2
 if anchor is not None:
  seeds=[(p,False) for p in [previous,current,anchor] if p is not None]+[([anchor[0]+dx,anchor[1],anchor[2]+dz],True) for dx,dz in rings]
  for seed,ring in seeds:
   q=list(pf.snap_point(seed))
   if valid(q,ring) and not any(connected(q,r) for r in old_reps):old_reps.append(q)
  for candidate in info['surface_candidates']:
   q=candidate['position']
   if not valid(q,True):continue
   if any(connected(q,r) for r in old_reps+new_reps):continue
   new_reps.append(q)
 rows.append({'scene':sc,'node':node,'current':current,'previous':previous,'anchor':anchor,'old_component_representatives':old_reps,'new_component_representatives':new_reps,'affected_tasks':tasks})
 if len(rows)%50==0:atomic_json(O/'state.json',{'status':'RUNNING','contexts':len(rows),'expected_contexts':len(groups),'contexts_with_new_components':sum(bool(r['new_component_representatives']) for r in rows)})
newrows=[r for r in rows if r['new_component_representatives']];keys={t['task_key'] for r in newrows for t in r['affected_tasks']};blocked={t['task_key'] for r in newrows for t in r['affected_tasks'] if t['status']=='STATIC_BLOCKED_PRESERVED' and not t['held114']};result={'status':'COMPLETE_COMPONENT_COMPARISON_NOT_MAPPING_ACCEPTANCE','nodes':96,'contexts':len(rows),'contexts_with_new_components':len(newrows),'affected_tasks':len(keys),'affected_nonheld_blocked_tasks':len(blocked),'affected_task_keys':sorted(keys),'affected_nonheld_blocked_keys':sorted(blocked),'rows':rows,'native_geodesic_queries':len(edges),'parent_manifest_sha256':digest(parent),'prior_manifest_sha256':digest(first_path),'surface_catalog_sha256':digest(surface_path),'script_sha256':digest(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'New surface points must pass the same old-derived-anchor sphere<=0.5, proposal horizontal<=0.350001 and raw-camera horizontal<0.5/down0..2. Compared against prior/current/anchor and all original rings through native geodesic queries. No new anchor, radius, coordinate or task status adopted; held114 original data/evidence unchanged.'};atomic_json(O/'validation.json',result);atomic_json(O/'state.json',{'status':'COMPLETE','contexts':len(rows),'contexts_with_new_components':len(newrows),'affected_nonheld_blocked_tasks':len(blocked)});print(len(rows),len(newrows),len(blocked))
