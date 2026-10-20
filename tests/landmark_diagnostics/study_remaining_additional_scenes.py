"""Single-factor gap study for remaining3342; no adoption or acceptance from static results."""
import os,sys,json,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='4';os.environ['OMP_NUM_THREADS']='2';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[10:12]);os.nice(10)
import subprocess
_gpu=subprocess.check_output(['nvidia-smi','--id=4','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True);_mem,_util=map(int,_gpu.strip().split(','));assert _mem<1024 and _util<10, 'GPU 4 no longer idle'
import habitat_sim
b=ROOT/'outputs/landmark-connectivity';out=b/'remaining3342-additional-scenes-v2';out.mkdir(exist_ok=False);m=json.loads((b/'full-native-v8/manifest.json').read_text());results=[]
atomic_json(out/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
atomic_json(out/'state.json',{'status':'RUNNING','completed_scenes':0})
import atexit
def terminal_on_exit():
 if not (out/'summary.json').exists():atomic_json(out/'state.json',{'status':'FAILED','completed_scenes':len(results),'reason':'Abnormal exit; see retained log'})
atexit.register(terminal_on_exit)
variants=[('fine_tight',.05,.05,.3,.1,20),('coarse_area_tight',.1,.05,.3,.1,10)]
for sc in ['JF19kD82Mey','qoiz87JEwZ2','D7N2EKCX4Sj','b8cTxDM8gDG','HxpKQynjfin','5q7pvUzZiYa','Uxmj2M2itWa','VLzqgDo317F']:
 _gpu=subprocess.check_output(['nvidia-smi','--id=4','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True);_mem,_util=map(int,_gpu.strip().split(','));assert _mem<1024 and _util<10, 'GPU 4 no longer idle'
 diagnostic=json.loads((b/'remaining3342-v1'/(sc+'.json')).read_text());cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id=str(ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb');cfg.create_renderer=True;cfg.enable_physics=False;cfg.gpu_device_id=0;agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;sensor=habitat_sim.SensorSpec();sensor.uuid='build';sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[16,16];agent.sensor_specifications=[sensor];sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));scene={'scene':sc,'source_sha256':digest(cfg.scene_id),'variants':[]};ts=[t for t in m['tasks'] if t['scene']==sc]
 try:
  for name,cs,ch,climb,edge_error,region in variants:
   ns=habitat_sim.NavMeshSettings();ns.set_defaults();ns.agent_height=1.5;ns.agent_radius=.1;ns.cell_size=cs;ns.cell_height=ch;ns.agent_max_climb=climb;ns.edge_max_error=edge_error;ns.region_min_size=region;ns.region_merge_size=region;assert sim.recompute_navmesh(sim.pathfinder,ns);pf=sim.pathfinder;mp=out/f'{sc}-{name}.navmesh';assert pf.save_nav_mesh(str(mp));cache={};paths={}
   def point(p):
    if p is None:return None
    key=tuple(p)
    if key not in cache:
     q=list(pf.snap_point(p));cache[key]=q if all(math.isfinite(v) for v in q) and math.dist(p,q)<=.5 and pf.is_navigable(q) else None
    return cache[key]
   def connected(a,c):
    if a is None or c is None:return False
    key=(tuple(a),tuple(c))
    if key not in paths:
     q=habitat_sim.ShortestPath();q.requested_start=a;q.requested_end=c;paths[key]=bool(pf.find_path(q) and math.isfinite(q.geodesic_distance))
    return paths[key]
   edge_results=[{'nodes':e['nodes'],'reachable':connected(point(e['start']),point(e['end'])),'task_count':len(e['task_keys'])} for e in diagnostic['disconnected_edges']];counts=collections.Counter();rows=[]
   for t in ts:
    ps=[point(p) for p in t['targets']];ok=all(p is not None for p in ps) and all(connected(a,c) for a,c in zip(ps,ps[1:]));prior=t['status']=='READY_FOR_NATIVE_MOTION';counts['candidate_static_pass' if ok else 'blocked']+=1;counts['regressions']+=prior and not ok;counts['recoveries']+=not prior and ok;rows.append({'task_key':t['task_key'],'pass':bool(ok),'prior_pass':prior})
   scene['variants'].append({'name':name,'settings':{'edge_max_error':edge_error,'cell_size':cs,'cell_height':ch,'agent_max_climb':climb,'region_min_size':region,'region_merge_size':region,'agent_height':1.5,'agent_radius':.1},'mesh_path':str(mp),'mesh_sha256':digest(mp),'edge_results':edge_results,'counts':dict(counts),'tasks':rows});print(sc,name,dict(counts),'connected_edges',sum(e['reachable'] for e in edge_results),flush=True)
 finally:sim.close()
 results.append(scene);atomic_json(out/'partial.json',results);atomic_json(out/'state.json',{'status':'RUNNING','completed_scenes':len(results),'last_scene':sc})
atomic_json(out/'summary.json',{'status':'DIAGNOSTIC_COMPLETE_NOT_ACCEPTED','scenes':results,'script_sha256':digest(__file__),'hypothesis':'Continue remaining3342 across eight additional scenes; preserve physical region area and tight contour, fixed body and motion gates. Reject any scene-level regressions; no automatic adoption.','limits':'Point projection is a screen only, not final source-anchor alignment. Requires grounded full-cohort nonregression, physical motion and independent replay before adoption. Original 114 retained.'})

atomic_json(out/'state.json',{'status':'COMPLETE_NOT_ACCEPTED','completed_scenes':len(results)})
