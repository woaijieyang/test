"""Bounded scene-level mesh study; retain all tasks and count regressions explicitly."""
import os,sys,json,math,collections,time
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
os.environ['CUDA_VISIBLE_DEVICES']='7';os.environ['OMP_NUM_THREADS']='2';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[2:4])
import habitat_sim
m=json.loads(Path('outputs/landmark-connectivity/full-native-v1/manifest.json').read_text());tasks=collections.defaultdict(list)
for t in m['tasks']:tasks[t['scene']].append(t)
scenes=[sc for sc,ts in tasks.items() if any(t['status']=='STATIC_BLOCKED_PRESERVED' for t in ts)];aligned={(r['split'],r['instruction_id']):r for r in json.loads(Path('outputs/landmark-connectivity/official-GT-alignment.json').read_text())['records']};identities={(r['scene'],r['node']):r for r in json.loads(Path('outputs/landmark-connectivity/published-identity-nodes.json').read_text())['nodes']};rec={(r['scene'],r['node']):r for r in json.loads(Path('outputs/landmark-connectivity/missing96-bounded-projection.json').read_text())['records']};out=ROOT/'outputs/landmark-connectivity/static-scene-search-v1';out.mkdir(exist_ok=True);variants={'coarse05_climb03':(.05,.05,.3,20),'fine025_climb03':(.025,.025,.3,40),'fine05_climb03':(.025,.05,.3,40)};summary=[]
for sc in sorted(scenes):
 rp=out/(sc+'.json')
 if rp.exists():summary.append(json.loads(rp.read_text()));continue
 seeds={};cameras={}
 for t in tasks[sc]:
  values=[]
  for i,(node,method) in enumerate(zip(t['original_viewpoint_path'],t['mapping_methods'])):
   if method=='official_GT_monotone_alignment':seed=aligned[(t['split'],t['instruction_id'])]['reference_target_positions'][i]
   elif method=='published_method_bounded_downward_candidate':seed=rec[(sc,node)]['bounded_downward_candidates'][0]['position']
   elif method=='UNRESOLVED_no_direct_identity':seed=None;cameras[node]=identities[(sc,node)]['camera_position']
   else:seed=identities[(sc,node)]['position']
   values.append(('camera',node) if seed is None else ('ground',tuple(seed)))
  seeds[t['task_key']]=values
 cfg=habitat_sim.SimulatorConfiguration();glb=ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb';cfg.scene_id=str(glb);cfg.create_renderer=True;cfg.enable_physics=False;cfg.gpu_device_id=0;agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;sensor=habitat_sim.SensorSpec();sensor.uuid='build_rgb';sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[16,16];sensor.position=[0,1.25,0];agent.sensor_specifications=[sensor];sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));scene_report={'scene':sc,'source_glb_sha256':digest(glb),'records':len(tasks[sc]),'prior_blocked':sum(t['status']=='STATIC_BLOCKED_PRESERVED' for t in tasks[sc]),'variants':[]}
 try:
  for name,(cs,ch,climb,region) in variants.items():
   started=time.time();settings=habitat_sim.NavMeshSettings();settings.set_defaults();settings.agent_height=1.5;settings.agent_radius=.1;settings.cell_size=cs;settings.cell_height=ch;settings.agent_max_climb=climb;settings.region_min_size=region;settings.region_merge_size=region;assert sim.recompute_navmesh(sim.pathfinder,settings);mesh=out/(sc+'-'+name+'.navmesh');assert sim.pathfinder.save_nav_mesh(str(mesh));pf=sim.pathfinder;pointcache={};pathcache={};results=[];counts=collections.Counter()
   def point(seed):
    if seed in pointcache:return pointcache[seed]
    if seed[0]=='ground':
     p=seed[1];q=list(pf.snap_point(p));ok=all(math.isfinite(v) for v in q) and math.hypot(q[0]-p[0],q[2]-p[2])<.5 and abs(q[1]-p[1])<=.5 and pf.is_navigable(q);value=q if ok else None
    else:
     p=cameras[seed[1]];possible=[]
     for i in range(101):
      q=list(pf.snap_point([p[0],p[1]-.02*i,p[2]]))
      if not all(math.isfinite(v) for v in q):continue
      h=math.hypot(q[0]-p[0],q[2]-p[2]);drop=p[1]-q[1]
      if h<.5 and 0<=drop<=2 and pf.is_navigable(q):possible.append((h,-drop,q))
     value=min(possible)[2] if possible else None
    pointcache[seed]=value;return value
   def reachable(a,b):
    key=(tuple(a),tuple(b))
    if key not in pathcache:
     q=habitat_sim.ShortestPath();q.requested_start=a;q.requested_end=b;pathcache[key]=bool(pf.find_path(q)) and math.isfinite(q.geodesic_distance)
    return pathcache[key]
   for t in tasks[sc]:
    ps=[point(s) for s in seeds[t['task_key']]];missing=[i for i,p in enumerate(ps) if p is None];bad=[] if missing else [i for i,(a,b) in enumerate(zip(ps,ps[1:])) if not reachable(a,b)];ok=not missing and not bad;prior=t['status']=='READY_FOR_NATIVE_MOTION';counts['pass' if ok else 'blocked']+=1;counts['regressed']+=prior and not ok;counts['recovered']+=not prior and ok;results.append({'task_key':t['task_key'],'pass':ok,'missing_indices':missing,'unreachable_indices':bad})
   scene_report['variants'].append({'variant':name,'settings':{'cell_size':cs,'cell_height':ch,'agent_max_climb':climb,'region_min_size':region,'region_merge_size':region,'agent_height':1.5,'agent_radius':.1},'mesh_path':str(mesh),'mesh_sha256':digest(mesh),'counts':dict(counts),'results':results,'seconds':time.time()-started});print(sc,name,dict(counts),flush=True)
 finally:sim.close()
 atomic_json(rp,scene_report);summary.append(scene_report);atomic_json(out/'state.json',{'status':'RUNNING','completed_scenes':len(summary),'expected_scenes':len(scenes),'last_scene':sc})
atomic_json(out/'summary.json',{'status':'DIAGNOSTIC_COMPLETE_NOT_ACCEPTED','scenes':summary,'script_sha256':digest(__file__),'selection_gate':'No automatic adoption. Any candidate needs zero static regressions and actual motion validation; original task denominator fixed.'});atomic_json(out/'state.json',{'status':'COMPLETE','completed_scenes':len(summary),'expected_scenes':len(scenes)})
