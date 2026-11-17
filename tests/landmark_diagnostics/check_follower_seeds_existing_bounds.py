"""Check Follower geometric seeds under unchanged frozen source bounds and native geometry."""
import os,sys,json,struct,math,collections,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from bounded_camera_seed import select_camera_seed
from swept_cylinder_reference import triangle_linear_sweep_distance
import numpy as np,habitat_sim,psutil
u=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:u[i])]);B=R/'outputs/landmark-connectivity';O=B/'follower-seed-existing-bounds-v1';O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});parent_path=B/'full-native-v11/manifest.json';parent=json.loads(parent_path.read_text());parent_sha=digest(parent_path);prior={t['task_key']:t for t in json.loads((B/'full-native-v1/manifest.json').read_text())['tasks']};proof_path=B/'follower-source-correspondence-v1/validation.json';proof=json.loads(proof_path.read_text());extra={(r['scene'],r['node']):r for r in proof['new_candidates']};assert len(extra)==211;identity={(r['scene'],r['node']):r for r in json.loads((B/'published-identity-nodes.json').read_text())['nodes']};held=set(json.loads((B/'constraint-blockers.json').read_text())['task_keys']);profile=json.loads(Path(parent['profile_path']).read_text());catalog={r['scene']:r for r in json.loads((B/'native-source-catalog-v1/catalog.json').read_text())['scenes']};contexts=collections.defaultdict(dict);occurrences=collections.defaultdict(list)
for t in parent['tasks']:
 if t['status']!='STATIC_BLOCKED_PRESERVED' or t['task_key'] in held:continue
 for index,node in enumerate(t['original_viewpoint_path']):
  if (t['scene'],node) not in extra:continue
  current=t['targets'][index];previous=prior[t['task_key']]['targets'][index];key=(node,None if current is None else tuple(current),None if previous is None else tuple(previous));contexts[t['scene']][key]={'node':node,'current':current,'previous':previous};occurrences[(t['scene'],key)].append({'task_key':t['task_key'],'reference_index':index})
reports=[];task_set=set()
for scene,items in sorted(contexts.items()):
 asset=profile['assets'][f'mp3d/{scene}/{scene}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path']);native=catalog[scene];assert digest(native['native_geometry_path'])==native['native_geometry_sha256'];raw=Path(native['native_geometry_path']).read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);v=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=v[ix].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);body_cache={}
 for key,item in items.items():
  node=item['node'];info=identity[(scene,node)];candidate=extra[(scene,node)];q=list(pf.snap_point(candidate['position']));anchor=info['position'] if info['method']!='UNRESOLVED_no_direct_identity' else item['current'] if item['current'] is not None else item['previous'] if item['previous'] is not None else select_camera_seed(pf,info['camera_position']);kind=info['method'] if info['method']!='UNRESOLVED_no_direct_identity' else 'bounded_camera_projection';reasons=[]
  if anchor is None:reasons.append('no_existing_bounded_anchor')
  if not all(math.isfinite(x) for x in q) or not pf.is_navigable(q) or math.dist(q,list(pf.snap_point(q)))>1e-5:reasons.append('not_actual_native_mesh_point')
  if anchor is not None and all(math.isfinite(x) for x in q):
   if math.dist(q,anchor)>.5:reasons.append('outside_existing_source_sphere')
   if math.hypot(q[0]-anchor[0],q[2]-anchor[2])>.350001:reasons.append('outside_existing_extra_proposal_horizontal_bound')
  if kind=='bounded_camera_projection' and all(math.isfinite(x) for x in q):
   c=info['camera_position']
   if math.hypot(q[0]-c[0],q[2]-c[2])>=.5 or not 0<=c[1]-q[1]<=2:reasons.append('outside_existing_camera_bounds')
  hits=[]
  if not reasons:
   qkey=tuple(q)
   if qkey not in body_cache:
    p=np.array(q);ids=np.flatnonzero((lo[:,0]<p[0]+.1)&(hi[:,0]>p[0]-.1)&(lo[:,2]<p[2]+.1)&(hi[:,2]>p[2]-.1)&(lo[:,1]<p[1]+1.5)&(hi[:,1]>p[1]+1e-5));body_cache[qkey]=[int(j) for j in ids if triangle_linear_sweep_distance(tri[j],p,p)<.1-1e-6]
   hits=body_cache[qkey]
   if hits:reasons.append('source_body_contact')
  associated=occurrences[(scene,key)];task_set.update(r['task_key'] for r in associated);same_component=None;current=item['current']
  if not reasons and current is not None and pf.is_navigable(current) and math.dist(current,list(pf.snap_point(current)))<=1e-5:
   path=habitat_sim.ShortestPath();path.requested_start=current;path.requested_end=q;same_component=bool(pf.find_path(path) and math.isfinite(path.geodesic_distance))
  reports.append({'scene':scene,'node':node,'current':current,'previous':item['previous'],'existing_anchor':anchor,'existing_anchor_kind':kind,'follower_geometric_seed':candidate['position'],'projected_candidate':q if all(math.isfinite(x) for x in q) else None,'status':'ELIGIBLE_EXTRA_SEED_NOT_ROUTE_PROOF' if not reasons else 'REJECTED_BY_UNCHANGED_GATES','reasons':reasons,'source_contact_triangles':hits,'same_component_as_existing_exact_current_point':same_component,'task_occurrences':associated,'mesh_sha256':asset['navmesh_sha256'],'native_geometry_sha256':native['native_geometry_sha256']})
 atomic_json(O/'state.json',{'status':'RUNNING','scenes_completed':len({r['scene'] for r in reports}),'contexts':len(reports)})
assert digest(parent_path)==parent_sha;eligible=[r for r in reports if not r['reasons']];atomic_json(O/'validation.json',{'status':'COMPLETE_EXISTING_BOUND_FOLLOWER_SEED_CHECK_NOT_REPAIR','source_nodes':211,'affected_scenes':len(contexts),'affected_nonheld_static_tasks':len(task_set),'contexts':len(reports),'eligible_contexts':len(eligible),'eligible_nodes':len({(r['scene'],r['node']) for r in eligible}),'eligible_task_occurrences':sum(len(r['task_occurrences']) for r in eligible),'reason_counts':dict(collections.Counter(x for r in reports for x in r['reasons'])),'records':reports,'parent_manifest_sha256':parent_sha,'follower_source_audit_sha256':digest(proof_path),'script_sha256':digest(__file__),'limits':'No inferred Follower coordinate upgraded to source identity; original published/camera/previous anchors and all0.5/.350001/body gates retained. CurrentREADY andheld114 untouched. Eligible point is not a new component, whole route, actual motion or accepted repair.'});atomic_json(O/'state.json',{'status':'COMPLETE','eligible_contexts':len(eligible),'eligible_nodes':len({(r['scene'],r['node']) for r in eligible})});print('eligible',len(eligible),'of',len(reports),'affectedtasks',len(task_set))
