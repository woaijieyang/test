"""Export exactly the native VFua build input through the already verified observation-only binding."""
import os,sys,json,subprocess,datetime,argparse,re
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--scene',required=True);args=parser.parse_args();assert re.fullmatch(r'[A-Za-z0-9]{11}',args.scene);
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='4';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['PYTHONDONTWRITEBYTECODE']='1';os.nice(15)
R=Path.cwd();C=R/'.cache/native-stage-trace-xc-v1';B=R/'outputs/landmark-connectivity';O=B/f'full-source-native-{args.scene}-v1';O.mkdir(exist_ok=False);sys.path[:0]=[str(C),str(R/'scripts')]
from workspace import atomic_json,digest
import psutil
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,sorted(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])[:2]);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
try:
 x=subprocess.check_output(['nvidia-smi','--id=4','--query-gpu=uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip().split(',');active=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid','--format=csv,noheader'],text=True);assert int(x[1])<1024 and int(x[2])<10 and x[0].strip() not in active,'GPU4 not idle'
 import habitat_sim,habitat_sim._ext.habitat_sim_bindings as binding
 receipt=json.loads((B/'native-stage-trace-xc-v1/state.json').read_text());assert Path(binding.__file__).resolve()==Path(receipt['binding']) and digest(binding.__file__)==receipt['binding_sha256']
 parent=B/'full-native-v11/manifest.json';m=json.loads(parent.read_text());p=json.loads(Path(m['profile_path']).read_text());sc=args.scene;asset=p['assets'][f'mp3d/{sc}/{sc}.glb'];screen=B/'full-source-geometry-v1/scenes'/sc/'validation.json';a=json.loads(screen.read_text());candidates=[c for r in a['rows'] for c in r['contact_examples'] if c['kind']=='ACTUAL_POSITION'];watch=max(candidates,key=lambda c:c['max_height'])['position'];gp=R/f'data/scene_datasets/mp3d/{sc}/{sc}.glb';assert digest(gp)==a['scene_sha256']
 os.environ['CASE1_NAV_TRACE_PREFIX']=str(O/'native');os.environ['CASE1_NAV_TRACE_WATCH']=' '.join(map(str,watch));atomic_json(O/'state.json',{'status':'NATIVE_GEOMETRY_EXPORT'})
 cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id=str(gp);cfg.create_renderer=True;cfg.enable_physics=False;cfg.gpu_device_id=0;agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;sensor=habitat_sim.SensorSpec();sensor.uuid='build';sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[16,16];agent.sensor_specifications=[sensor];sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));ns=habitat_sim.NavMeshSettings();ns.set_defaults()
 ns.agent_height=1.5;ns.agent_radius=.1 # Export-only build, never used as a candidate or assumed original settings
 try:
  assert sim.recompute_navmesh(sim.pathfinder,ns);dest=O/'control.navmesh';assert sim.pathfinder.save_nav_mesh(str(dest))
 finally:sim.close()
 assert (O/'native-1.bin').exists();assert len(list(O.glob('native-*.bin')))==1
 atomic_json(O/'validation.json',{'status':'NATIVE_SOURCE_EXPORT_ONLY_NO_ORIGINAL_MESH_CONTROL','scene':sc,'scene_sha256':digest(gp),'native_geometry_path':str(O/'native-1.bin'),'native_geometry_sha256':digest(O/'native-1.bin'),'reference_mesh_sha256':asset['navmesh_sha256'],'observed_mesh_sha256':digest(dest),'parent_manifest_sha256':digest(parent),'profile_sha256':digest(m['profile_path']),'binding_sha256':digest(binding.__file__),'script_sha256':digest(__file__),'export_settings':{k:getattr(ns,k) for k in ['agent_height','agent_radius','cell_size','cell_height','agent_max_climb']},'limits':'Native geometry export only using verified observation binding; original build_settings unknown, NO original-mesh reproduction claim. Export-only navmesh is not a candidate and must never enter evaluation. Source geometry read before Recast filtering; original runtime/scene/profile unchanged.'});atomic_json(O/'state.json',{'status':'NATIVE_SOURCE_EXPORT_ONLY_NO_ORIGINAL_MESH_CONTROL'})
except Exception as e:atomic_json(O/'state.json',{'status':'FAILED','error':repr(e)});raise
