import os,sys,json,math,subprocess
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
from bounded_camera_seed import select_camera_seed
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='4';os.environ['OMP_NUM_THREADS']='2';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[28:30]);os.nice(15)
mem,util=map(int,subprocess.check_output(['nvidia-smi','--id=4','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip().split(','));assert mem<1024 and util<10
import habitat_sim
b=ROOT/'outputs/landmark-connectivity';out=b/'mJX-height075-v1';out.mkdir(exist_ok=False);sc='mJXqzFtmKg4';cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id=str(ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb');cfg.create_renderer=True;cfg.enable_physics=False;cfg.gpu_device_id=0;a=habitat_sim.agent.AgentConfiguration();a.height=1.5;a.radius=.1;sensor=habitat_sim.SensorSpec();sensor.uuid='build';sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[16,16];a.sensor_specifications=[sensor];sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[a]));identity=json.loads((b/'published-identity-nodes.json').read_text())['nodes'];m=json.loads((b/'full-native-v8/manifest.json').read_text());tasks=[t for t in m['tasks'] if t['scene']==sc];variants=[]
try:
 for cellheight in [.075]:
  climb=.3
  ns=habitat_sim.NavMeshSettings();ns.set_defaults();ns.agent_height=1.5;ns.agent_radius=.1;ns.cell_size=.025;ns.cell_height=cellheight;ns.agent_max_climb=climb;ns.region_min_size=40;ns.region_merge_size=40;assert sim.recompute_navmesh(sim.pathfinder,ns);pf=sim.pathfinder;mp=out/f'height{cellheight}.navmesh';assert pf.save_nav_mesh(str(mp));seeds={};records=[]
  for node in ['596c721baa6545aba7d244e239d48972','b6bfed9c855f4d67a0ece0a83fc4ef67']:
   x=next(x for x in identity if x['scene']==sc and x['node']==node);q=select_camera_seed(pf,x['camera_position']);seeds[node]=q;records.append({'node':node,'fresh_seed':q})
  passed=regressed=recovered=0
  for t in tasks:
   ps=[]
   for node,p in zip(t['original_viewpoint_path'],t['targets']):
    q=list(pf.snap_point(p)) if p is not None else seeds.get(node)
    if q is None or not all(math.isfinite(v) for v in q) or (p is not None and math.dist(p,q)>.5):q=None
    ps.append(q)
   ok=all(p is not None for p in ps)
   if ok:
    for a0,c in zip(ps,ps[1:]):
     q=habitat_sim.ShortestPath();q.requested_start=a0;q.requested_end=c
     if not pf.find_path(q) or not math.isfinite(q.geodesic_distance):ok=False;break
   old=t['status']=='READY_FOR_NATIVE_MOTION';passed+=ok;regressed+=old and not ok;recovered+=not old and ok
  row={'settings':{'agent_height':1.5,'agent_radius':.1,'cell_size':.025,'cell_height':cellheight,'agent_max_climb':climb,'region_min_size':40,'region_merge_size':40},'mesh_path':str(mp),'mesh_sha256':digest(mp),'seeds':records,'screen_counts':{'passed':passed,'regressed':regressed,'recovered':recovered}};variants.append(row);print(row['screen_counts'],records,flush=True)
finally:sim.close()
atomic_json(out/'summary.json',{'status':'DIAGNOSTIC_NOT_ACCEPTED','variants':variants,'source_sha256':digest(cfg.scene_id),'script_sha256':digest(__file__),'hypothesis':'Fine vertical voxels recover the missing camera but lose six old tasks; coarse0.2 retains six but loses45. Test the remaining midpoint0.075m that divides the fixed1.5m body exactly, constant horizontal grid and climb.','limits':'Projection screen only; exact grounded source bounds, whole-scene nonregression, motion and source geometry required.'})
