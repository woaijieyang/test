"""Exhaustive native action execution with independent replay; not model evaluation."""
import argparse,os,sys,json,gzip,math,time,hashlib,datetime,fcntl
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest,owned
p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--shard',type=int,required=True);p.add_argument('--shards',type=int,default=2);a=p.parse_args()
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';cpus=sorted(os.sched_getaffinity(0));run=owned(a.run);manifest=json.loads((run/'manifest.json').read_text());os.sched_setaffinity(0,manifest['cpu_assignments'][str(a.shard)]);os.nice(10);msha=digest(run/'manifest.json');expected_code=manifest['worker_sha256'];assert digest(__file__)==expected_code;assert digest(Path(__file__).with_name('robust_oracle.py'))==manifest['oracle_sha256'];profile=json.loads(Path(manifest['profile_path']).read_text());assert digest(manifest['profile_path'])==manifest['profile_sha256'];directory=run/f'shard-{a.shard:02}';directory.mkdir(exist_ok=True);lease=(directory/'worker.lock').open('a');fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
import habitat_sim
from robust_oracle import RobustOracle
from habitat_sim.utils.common import quat_from_coeffs
cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;agent.sensor_specifications=[];agent.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))};sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));replay=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));planner=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));current_scene=None;pid=os.getpid();start_ticks=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19];atomic_json(directory/'process.json',{'pid':pid,'start_ticks':start_ticks,'manifest_sha256':msha,'script_sha256':expected_code,'cpu_affinity':sorted(os.sched_getaffinity(0))});tasks=[t for t in manifest['tasks'] if int(hashlib.sha256(t['task_key'].encode()).hexdigest(),16)%a.shards==a.shard];tasks.sort(key=lambda t:(t['scene'],t['task_key']));counts={'processed':0,'passed':0,'failed':0,'static_blocked':0};gate=manifest['motion_gate'];started=time.time()
def state():atomic_json(directory/'state.json',{'status':'RUNNING','pid':pid,'start_ticks':start_ticks,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'counts':counts,'assigned':len(tasks),'manifest_sha256':msha,'elapsed_seconds':time.time()-started})
def set_agent(s,start,rotation):
 st=habitat_sim.AgentState();st.position=start;st.rotation=quat_from_coeffs(rotation);s.initialize_agent(0,st)
def path_exists(pf,start,end):
 q=habitat_sim.ShortestPath();q.requested_start=start;q.requested_end=end;ok=pf.find_path(q);return bool(ok) and math.isfinite(q.geodesic_distance),float(q.geodesic_distance) if ok else None
state()
try:
 for task in tasks:
  key=task['task_key'];tid=hashlib.sha256(key.encode()).hexdigest()[:24];result_path=directory/(tid+'.result.json')
  if result_path.exists():
   previous=json.loads(result_path.read_text());assert previous['manifest_sha256']==msha and previous['task_key']==key;counts['processed']+=1;counts['passed' if previous['status']=='PASS' else 'static_blocked' if previous['status']=='STATIC_BLOCKED_PRESERVED' else 'failed']+=1;continue
  result={'task_key':key,'manifest_sha256':msha,'scene':task['scene'],'source_record_sha256':task['source_record_sha256']}
  if task['status']=='STATIC_BLOCKED_PRESERVED':result.update(status=task['status'],errors=task['static_errors']);counts['static_blocked']+=1
  else:
   scene=task['scene'];asset=profile['assets'][f'mp3d/{scene}/{scene}.glb']
   if scene!=current_scene:
    assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];assert sim.pathfinder.load_nav_mesh(asset['navmesh_path']);assert replay.pathfinder.load_nav_mesh(asset['navmesh_path']);assert planner.pathfinder.load_nav_mesh(asset['navmesh_path']);current_scene=scene
   yaw=(-task['heading']+math.pi)%(2*math.pi)-math.pi;rotation=[0,math.sin(yaw/2),0,math.cos(yaw/2)];targets=task['targets'];set_agent(sim,targets[0],rotation);positions=[sim.get_agent(0).get_state().position.tolist()];actions=[];boundaries=[];errors=[];goal=targets[-1]
   if math.dist(positions[0],targets[0])>1e-5:errors.append({'kind':'reset_mismatch'})
   for index,target in enumerate(targets[1:],1):
    follower=RobustOracle(sim,planner,target,radius=gate['goal_radius_m'],max_nodes=100000)
    try:
     for step in range(gate['max_actions_per_segment']):
      action=follower.next_action(target)
      if action==0:break
      if len(actions)>=gate['max_actions_per_episode']:raise RuntimeError('episode_budget_exhausted')
      sim.step(action);actions.append(int(action));point=sim.get_agent(0).get_state().position.tolist();before=positions[-1];positions.append(point)
      if not all(math.isfinite(x) for x in point):raise RuntimeError('nonfinite_position')
      if not sim.pathfinder.is_navigable(point):raise RuntimeError('offmesh_position')
      if abs(point[1]-before[1])>gate['max_vertical_step_m']:raise RuntimeError('vertical_step_exceeded')
      ok,_=path_exists(sim.pathfinder,point,goal)
      if not ok:raise RuntimeError('actual_position_unreachable_to_final_goal')
     else:raise RuntimeError('segment_budget_exhausted')
     ok,dist=path_exists(sim.pathfinder,positions[-1],target)
     if not ok or dist>gate['goal_radius_m']+1e-6:raise RuntimeError('follower_stopped_outside_radius')
     boundaries.append({'reference_index':index,'action_index':len(actions),'distance':dist})
    except Exception as exc:errors.append({'kind':'native_motion_failure','reference_index':index,'error':repr(exc)});break
   set_agent(replay,targets[0],rotation);replay_error=math.dist(replay.get_agent(0).get_state().position.tolist(),positions[0])
   for i,action in enumerate(actions):
    replay.step(action);replay_error=max(replay_error,math.dist(replay.get_agent(0).get_state().position.tolist(),positions[i+1]))
   if replay_error>gate['replay_tolerance_m']:errors.append({'kind':'native_replay_mismatch','max_error':replay_error})
   trace={'task_key':key,'manifest_sha256':msha,'mesh_sha256':asset['navmesh_sha256'],'rotation':rotation,'targets':targets,'positions':positions,'actions':actions,'reached_reference_boundaries':boundaries,'errors':errors,'max_replay_error':replay_error};trace_path=directory/(tid+'.trace.json.gz');blob=gzip.compress(json.dumps(trace,separators=(',',':'),allow_nan=False).encode(),mtime=0);trace_path.write_bytes(blob)
   result.update(status='PASS' if not errors and len(boundaries)==len(targets)-1 else 'FAIL',errors=errors,actions=len(actions),trace_path=str(trace_path.relative_to(run)),trace_sha256=hashlib.sha256(blob).hexdigest(),max_replay_error=replay_error,reached_reference_points=len(boundaries)+1,expected_reference_points=len(targets));counts['passed' if result['status']=='PASS' else 'failed']+=1
  atomic_json(result_path,result);counts['processed']+=1
  if counts['processed']%20==0:state()
 assert digest(__file__)==expected_code and digest(run/'manifest.json')==msha
 atomic_json(directory/'state.json',{'status':'COMPLETE','pid':pid,'start_ticks':start_ticks,'counts':counts,'assigned':len(tasks),'manifest_sha256':msha,'elapsed_seconds':time.time()-started})
finally:sim.close();replay.close();planner.close()
