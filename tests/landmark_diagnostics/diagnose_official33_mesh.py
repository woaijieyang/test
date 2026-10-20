"""Four official-reference anchors: controlled rasterization study, fixed body/geometry."""
import os,sys,json,math
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='4';os.environ['OMP_NUM_THREADS']='2';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[10:12]);os.nice(10)
import habitat_sim
b=ROOT/'outputs/landmark-connectivity';out=b/'official33-mesh-study-v2';out.mkdir(exist_ok=False);source=json.loads((b/'official33-anchor-diagnostic.json').read_text());m=json.loads((b/'full-native-v4/manifest.json').read_text());results=[]
variants=[('base05',.05,.05,.2),('horizontal025',.025,.05,.2),('vertical025',.025,.025,.2),('climb03',.025,.025,.3)]
for sc in sorted({r['scene'] for r in source['records']}):
 cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id=str(ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb');cfg.create_renderer=True;cfg.enable_physics=False;cfg.gpu_device_id=0;a=habitat_sim.agent.AgentConfiguration();a.height=1.5;a.radius=.1;sensor=habitat_sim.SensorSpec();sensor.uuid='build';sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[16,16];a.sensor_specifications=[sensor];sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[a]));anchors={n['node']:n['reference'] for r in source['records'] if r['scene']==sc for n in r['missing_nodes']};scene={'scene':sc,'source_sha256':digest(cfg.scene_id),'variants':[]}
 try:
  for name,cs,ch,climb in variants:
   ns=habitat_sim.NavMeshSettings();ns.set_defaults();ns.agent_height=1.5;ns.agent_radius=.1;ns.cell_size=cs;ns.cell_height=ch;ns.agent_max_climb=climb;ns.region_min_size=20;ns.region_merge_size=20;assert sim.recompute_navmesh(sim.pathfinder,ns);pf=sim.pathfinder;mp=out/f'{sc}-{name}.navmesh';assert pf.save_nav_mesh(str(mp));rows=[]
   for node,p in anchors.items():
    offsets=[(0,0)]+[(r*math.cos(i*2*math.pi/n),r*math.sin(i*2*math.pi/n)) for r,n in ((.1,18),(.15,30),(.2,36),(.25,48),(.3,60),(.35,72)) for i in range(n)];valid={}
    for dx,dz in offsets:
     q=list(pf.snap_point([p[0]+dx,p[1],p[2]+dz]))
     if not all(math.isfinite(x) for x in q) or not pf.is_navigable(q) or math.dist(q,p)>.5 or math.dist(q,list(pf.snap_point(q)))>1e-5:continue
     if (dx or dz) and math.hypot(q[0]-p[0],q[2]-p[2])>.350001:continue
     valid[tuple(round(x,6) for x in q)]=q
    rows.append({'node':node,'anchor':p,'candidates':list(valid.values())})
   scene['variants'].append({'name':name,'settings':{'cell_size':cs,'cell_height':ch,'agent_max_climb':climb,'region_min_size':20,'region_merge_size':20,'agent_height':1.5,'agent_radius':.1},'mesh_path':str(mp),'mesh_sha256':digest(mp),'records':rows});print(sc,name,[(r['node'],len(r['candidates'])) for r in rows],flush=True)
 finally:sim.close()
 results.append(scene);atomic_json(out/'partial.json',results)
atomic_json(out/'summary.json',{'status':'DIAGNOSTIC_COMPLETE_NOT_ACCEPTED','results':results,'script_sha256':digest(__file__),'limits':'One changed rasterization/climb factor per consecutive variant; body and geometry fixed. Candidate existence is not route or motion acceptance. No live profile changed.'})

