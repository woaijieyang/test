"""Offline single-task native oracle with source-cylinder guard; never used by model."""
import os,sys,json,math,datetime,argparse
_parser=argparse.ArgumentParser();_parser.add_argument("--manifest",required=True);_parser.add_argument("--task-file",required=True);_parser.add_argument("--output",required=True);_parser.add_argument("--cpu",type=int,required=True);_args=_parser.parse_args()
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'.cache/geometry-tools'));sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
from robust_oracle import RobustOracle
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.sched_setaffinity(0,[_args.cpu]);os.nice(15)
import numpy as np,trimesh,habitat_sim
from habitat_sim.utils.common import quat_from_coeffs
helper=ROOT/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';source=helper.read_text();exec(source[source.index('def clip('):source.index('records=[]')])
b=ROOT/'outputs/landmark-connectivity';m=json.loads(Path(_args.manifest).read_text());task=json.loads(Path(_args.task_file).read_text());assert digest(__file__)==m['worker_sha256'];assert digest(helper)==m['helper_sha256'];assert digest(Path(__file__).with_name('robust_oracle.py'))==m['oracle_sha256'];assert digest(m['profile_path'])==m['profile_sha256'];profile=json.loads(Path(m['profile_path']).read_text());asset=profile['assets'][f"mp3d/{task['scene']}/{task['scene']}.glb"];gp=ROOT/f"data/scene_datasets/mp3d/{task['scene']}/{task['scene']}.glb";mesh=trimesh.load(str(gp),force='scene',process=False).to_geometry();mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float));tri=np.asarray(mesh.triangles);lo=tri.min(axis=1);hi=tri.max(axis=1);regioncache={};posecache={};stats={'checked_poses':0,'rejected_poses':0,'rejected_transitions':0}
def safe(p):
 key=tuple(round(float(x),6) for x in p)
 if key in posecache:return posecache[key]
 p=np.asarray(p);cell=tuple(math.floor(float(v)/.5) for v in p)
 if cell not in regioncache:
  low=np.asarray(cell)*.5;high=low+.5;regioncache[cell]=np.flatnonzero((lo[:,0]<high[0]+.1)&(hi[:,0]>low[0]-.1)&(lo[:,2]<high[2]+.1)&(hi[:,2]>low[2]-.1)&(lo[:,1]<high[1]+1.5)&(hi[:,1]>low[1]))
 candidates=regioncache[cell];stats['checked_poses']+=1;ok=True
 for j in candidates:
  if lo[j,0]>=p[0]+.1 or hi[j,0]<=p[0]-.1 or lo[j,2]>=p[2]+.1 or hi[j,2]<=p[2]-.1 or lo[j,1]>=p[1]+1.5 or hi[j,1]<=p[1]+1e-5:continue
  poly=clip(list(tri[j]),p[1]+1e-5,True)
  if len(poly)<3:continue
  poly=clip(poly,p[1]+1.5,False)
  if len(poly)>=3 and distance(poly,p)<.1-1e-6:ok=False;stats['rejected_poses']+=1;break
 posecache[key]=ok;return ok
class BodyOracle(RobustOracle):
 def transition(self,state,action):
  new=super().transition(state,action)
  if new is None:return None
  count=max(1,math.ceil(math.dist(state[0],new[0])/.05))
  if not all(safe(state[0]+(new[0]-state[0])*i/count) for i in range(1,count+1)):
   stats['rejected_transitions']+=1;return None
  return new
cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;a=habitat_sim.agent.AgentConfiguration();a.height=1.5;a.radius=.1;a.sensor_specifications=[];a.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))};sims=[habitat_sim.Simulator(habitat_sim.Configuration(cfg,[a])) for _ in range(3)];sim,planner,replay=sims
for s in sims:assert s.pathfinder.load_nav_mesh(asset['navmesh_path'])
yaw=(-task['heading']+math.pi)%(2*math.pi)-math.pi;rotation=[0,math.sin(yaw/2),0,math.cos(yaw/2)];state=habitat_sim.AgentState();state.position=task['targets'][0];state.rotation=quat_from_coeffs(rotation);sim.initialize_agent(0,state);replay.initialize_agent(0,state);positions=[sim.get_agent(0).get_state().position.tolist()];actions=[];boundaries=[];error=None
try:
 assert safe(positions[0]),'source_body_initial_collision'
 for i,target in enumerate(task['targets'][1:],1):
  oracle=BodyOracle(sim,planner,target,radius=.25,max_nodes=100000)
  for step in range(1500):
   action=oracle.next_action()
   if action==0:break
   assert len(actions)<10000;sim.step(action);p=sim.get_agent(0).get_state().position.tolist();assert all(math.isfinite(v) for v in p) and sim.pathfinder.is_navigable(p);assert abs(p[1]-positions[-1][1])<=.5;assert safe(p);actions.append(action);positions.append(p)
  else:raise RuntimeError('segment_budget_exhausted')
  assert oracle.distance(positions[-1])<=.25;boundaries.append({'reference_index':i,'action_index':len(actions)});print('reference',i,'actions',len(actions),stats,flush=True)
except Exception as e:error=repr(e)
max_error=0
for i,act in enumerate(actions):replay.step(act);max_error=max(max_error,math.dist(replay.get_agent(0).get_state().position.tolist(),positions[i+1]))
for s in sims:s.close()
out=Path(_args.output);atomic_json(out,{'status':'PASS_DIAGNOSTIC' if error is None and max_error<=1e-5 else 'FAILED_DIAGNOSTIC','task_key':task['task_key'],'source_record_sha256':task['source_record_sha256'],'guard_manifest_sha256':digest(_args.manifest),'helper_sha256':digest(helper),'oracle_sha256':digest(Path(__file__).with_name('robust_oracle.py')),'error':error,'stats':stats,'targets':task['targets'],'rotation':rotation,'actions':actions,'positions':positions,'boundaries':boundaries,'max_replay_error':max_error,'mesh_sha256':digest(asset['navmesh_path']),'scene_sha256':digest(gp),'script_sha256':digest(__file__),'limits':'Additional conservative full-body source-geometry oracle check, no relaxation of native gates. Failure is not proof of physical impossibility. No model policy change.'});print(out,error,stats,flush=True)
