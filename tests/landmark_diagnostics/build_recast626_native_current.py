"""Native scene-loader controls for the isolated official Recast626 backport."""
import os,sys,json,subprocess,math,collections,argparse,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='4';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['PYTHONDONTWRITEBYTECODE']='1';os.nice(15)
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
P=argparse.ArgumentParser();P.add_argument('--label',choices=['control','patched']);args=P.parse_args();b=ROOT/'outputs/landmark-connectivity';out=b/'recast626-native-loader-gTV-current-v1';cache=ROOT/'.cache/recast626-isolated-binding-v1';sc='gTV8FGcVJC9';binary='habitat_sim_bindings.cpython-310-x86_64-linux-gnu.so';receipt=json.loads((b/'recast626-isolated-binding-v1/validation.json').read_text());assert receipt['status']=='PASS_ISOLATED_BINARY_CONTROL_AND_IMPORT'
def gpu_idle():
 x=subprocess.check_output(['nvidia-smi','--id=4','--query-gpu=uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip().split(',');active=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid','--format=csv,noheader'],text=True);return int(x[1])<1024 and int(x[2])<10 and x[0].strip() not in active
parent_manifest=json.loads((b/'full-native-v11/manifest.json').read_text());parent_profile=json.loads(Path(parent_manifest['profile_path']).read_text());original_asset=parent_profile['assets']['mp3d/gTV8FGcVJC9/gTV8FGcVJC9.glb'];reference_mesh=Path(original_asset['navmesh_path']);assert digest(reference_mesh)==original_asset['navmesh_sha256'];assert original_asset['build_settings']=={'cell_size':.05,'cell_height':.05,'agent_max_climb':.3,'region_min_size':20,'region_merge_size':20,'agent_height':1.5,'agent_radius':.1}
if args.label:
 assert gpu_idle(),'GPU4 not idle; no work launched'
 import habitat_sim,habitat_sim._ext.habitat_sim_bindings as binding
 expected=cache/args.label/'habitat_sim/_ext'/binary;assert Path(binding.__file__).resolve()==expected and digest(expected)==receipt[args.label+'_binding_sha256']
 gp=ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb';cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id=str(gp);cfg.create_renderer=True;cfg.enable_physics=False;cfg.gpu_device_id=0;agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;sensor=habitat_sim.SensorSpec();sensor.uuid='build';sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[16,16];agent.sensor_specifications=[sensor];sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));ns=habitat_sim.NavMeshSettings();ns.set_defaults();ns.agent_height=1.5;ns.agent_radius=.1;ns.cell_size=.05;ns.cell_height=.05;ns.agent_max_climb=.3;ns.region_min_size=20;ns.region_merge_size=20
 try:
  assert sim.recompute_navmesh(sim.pathfinder,ns);mesh=out/(args.label+'.navmesh');assert not mesh.exists();assert sim.pathfinder.save_nav_mesh(str(mesh))
 finally:sim.close()
 atomic_json(out/(args.label+'-build.json'),{'scene':sc,'scene_sha256':digest(gp),'binding':str(expected),'binding_sha256':digest(expected),'mesh_path':str(mesh),'mesh_sha256':digest(mesh),'script_sha256':digest(__file__),'settings':{'agent_height':1.5,'agent_radius':.1,'cell_size':.05,'cell_height':.05,'agent_max_climb':.3,'region_min_size':20,'region_merge_size':20}});sys.exit(0)
import psutil
usage=psutil.cpu_percent(interval=1,percpu=True);cpus=sorted(sorted(os.sched_getaffinity(0))[:64],key=lambda x:usage[x])[:2];os.sched_setaffinity(0,cpus);out.mkdir(exist_ok=False);atomic_json(out/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'cpu_ids':cpus})
try:
 for label in ['control','patched']:
  atomic_json(out/'state.json',{'status':'BUILDING','label':label});env={**os.environ,'PYTHONPATH':str(cache/label)}
  with (out/(label+'.log')).open('xb') as log:subprocess.run([sys.executable,str(Path(__file__).resolve()),'--label',label],stdout=log,stderr=subprocess.STDOUT,env=env,check=True)
  if label=='control':assert digest(out/'control.navmesh')==digest(reference_mesh),'NATIVE_BYTE_CONTROL_MISMATCH'
 import habitat_sim
 from importlib import util
 spec=util.spec_from_file_location('bounded',ROOT/'tests/landmark_diagnostics/bounded_camera_seed.py');bounded=util.module_from_spec(spec);spec.loader.exec_module(bounded)
 pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(str(out/'patched.navmesh'));m=json.loads((b/'full-native-v8/manifest.json').read_text());identity={(x['scene'],x['node']):x for x in json.loads((b/'published-identity-nodes.json').read_text())['nodes']};counts=collections.Counter();rows=[];pointcache={}
 for t in [x for x in m['tasks'] if x['scene']==sc]:
  points=[]
  for node,p in zip(t['original_viewpoint_path'],t['targets']):
   key=(node,tuple(p) if p is not None else None)
   if key not in pointcache:
    info=identity[(sc,node)];q=list(pf.snap_point(p)) if p is not None else bounded.select_camera_seed(pf,info['camera_position']) if info['method']=='UNRESOLVED_no_direct_identity' else None;pointcache[key]=q if q is not None and all(math.isfinite(v) for v in q) and pf.is_navigable(q) and (p is None or math.dist(p,q)<=.5) else None
   points.append(pointcache[key])
  ok=all(p is not None for p in points)
  if ok:
   for a,c in zip(points,points[1:]):
    path=habitat_sim.ShortestPath();path.requested_start=a;path.requested_end=c
    if not pf.find_path(path) or not math.isfinite(path.geodesic_distance):ok=False;break
  prior=t['status']=='READY_FOR_NATIVE_MOTION';counts['pass' if ok else 'blocked']+=1;counts['regressions']+=prior and not ok;counts['recoveries']+=not prior and ok;rows.append({'task_key':t['task_key'],'candidate_pass':ok,'prior_pass':prior})
 atomic_json(out/'validation.json',{'status':'NATIVE_CONTROL_PASS_STATIC_SCREEN_ONLY','scene':sc,'native_byte_control_match':True,'reference_sha256':digest(reference_mesh),'control_sha256':digest(out/'control.navmesh'),'patched_sha256':digest(out/'patched.navmesh'),'counts':dict(counts),'tasks':rows,'script_sha256':digest(__file__),'binding_receipt_sha256':digest(b/'recast626-isolated-binding-v1/validation.json'),'limitations':'Static initial screen, not full source-bound joint selection, motion or geometry acceptance. No active profile change.'});atomic_json(out/'state.json',{'status':'COMPLETE_NOT_ACCEPTED','counts':dict(counts)});print(dict(counts))
except Exception as e:atomic_json(out/'state.json',{'status':'FAILED','error':repr(e)});raise
