"""Export exactly the native VFua build input through the already verified observation-only binding."""
import os,sys,json,subprocess,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='4';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['PYTHONDONTWRITEBYTECODE']='1';os.nice(15)
R=Path.cwd();C=R/'.cache/native-stage-trace-xc-v1';B=R/'outputs/landmark-connectivity';O=B/'vfua-native-geometry-v1';O.mkdir(exist_ok=False);sys.path[:0]=[str(C),str(R/'scripts')]
from workspace import atomic_json,digest
import psutil
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,sorted(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])[:2]);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
try:
 x=subprocess.check_output(['nvidia-smi','--id=4','--query-gpu=uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip().split(',');active=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid','--format=csv,noheader'],text=True);assert int(x[1])<1024 and int(x[2])<10 and x[0].strip() not in active,'GPU4 not idle'
 import habitat_sim,habitat_sim._ext.habitat_sim_bindings as binding
 receipt=json.loads((B/'native-stage-trace-xc-v1/state.json').read_text());assert Path(binding.__file__).resolve()==Path(receipt['binding']) and digest(binding.__file__)==receipt['binding_sha256']
 parent=B/'full-native-v10/manifest.json';m=json.loads(parent.read_text());p=json.loads(Path(m['profile_path']).read_text());sc='VFuaQ6m2Qom';asset=p['assets'][f'mp3d/{sc}/{sc}.glb'];audit=B/'full-native-v10/source-body-audit.json';a=json.loads(audit.read_text());watch=next(row['position'] for row in a['contacts'] if any(h['max_height']>.3 for h in row['hits']) and any(o['fraction'] in (0.,1.) for o in row['occurrences']));gp=R/f'data/scene_datasets/mp3d/{sc}/{sc}.glb';assert digest(gp)==a['scene_sha256']
 os.environ['CASE1_NAV_TRACE_PREFIX']=str(O/'native');os.environ['CASE1_NAV_TRACE_WATCH']=' '.join(map(str,watch));atomic_json(O/'state.json',{'status':'NATIVE_GEOMETRY_EXPORT'})
 cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id=str(gp);cfg.create_renderer=True;cfg.enable_physics=False;cfg.gpu_device_id=0;agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;sensor=habitat_sim.SensorSpec();sensor.uuid='build';sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[16,16];agent.sensor_specifications=[sensor];sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));ns=habitat_sim.NavMeshSettings();ns.set_defaults()
 for k,v in asset['build_settings'].items():setattr(ns,k,v)
 try:
  assert sim.recompute_navmesh(sim.pathfinder,ns);dest=O/'control.navmesh';assert sim.pathfinder.save_nav_mesh(str(dest))
 finally:sim.close()
 assert digest(dest)==asset['navmesh_sha256'],'Native byte control mismatch';assert (O/'native-1.bin').exists();assert len(list(O.glob('native-*.bin')))==1
 atomic_json(O/'validation.json',{'status':'PASS_NATIVE_GEOMETRY_EXPORT_BYTE_CONTROL','scene':sc,'scene_sha256':digest(gp),'native_geometry_path':str(O/'native-1.bin'),'native_geometry_sha256':digest(O/'native-1.bin'),'reference_mesh_sha256':asset['navmesh_sha256'],'observed_mesh_sha256':digest(dest),'parent_manifest_sha256':digest(parent),'profile_sha256':digest(m['profile_path']),'binding_sha256':digest(binding.__file__),'script_sha256':digest(__file__),'limits':'Geometry export provenance only. Existing source-guard workers continue unchanged; this native input supports a separate independent audit, not automatic acceptance.'});atomic_json(O/'state.json',{'status':'PASS_NATIVE_GEOMETRY_EXPORT_BYTE_CONTROL'})
except Exception as e:atomic_json(O/'state.json',{'status':'FAILED','error':repr(e)});raise
