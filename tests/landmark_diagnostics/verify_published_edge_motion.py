import os,sys,json,math,zipfile,hashlib
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected launcher required')
os.environ['CUDA_VISIBLE_DEVICES']='7';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2])
import habitat_sim,numpy as np
from habitat_sim.utils.common import quat_from_coeffs
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--variant',default='fine05_climb03');parser.add_argument('--output',required=True);args=parser.parse_args()
if args.variant not in ('fine05_climb03','fine025_climb03','coarse05_climb03','fine01_climb03'):raise ValueError('Unknown diagnostic variant')
sc='pRbA3pwrgk9';mesh=ROOT/('outputs/landmark-connectivity/mesh-search/pRbA3pwrgk9-'+args.variant+'.navmesh');z=zipfile.ZipFile('outputs/landmark-connectivity/habitat_mp3d_connectivity_graphs.zip');edge=json.loads(z.read('habitat_mp3d_connectivity_graphs/'+sc+'.json'))['edges']['edge_51'];from workspace import owned
out=owned(args.output);out.mkdir(exist_ok=False)
def make(render):
 cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id=str(ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb') if render else 'NONE';cfg.create_renderer=render;cfg.enable_physics=False;cfg.gpu_device_id=0
 agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;agent.sensor_specifications=[];agent.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))}
 if render:
  sensor=habitat_sim.SensorSpec();sensor.uuid='rgb';sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[64,64];sensor.position=[0,1.25,0];agent.sensor_specifications=[sensor]
 sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));assert sim.pathfinder.load_nav_mesh(str(mesh));return sim
sim=make(True);traces=[]
try:
 for direction,start,target in [('forward',edge['start_coor'],edge['end_coor']),('reverse',edge['end_coor'],edge['start_coor'])]:
  start=list(sim.pathfinder.snap_point(start));goal=list(sim.pathfinder.snap_point(target));state=habitat_sim.AgentState();state.position=start;state.rotation=quat_from_coeffs([0,0,0,1]);sim.initialize_agent(0,state);follower=sim.make_greedy_follower(goal_radius=.25,stop_key=0,forward_key=1,left_key=2,right_key=3);positions=[sim.get_agent(0).get_state().position.tolist()];actions=[];error=None;images=[]
  try:
   for step in range(2000):
    action=follower.next_action_along(goal)
    if action==0:break
    observations=sim.step(action);actions.append(int(action));positions.append(sim.get_agent(0).get_state().position.tolist())
    if step%20==0:images.append({'step':step,'rgb_sha256':hashlib.sha256(observations['rgb'].tobytes()).hexdigest()})
   else:error='budget_exhausted'
  except Exception as e:error=repr(e)
  q=habitat_sim.ShortestPath();q.requested_start=positions[-1];q.requested_end=goal;found=sim.pathfinder.find_path(q);distance=float(q.geodesic_distance) if found else None
  trace={'direction':direction,'start':start,'goal':goal,'original_published_start':edge['start_coor'] if direction=='forward' else edge['end_coor'],'original_published_goal':target,'rotation':[0,0,0,1],'positions':positions,'actions':actions,'error':error,'final_geodesic_distance':distance,'reached':distance is not None and distance<=.25,'images':images};traces.append(trace);atomic_json(out/(direction+'.json'),trace);print(direction,len(actions),distance,error,flush=True)
finally:sim.close()
replay=make(False);results=[]
try:
 for trace in traces:
  state=habitat_sim.AgentState();state.position=trace['start'];state.rotation=quat_from_coeffs(trace['rotation']);replay.initialize_agent(0,state);errors=[math.dist(replay.get_agent(0).get_state().position.tolist(),trace['positions'][0])];offmesh=0;unreachable=0
  for i,action in enumerate(trace['actions']):
   replay.step(action);point=replay.get_agent(0).get_state().position.tolist();errors.append(math.dist(point,trace['positions'][i+1]));offmesh+=not replay.pathfinder.is_navigable(point);q=habitat_sim.ShortestPath();q.requested_start=point;q.requested_end=trace['goal'];unreachable+=not replay.pathfinder.find_path(q)
  maxvertical=max((abs(b[1]-a[1]) for a,b in zip(trace['positions'],trace['positions'][1:])),default=0);results.append({'direction':trace['direction'],'reached':trace['reached'],'error':trace['error'],'max_replay_error':max(errors),'offmesh_positions':offmesh,'unreachable_positions':unreachable,'max_vertical_step':maxvertical})
finally:replay.close()
report={'status':'PASS' if all(r['reached'] and not r['error'] and r['max_replay_error']<1e-5 and r['offmesh_positions']==0 and r['unreachable_positions']==0 and r['max_vertical_step']<=.5 for r in results) else 'FAIL','scope':'two_directions_published_edge_51_only','mesh_sha256':digest(mesh),'body':{'height':1.5,'radius':.1},'steps':{'forward':.25,'turn':15},'results':results,'script_sha256':digest(__file__)};atomic_json(out/'validation.json',report);print(json.dumps(report))
