"""Single-factor diagnostic: does region_min_size discard valid support islands?"""
import os,sys,json,math,time
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
assert os.environ.get('CASE1_PROTECTION')
os.environ['CUDA_VISIBLE_DEVICES']='4';os.environ['OMP_NUM_THREADS']='2'
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[10:12]);os.nice(10)
import habitat_sim
b=ROOT/'outputs/landmark-connectivity';out=b/'region-filter-diagnostic-v1';out.mkdir(exist_ok=False)
samples=json.loads((b/'remaining-body-clearance.json').read_text())['records']
manifest=json.loads((b/'full-native-v4/manifest.json').read_text());results=[]
for sc in ['29hnd4uzFmX','2n8kARJN3HM']:
 cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id=str(ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb');cfg.create_renderer=True;cfg.enable_physics=False;cfg.gpu_device_id=0
 agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1
 sensor=habitat_sim.SensorSpec();sensor.uuid='build';sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[16,16];agent.sensor_specifications=[sensor]
 sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));scene={'scene':sc,'variants':[],'source_sha256':digest(cfg.scene_id)}
 try:
  for region in [20,0]:
   s=habitat_sim.NavMeshSettings();s.set_defaults();s.agent_height=1.5;s.agent_radius=.1;s.cell_size=.05;s.cell_height=.05;s.agent_max_climb=.3;s.region_min_size=region;s.region_merge_size=20
   assert sim.recompute_navmesh(sim.pathfinder,s);pf=sim.pathfinder;mesh=out/f'{sc}-minregion{region}.navmesh';assert pf.save_nav_mesh(str(mesh));rows=[]
   for r in samples:
    if r['scene']!=sc:continue
    camera=r['camera_position'];seeds=r['closest_free_candidates']+[[camera[0],camera[1]-.02*i,camera[2]] for i in range(101)];valid={}
    for seed in seeds:
     p=list(pf.snap_point(seed))
     if not all(math.isfinite(x) for x in p) or not pf.is_navigable(p):continue
     if math.hypot(p[0]-camera[0],p[2]-camera[2])>=.5 or not 0<=camera[1]-p[1]<=2:continue
     valid[tuple(round(x,6) for x in p)]=p
    affected=[t for t in manifest['tasks'] if t['scene']==sc and r['node'] in t['original_viewpoint_path']];routes=[]
    for t in affected:
     checks=[]
     for p in valid.values():
      good=True
      for node,target in zip(t['original_viewpoint_path'],t['targets']):
       if node==r['node']:continue
       if target is None:good=False;break
       q=list(pf.snap_point(target))
       if not all(math.isfinite(x) for x in q) or math.dist(q,target)>.5:good=False;break
       path=habitat_sim.ShortestPath();path.requested_start=p;path.requested_end=q
       if not pf.find_path(path) or not math.isfinite(path.geodesic_distance):good=False;break
      checks.append(good)
     routes.append({'task_key':t['task_key'],'any_candidate_connected_to_all_existing_targets':any(checks)})
    rows.append({'node':r['node'],'bounded_candidates':list(valid.values()),'routes':routes})
   scene['variants'].append({'region_min_size':region,'other_settings':{'cell_size':.05,'cell_height':.05,'agent_max_climb':.3,'region_merge_size':20,'agent_height':1.5,'agent_radius':.1},'mesh_sha256':digest(mesh),'records':rows})
   print(sc,region,[(r['node'],len(r['bounded_candidates']),sum(x['any_candidate_connected_to_all_existing_targets'] for x in r['routes'])) for r in rows],flush=True)
 finally:sim.close()
 results.append(scene);atomic_json(out/'partial.json',results)
atomic_json(out/'summary.json',{'status':'DIAGNOSTIC_COMPLETE_NOT_ACCEPTED','results':results,'script_sha256':digest(__file__),'limits':'Only region_min_size changes within each pair. New isolated islands do not count as route repair. No profile or dataset adoption; full original acceptance remains required.'})
