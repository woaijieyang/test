import os,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,digest,atomic_json
os.environ['CUDA_VISIBLE_DEVICES']='7';os.environ['OMP_NUM_THREADS']='2';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2])
import habitat_sim
report=json.loads(Path('outputs/landmark-connectivity/candidate-audit.json').read_text());base=json.loads(Path('data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json').read_text())
out=ROOT/'data/derived/navmeshes/landmark-fine-candidate-v1';out.mkdir(exist_ok=True)
profile={'profile_id':'landmark-fine-candidate-v1','agent':{'height':1.5,'radius':.1},'status':'DIAGNOSTIC_NOT_ACCEPTED','assets':{}}
for row in report['scenes']:
 scene=row['scene'];key=f'mp3d/{scene}/{scene}.glb';glb=ROOT/'data/scene_datasets'/key
 if not row['affected_episodes']:
  asset=base['assets'].get(key,{'scene_path':str(glb),'navmesh_path':str(glb.with_suffix('.navmesh')),'navmesh_sha256':digest(glb.with_suffix('.navmesh'))});profile['assets'][key]=asset;continue
 mesh=out/(scene+'.navmesh');started=time.time()
 if not mesh.exists():
  cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id=str(glb);cfg.create_renderer=True;cfg.gpu_device_id=0;cfg.enable_physics=False
  agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;sensor=habitat_sim.SensorSpec();sensor.uuid="build_rgb";sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[16,16];sensor.position=[0,1.25,0];agent.sensor_specifications=[sensor]
  sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]))
  try:
   settings=habitat_sim.NavMeshSettings();settings.set_defaults();settings.agent_height=1.5;settings.agent_radius=.1;settings.cell_height=.05;settings.cell_size=.025;settings.region_min_size=40;settings.region_merge_size=40
   assert sim.recompute_navmesh(sim.pathfinder,settings);assert sim.pathfinder.save_nav_mesh(str(mesh))
  finally:sim.close()
 profile['assets'][key]={'scene_path':str(glb),'navmesh_path':str(mesh),'navmesh_sha256':digest(mesh),'settings':{'agent_height':1.5,'agent_radius':.1,'cell_height':.05,'cell_size':.025,'region_min_size':40,'region_merge_size':40}}
 atomic_json(out/'profile.partial.json',profile);print(scene,round(time.time()-started,2),flush=True)
atomic_json(out/'profile.json',profile)
