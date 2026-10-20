import os,sys,json,subprocess
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
from bounded_camera_seed import select_camera_seed
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='4';os.environ['OMP_NUM_THREADS']='2';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[28:30]);os.nice(15)
mem,util=map(int,subprocess.check_output(['nvidia-smi','--id=4','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip().split(','));assert mem<1024 and util<10
import habitat_sim
b=ROOT/'outputs/landmark-connectivity';out=b/'mJX-region-control-v1';out.mkdir(exist_ok=False);sc='mJXqzFtmKg4';cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id=str(ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb');cfg.create_renderer=True;cfg.enable_physics=False;cfg.gpu_device_id=0;a=habitat_sim.agent.AgentConfiguration();a.height=1.5;a.radius=.1;sensor=habitat_sim.SensorSpec();sensor.uuid='build';sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[16,16];a.sensor_specifications=[sensor];sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[a]));ns=habitat_sim.NavMeshSettings();ns.set_defaults();ns.agent_height=1.5;ns.agent_radius=.1;ns.cell_size=.025;ns.cell_height=.025;ns.agent_max_climb=.3;ns.region_min_size=0;ns.region_merge_size=40
assert sim.recompute_navmesh(sim.pathfinder,ns);mp=out/'mJXqzFtmKg4.navmesh';assert sim.pathfinder.save_nav_mesh(str(mp));identity=json.loads((b/'published-identity-nodes.json').read_text())['nodes'];records=[]
for node in ['596c721baa6545aba7d244e239d48972','b6bfed9c855f4d67a0ece0a83fc4ef67']:
 x=next(x for x in identity if x['scene']==sc and x['node']==node);q=select_camera_seed(sim.pathfinder,x['camera_position']);records.append({'node':node,'camera':x['camera_position'],'fresh_candidate':q});print(records[-1],flush=True)
sim.close();atomic_json(out/'summary.json',{'status':'DIAGNOSTIC_COMPLETE_NOT_ACCEPTED','scene':sc,'mesh_path':str(mp),'mesh_sha256':digest(mp),'source_sha256':digest(cfg.scene_id),'settings':{'agent_height':1.5,'agent_radius':.1,'cell_size':.025,'cell_height':.025,'agent_max_climb':.3,'region_min_size':0,'region_merge_size':40},'records':records,'script_sha256':digest(__file__),'limits':'Single-factor region deletion control; restoring a local island is not whole-route acceptance. All original constraints and records retained.'})
