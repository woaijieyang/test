"""Independent sanity audit of every stored blocked task; no new candidate search or mutation."""
import os,sys,json,math,datetime,collections
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'));from workspace import atomic_json,digest
import habitat_sim,psutil
u=psutil.cpu_percent(interval=1,percpu=True);eligible=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<25];assert eligible;os.sched_setaffinity(0,[min(eligible,key=lambda i:u[i])])
B=R/'outputs/landmark-connectivity';O=B/'blocked-single-snap-independent-v1';O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});parent=B/'full-native-v11/manifest.json';m=json.loads(parent.read_text());profile=json.loads(Path(m['profile_path']).read_text());assert digest(m['profile_path'])==m['profile_sha256'];tasks=[t for t in m['tasks'] if t['status']=='STATIC_BLOCKED_PRESERVED'];assert len(tasks)==3411;native_path=B/'native-mapping.json';identity_path=B/'published-identity-nodes.json';native={(r['scene'],r['node']):r['native_candidates'][0] for r in json.loads(native_path.read_text())['nodes']};identity={(r['scene'],r['node']):r for r in json.loads(identity_path.read_text())['nodes']};held=set(json.loads((B/'constraint-blockers.json').read_text())['task_keys']);finders={};querycache={};pointcache={};reports=[]
for t in tasks:
 sc=t['scene']
 if sc not in finders:
  asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path']);finders[sc]=pf
 pf=finders[sc];issues=[];source_ok=True;mesh_ok=True;original_points=t['targets'];points=[]
 for original in original_points:
  if original is None or len(original)!=3 or not all(math.isfinite(v) for v in original):points.append(None)
  else:
   snap=list(pf.snap_point(original));points.append(snap if all(math.isfinite(v) for v in snap) else None)
 for i,(node,p) in enumerate(zip(t['original_viewpoint_path'],points)):
  if p is None or len(p)!=3 or not all(math.isfinite(v) for v in p):issues.append({'index':i,'kind':'missing_or_nonfinite_target'});source_ok=mesh_ok=False;continue
  info=identity[(sc,node)]
  if (sc,node) in native:anchor=native[(sc,node)];kind='official'
  elif info['method']!='UNRESOLVED_no_direct_identity':anchor=info['position'];kind='published'
  else:anchor=original_points[i];kind='camera'
  if math.dist(p,anchor)>.5:issues.append({'index':i,'kind':'source_anchor_bound','distance':math.dist(p,anchor)});source_ok=False
  if kind=='camera':
   camera=info['camera_position'];horizontal=math.hypot(p[0]-camera[0],p[2]-camera[2]);drop=camera[1]-p[1]
   if horizontal>=.5 or not 0<=drop<=2:issues.append({'index':i,'kind':'camera_bound','horizontal':horizontal,'drop':drop});source_ok=False
  key=(sc,tuple(p))
  if key not in pointcache:
   snap=list(pf.snap_point(p));pointcache[key]={'is_navigable':bool(pf.is_navigable(p)),'snap_residual':math.dist(p,snap) if all(math.isfinite(v) for v in snap) else None,'snap':snap}
  point=pointcache[key]
  if not point['is_navigable'] or point['snap_residual'] is None or point['snap_residual']>1e-5:issues.append({'index':i,'kind':'not_exact_active_mesh_member',**point});mesh_ok=False
 connected=None
 if mesh_ok:
  connected=True
  for i,(a,b) in enumerate(zip(points,points[1:])):
   key=(sc,tuple(a),tuple(b))
   if key not in querycache:
    path=habitat_sim.ShortestPath();path.requested_start=a;path.requested_end=b;found=pf.find_path(path);querycache[key]=bool(found and math.isfinite(path.geodesic_distance))
   if not querycache[key]:connected=False;issues.append({'segment':i,'kind':'direct_native_geodesic_disconnected'})
 classification='SINGLE_SNAP_CANDIDATE_PASSES_ORIGINAL_NAV_SOURCE_GATES' if source_ok and mesh_ok and connected else 'SINGLE_SNAP_DOES_NOT_PASS_ORIGINAL_GATES';reports.append({'task_key':t['task_key'],'scene':sc,'held114':t['task_key'] in held,'classification':classification,'source_bounds_pass':source_ok,'exact_mesh_membership_pass':mesh_ok,'all_direct_native_segments_connected':connected,'issues':issues,'single_snap_targets':points if classification=='SINGLE_SNAP_CANDIDATE_PASSES_ORIGINAL_NAV_SOURCE_GATES' else None})
 if len(reports)%250==0:atomic_json(O/'state.json',{'status':'RUNNING','completed':len(reports),'expected':len(tasks)})
counts=dict(collections.Counter(r['classification'] for r in reports));issue_counts=collections.Counter()
for r in reports:
 for kind in set(x['kind'] for x in r['issues']):issue_counts[kind]+=1
atomic_json(O/'validation.json',{'status':'COMPLETE_STORED_TARGET_SANITY_AUDIT_NOT_INFEASIBILITY_PROOF','tasks':len(reports),'held_records_checked':sum(r['held114'] for r in reports),'counts':counts,'tasks_by_issue_kind':dict(issue_counts),'rows':reports,'native_point_queries':len(pointcache),'native_edge_queries':len(querycache),'manifest_sha256':digest(parent),'profile_sha256':m['profile_sha256'],'native_mapping_sha256':digest(native_path),'identity_mapping_sha256':digest(identity_path),'script_sha256':digest(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'One deterministic native snap per existing finite target, checked against the SAME official/published/old-derived anchors and raw camera bounds. No expanded search or bound change, no body/motion proof, no applied annotation change. Candidates need independent source geometry and complete motion validation; negatives do not prove all mappings impossible.'});atomic_json(O/'state.json',{'status':'COMPLETE','counts':counts,'tasks_by_issue_kind':dict(issue_counts)});print(counts,dict(issue_counts))
