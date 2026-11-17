"""Read-only frame audit for camera-only fallback seeds. Does not replace any anchor or bound."""
import os,sys,json,math,ast,datetime,collections
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'));from workspace import atomic_json,digest
import habitat_sim,psutil
u=psutil.cpu_percent(interval=1,percpu=True);eligible=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<25];assert eligible;os.sched_setaffinity(0,[min(eligible,key=lambda i:u[i])])
B=R/'outputs/landmark-connectivity';O=B/'camera-seed-frame-audit-v1';O.mkdir(exist_ok=False);snapshot=R/'outputs/awarevln-r2r-valunseen-endpoint9-20261015-v2/shards/shard-06/attempt-01/effective-config.yaml'
# This artifact is a YACS display snapshot, not fully loadable YAML (tuple reprs exist).
stack=[];sensor=None
for line in snapshot.read_text().splitlines():
 if not line.strip() or ':' not in line:continue
 indent=len(line)-len(line.lstrip());key,value=line.strip().split(':',1);value=value.strip()
 while stack and stack[-1][0]>=indent:stack.pop()
 path=[k for _,k in stack]+[key]
 if path==['TASK_CONFIG','SIMULATOR','RGB_SENSOR','POSITION']:sensor=ast.literal_eval(value)
 if not value:stack.append((indent,key))
assert sensor==[0,1.25,0];height=sensor[1];parent=B/'full-native-v11/manifest.json';m=json.loads(parent.read_text());profile=json.loads(Path(m['profile_path']).read_text());identity_path=B/'published-identity-nodes.json';identity={(r['scene'],r['node']):r for r in json.loads(identity_path.read_text())['nodes']};held=set(json.loads((B/'constraint-blockers.json').read_text())['task_keys']);nodes={}
for t in m['tasks']:
 for node,p in zip(t['original_viewpoint_path'],t['targets']):
  info=identity[(t['scene'],node)]
  if info['method']!='UNRESOLVED_no_direct_identity':continue
  k=(t['scene'],node);entry=nodes.setdefault(k,{'camera':info['camera_position'],'occurrences':[]});entry['occurrences'].append({'task_key':t['task_key'],'target':p,'task_status':t['status'],'held114':t['task_key'] in held})
assert len(nodes)==96;finders={};rows=[]
for (sc,node),entry in sorted(nodes.items()):
 if sc not in finders:
  asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path']);finders[sc]=pf
 pf=finders[sc];cam=entry['camera'];nominal=[cam[0],cam[1]-height,cam[2]];q=list(pf.snap_point(nominal));finite=all(math.isfinite(v) for v in q);horizontal=math.hypot(q[0]-cam[0],q[2]-cam[2]) if finite else None;drop=cam[1]-q[1] if finite else None;bound=finite and horizontal<.5 and 0<=drop<=2;exact=finite and pf.is_navigable(q) and math.dist(q,list(pf.snap_point(q)))<=1e-5;nominal_distance=math.dist(q,nominal) if finite else None;occ=[]
 for r in entry['occurrences']:
  old=r['target'];oldfinite=old is not None and all(math.isfinite(v) for v in old);old_error=abs(old[1]+height-cam[1]) if oldfinite else None;new_error=abs(q[1]+height-cam[1]) if finite else None;distance=math.dist(old,q) if oldfinite and finite else None;potential=bool(oldfinite and bound and exact and nominal_distance<=.5 and distance>.5 and new_error+1e-6<old_error)
  occ.append({**r,'old_render_camera_vertical_error':old_error,'new_render_camera_vertical_error':new_error,'old_derived_target_to_new_seed_distance':distance,'finite_old_anchor_may_lock_out_better_camera_frame':potential})
 rows.append({'scene':sc,'node':node,'raw_camera_position':cam,'nominal_agent_position':nominal,'new_snap_candidate':q if finite else None,'unchanged_raw_camera_bounds_pass':bool(bound),'exact_active_mesh_member':bool(exact),'distance_to_sensor_based_nominal':nominal_distance,'occurrences':occ})
flagged={r['task_key'] for n in rows for r in n['occurrences'] if r['finite_old_anchor_may_lock_out_better_camera_frame']};blocked={r['task_key'] for n in rows for r in n['occurrences'] if r['finite_old_anchor_may_lock_out_better_camera_frame'] and r['task_status']=='STATIC_BLOCKED_PRESERVED'}
report={'status':'COMPLETE_CAMERA_FRAME_DIAGNOSTIC_NO_MAPPING_CHANGE','camera_only_nodes':96,'flagged_unique_tasks':len(flagged),'flagged_blocked_tasks':len(blocked),'flagged_task_keys':sorted(flagged),'flagged_blocked_task_keys':sorted(blocked),'sensor_position':sensor,'effective_snapshot_sha256':digest(snapshot),'manifest_sha256':digest(parent),'profile_sha256':m['profile_sha256'],'identity_mapping_sha256':digest(identity_path),'rows':rows,'script_sha256':digest(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'A sensor-height-based probe is not a new accepted source anchor. All old raw-camera bounds retained; current-derived-anchor displacement>0.5 is flagged rather than waived. Requires source geometry, floor/landmark semantics, whole-route/nonregression and actual motion review before any correction. No original/derived running data modified; held114 evidence unchanged.'};atomic_json(O/'validation.json',report);print('camera nodes',96,'flagged tasks',len(flagged),'blocked',len(blocked));print([(r['scene'],r['node'],sum(x['finite_old_anchor_may_lock_out_better_camera_frame'] for x in r['occurrences'])) for r in rows if any(x['finite_old_anchor_may_lock_out_better_camera_frame'] for x in r['occurrences'])])
