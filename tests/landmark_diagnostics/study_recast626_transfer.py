"""Transfer official626 fix to two evidence-prioritized scenes, with native byte controls."""
import os,sys,json,time,subprocess,struct,collections,math,atexit
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'.cache/geometry-tools'));sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
from bounded_camera_seed import select_camera_seed
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='4';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[28:30]);os.nice(15)
import numpy as np,trimesh,habitat_sim
b=ROOT/'outputs/landmark-connectivity';out=b/'recast626-transfer-v1';out.mkdir(exist_ok=False);cache=ROOT/'.cache/recast626-transfer-v1';cache.mkdir(exist_ok=False);binroot=ROOT/'.cache/recast626-navmesh';m=json.loads((b/'full-native-v8/manifest.json').read_text());identity={(x['scene'],x['node']):x for x in json.loads((b/'published-identity-nodes.json').read_text())['nodes']};reports=[];atomic_json(out/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
def state(status,**kw):atomic_json(out/'state.json',{'status':status,'completed_scenes':len(reports),**kw})
def finish():
 if not (out/'summary.json').exists():state('FAILED',reason='See retained log')
atexit.register(finish)
state('RUNNING')
for sc in ['gTV8FGcVJC9','cV4RVeZvu5T']:
 while True:
  parts=subprocess.check_output(['nvidia-smi','--id=4','--query-gpu=uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip().split(',');uuid=parts[0].strip();active=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid','--format=csv,noheader'],text=True)
  if int(parts[1])<1024 and int(parts[2])<10 and uuid not in active:break
  state('WAITING_FOR_IDLE_GPU',scene=sc);time.sleep(120)
 state('NATIVE_CONTROL_BUILD',scene=sc);sceneout=out/sc;sceneout.mkdir();scache=cache/sc;scache.mkdir();gp=ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb';cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id=str(gp);cfg.create_renderer=True;cfg.enable_physics=False;cfg.gpu_device_id=0;agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;sensor=habitat_sim.SensorSpec();sensor.uuid='build';sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[16,16];agent.sensor_specifications=[sensor];sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));ns=habitat_sim.NavMeshSettings();ns.set_defaults();ns.agent_height=1.5;ns.agent_radius=.1;ns.cell_size=.025;ns.cell_height=.1;ns.agent_max_climb=.3;ns.region_min_size=40;ns.region_merge_size=40
 try:assert sim.recompute_navmesh(sim.pathfinder,ns);reference=sceneout/'native-old.navmesh';assert sim.pathfinder.save_nav_mesh(str(reference))
 finally:sim.close()
 mesh=trimesh.load(str(gp),force='scene',process=False).to_geometry();tri=np.asarray(mesh.triangles,dtype='<f4');raw=scache/'raw.bin';raw.write_bytes(struct.pack('<I',len(tri))+tri.tobytes());converted=scache/'native.bin';frame=subprocess.check_output([str(binroot/'frame_export'),str(raw),str(converted)],text=True);(sceneout/'frame.txt').write_text(frame);watch=scache/'watch.txt';watch.write_text('0 0 0\n')
 for label in ['old','upstream626']:
  text=subprocess.check_output([str(binroot/label),str(converted),'.025','.1',str(watch),str(sceneout/(label+'.navmesh'))],text=True);(sceneout/(label+'.log')).write_text(text)
 control=habitat_sim.PathFinder();assert control.load_nav_mesh(str(sceneout/'old.navmesh'));norm=sceneout/'old-normalized.navmesh';assert control.save_nav_mesh(str(norm));match=digest(norm)==digest(reference);row={'scene':sc,'source_sha256':digest(gp),'native_reference_sha256':digest(reference),'control_sha256':digest(norm),'byte_control_match':match}
 if not match:row['status']='CONTROL_MISMATCH';reports.append(row);atomic_json(sceneout/'result.json',row);continue
 pf=habitat_sim.PathFinder();patched=sceneout/'upstream626.navmesh';assert pf.load_nav_mesh(str(patched));counts=collections.Counter();tasks=[];pointcache={}
 for t in [t for t in m['tasks'] if t['scene']==sc]:
  points=[]
  for node,p in zip(t['original_viewpoint_path'],t['targets']):
   key=(node,tuple(p) if p is not None else None)
   if key not in pointcache:
    info=identity[(sc,node)];q=list(pf.snap_point(p)) if p is not None else select_camera_seed(pf,info['camera_position']) if info['method']=='UNRESOLVED_no_direct_identity' else None;pointcache[key]=q if q is not None and all(math.isfinite(v) for v in q) and pf.is_navigable(q) and (p is None or math.dist(p,q)<=.5) else None
   points.append(pointcache[key])
  ok=all(p is not None for p in points)
  if ok:
   for a,c in zip(points,points[1:]):
    path=habitat_sim.ShortestPath();path.requested_start=a;path.requested_end=c
    if not pf.find_path(path) or not math.isfinite(path.geodesic_distance):ok=False;break
  prior=t['status']=='READY_FOR_NATIVE_MOTION';counts['pass' if ok else 'blocked']+=1;counts['regressions']+=prior and not ok;counts['recoveries']+=not prior and ok;tasks.append({'task_key':t['task_key'],'candidate_pass':ok,'prior_pass':prior})
 row.update(status='SCREEN_ONLY_NOT_ACCEPTED',counts=dict(counts),tasks=tasks,patched_mesh_path=str(patched),patched_mesh_sha256=digest(patched));reports.append(row);atomic_json(sceneout/'result.json',row);state('RUNNING',last_scene=sc);print(sc,match,dict(counts),flush=True)
atomic_json(out/'summary.json',{'status':'COMPLETE_NOT_ACCEPTED','scenes':reports,'script_sha256':digest(__file__),'parent_manifest_sha256':digest(b/'full-native-v8/manifest.json'),'limits':'Byte controls plus static screen only. Exact source-bound joint selection, full motion, source geometry and replay required. No adoption or frozen environment changes.'});state('COMPLETE_NOT_ACCEPTED')
