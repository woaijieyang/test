import os,json,sys,time,collections,math
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
os.environ['CUDA_VISIBLE_DEVICES']='7';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2])
import habitat_sim
nodes=json.loads(Path('outputs/landmark-connectivity/fine-candidate-nodes.json').read_text())['nodes'];out=ROOT/'outputs/landmark-connectivity/mesh-search';out.mkdir(exist_ok=True)
variants={'fine05_climb02':(.025,.05,.2,40),'fine05_climb03':(.025,.05,.3,40),'fine025_climb02':(.025,.025,.2,40),'coarse05_climb02':(.05,.05,.2,20),'fine05_regions0':(.025,.05,.2,0)}
for sc in ('XcA2TqTSSAj','kEZ7cmS4wCh','82sE5b5pLXE'):
 rows=[r for r in nodes if r['scene']==sc];pairs=set()
 for split in ('train','val_seen','val_unseen'):
  for row in json.loads((Path('/data/zy/vln/data/raw_data/landmark-rxr')/f'LandmarkRxR_{split}.json').read_text()):
   if row['scan']!=sc:continue
   for path in [row['path'],*row['sub_paths']]:pairs.update(zip(path,path[1:]));pairs.add((path[0],path[-1]))
 cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id=str(ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb');cfg.create_renderer=True;cfg.enable_physics=False;cfg.gpu_device_id=0
 agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;sensor=habitat_sim.SensorSpec();sensor.uuid='build_rgb';sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[16,16];sensor.position=[0,1.25,0];agent.sensor_specifications=[sensor]
 sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));summary=[]
 try:
  for name,(cs,ch,climb,region) in variants.items():
   settings=habitat_sim.NavMeshSettings();settings.set_defaults();settings.agent_height=1.5;settings.agent_radius=.1;settings.cell_height=ch;settings.cell_size=cs;settings.agent_max_climb=climb;settings.region_min_size=region;settings.region_merge_size=region
   assert sim.recompute_navmesh(sim.pathfinder,settings);mesh=out/f'{sc}-{name}.navmesh';assert sim.pathfinder.save_nav_mesh(str(mesh));pf=sim.pathfinder;points={};large=0
   for row in rows:
    seed=row['candidate_seed'];point=seed if pf.is_navigable(seed) else list(pf.snap_point(seed));points[row['node']]=point
    if not all(math.isfinite(v) for v in point) or math.hypot(point[0]-seed[0],point[2]-seed[2])>.25 or abs(point[1]-seed[1])>.2:large+=1
   failed=[]
   for n1,n2 in sorted(pairs):
    q=habitat_sim.ShortestPath();q.requested_start=points[n1];q.requested_end=points[n2]
    if not pf.find_path(q) or not math.isfinite(q.geodesic_distance):failed.append([n1,n2])
   summary.append({'variant':name,'failed_pairs':failed,'large_projection_nodes':large,'pairs':len(pairs),'mesh_sha256':digest(mesh),'settings':{'cell_size':cs,'cell_height':ch,'agent_max_climb':climb,'region_size':region}});print(sc,name,len(failed),large,flush=True)
   atomic_json(out/f'{sc}.json',summary)
 finally:sim.close()
