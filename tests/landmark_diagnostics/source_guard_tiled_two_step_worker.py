"""Offline single-task native oracle with source-cylinder guard; never used by model."""
import os,sys,json,math,datetime,argparse,gzip,resource
_parser=argparse.ArgumentParser();_parser.add_argument("--manifest",required=True);_parser.add_argument("--task-file",required=True);_parser.add_argument("--output",required=True);_parser.add_argument("--cpu",type=int,required=True);_args=_parser.parse_args()
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'.cache/geometry-tools'));sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
from robust_oracle import RobustOracle
assert os.environ.get('CASE1_PROTECTION');resource.setrlimit(resource.RLIMIT_CORE,(0,0));os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.sched_setaffinity(0,[_args.cpu]);os.nice(15)
import numpy as np,trimesh,habitat_sim
from habitat_sim.utils.common import quat_from_coeffs
helper=ROOT/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';source=helper.read_text();exec(source[source.index('def clip('):source.index('records=[]')])
b=ROOT/'outputs/landmark-connectivity';m=json.loads(Path(_args.manifest).read_text());task=json.loads(Path(_args.task_file).read_text());assert digest(__file__)==m['worker_sha256'];assert digest(helper)==m['helper_sha256'];assert digest(Path(__file__).with_name('robust_oracle.py'))==m['oracle_sha256'];assert digest(m['profile_path'])==m['profile_sha256'];profile=json.loads(Path(m['profile_path']).read_text());asset=profile['assets'][f"mp3d/{task['scene']}/{task['scene']}.glb"];gp=ROOT/f"data/scene_datasets/mp3d/{task['scene']}/{task['scene']}.glb";native=m['native_geometry'];assert digest(native['receipt_path'])==native['receipt_sha256'];nr=json.loads(Path(native['receipt_path']).read_text());assert nr['scene']==task['scene'] and nr['scene_sha256']==m['scene_sha256'];ng=Path(nr['native_geometry_path']);assert digest(ng)==nr['native_geometry_sha256'];raw=ng.read_bytes();nv,nt=np.frombuffer(raw[:8],dtype=np.int32);assert len(raw)==8+int(nv)*12+int(nt)*12;vertices=np.frombuffer(raw,dtype=np.float32,count=int(nv)*3,offset=8).reshape(-1,3);indices=np.frombuffer(raw,dtype=np.int32,count=int(nt)*3,offset=8+int(nv)*12).reshape(-1,3);tri=vertices[indices].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);regioncache={};posecache={};stats={'checked_poses':0,'rejected_poses':0,'rejected_transitions':0}
def safe(p):
 key=tuple(float(x) for x in p)
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
sweep_reference=ROOT/'tests/landmark_diagnostics/swept_cylinder_reference.py';assert digest(sweep_reference)==m['sweep_helper_sha256'];from swept_cylinder_reference import triangle_linear_sweep_distance
transition_cache={};sweep_regions={}
def continuous_clear(a,b):
 key=(tuple(float(x) for x in a),tuple(float(x) for x in b))
 if key in transition_cache:return transition_cache[key]
 low=np.minimum(a,b);high=np.maximum(a,b);c0=tuple(np.floor(low/.5).astype(int));c1=tuple(np.floor(high/.5).astype(int));rk=(c0,c1)
 if rk not in sweep_regions:
  l=np.array(c0)*.5;h=(np.array(c1)+1)*.5;sweep_regions[rk]=np.flatnonzero((lo[:,0]<h[0]+.1)&(hi[:,0]>l[0]-.1)&(lo[:,2]<h[2]+.1)&(hi[:,2]>l[2]-.1)&(lo[:,1]<h[1]+1.5)&(hi[:,1]>l[1]+1e-5))
 ok=True
 for j in sweep_regions[rk]:
  if lo[j,0]>=high[0]+.1 or hi[j,0]<=low[0]-.1 or lo[j,2]>=high[2]+.1 or hi[j,2]<=low[2]-.1 or lo[j,1]>=high[1]+1.5 or hi[j,1]<=low[1]+1e-5:continue
  if triangle_linear_sweep_distance(tri[j],a,b)<.1-1e-6:ok=False;break
 transition_cache[key]=ok;return ok
class BodyOracle(RobustOracle):
 def key(self,state):
  base=super().key(state)+(int(self.transition(state,1) is not None),)
  continuation=[]
  for action in (1,2,3):
   first=self.transition(state,action)
   continuation.append(int(first is not None and self.transition(first,1) is not None))
  return base+tuple(continuation)
 def transition(self,state,action):
  new=super().transition(state,action)
  if new is None:return None
  if not continuous_clear(state[0],new[0]):stats['rejected_transitions']+=1;return None
  return new
reference=ROOT/'tests/landmark_diagnostics/projected_distance_reference.py';assert digest(reference)==m['geometry_reference_sha256'];from projected_distance_reference import projected_distance;distance=projected_distance
assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];assert digest(gp)==m['scene_sha256'];assert digest(m['tile_header_audit_path'])==m['tile_header_audit_sha256']
seed_info=m['native_plan_inputs'][task['task_key']]
assert digest(seed_info['result_path'])==seed_info['result_sha256'];seed_result=json.loads(Path(seed_info['result_path']).read_text());assert seed_result['source_record_sha256']==task['source_record_sha256'] and seed_result['manifest_sha256']==m['parent_manifest_sha256']
assert digest(m['candidate_tasks_path'])==m['candidate_tasks_sha256'] and digest(m['candidate_static_audit_path'])==m['candidate_static_audit_sha256'];candidate_audit=json.loads(Path(m['candidate_static_audit_path']).read_text());assert candidate_audit['status']=='PASS_PROPOSAL_IDENTITY_BOUNDS_BODY_AND_CONNECTIVITY_NOT_MOTION' and candidate_audit['candidate_tasks_sha256']==m['candidate_tasks_sha256'] and candidate_audit['profile_sha256']==m['profile_sha256'];assert next(t for t in json.loads(Path(m['candidate_tasks_path']).read_text())['tasks'] if t['task_key']==task['task_key'])==task
assert digest(m['source_profile_path'])==m['source_profile_sha256'];source_profile=json.loads(Path(m['source_profile_path']).read_text());assert source_profile['assets'][f"mp3d/{task['scene']}/{task['scene']}.glb"]['navmesh_sha256']==seed_info['source_mesh_sha256'];assert digest(seed_info['source_task_path'])==seed_info['source_task_sha256'];original_task=json.loads(Path(seed_info['source_task_path']).read_text());assert {k:v for k,v in task.items() if k not in ['targets','mapping_methods']}=={k:v for k,v in original_task.items() if k not in ['targets','mapping_methods']}
seed=None
if seed_info['use_native_plan']:
 assert seed_result['status']=='PASS' and digest(seed_info['trace_path'])==seed_info['trace_sha256'];seed=json.load(gzip.open(seed_info['trace_path'],'rt'));assert seed['task_key']==task['task_key'] and seed['targets']==original_task['targets'] and seed['mesh_sha256']==seed_info['source_mesh_sha256'];assert seed['manifest_sha256']==m['parent_manifest_sha256'] and len(seed['reached_reference_boundaries'])==len(task['targets'])-1
else:
 assert seed_result['status']=='STATIC_BLOCKED_PRESERVED' and original_task['status']=='STATIC_BLOCKED_PRESERVED'
cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;a=habitat_sim.agent.AgentConfiguration();a.height=1.5;a.radius=.1;a.sensor_specifications=[];a.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))};sims=[habitat_sim.Simulator(habitat_sim.Configuration(cfg,[a])) for _ in range(3)];sim,planner,replay=sims
for s in sims:assert s.pathfinder.load_nav_mesh(asset['navmesh_path'])
yaw=(-task['heading']+math.pi)%(2*math.pi)-math.pi;rotation=[0,math.sin(yaw/2),0,math.cos(yaw/2)];state=habitat_sim.AgentState();state.position=task['targets'][0];state.rotation=quat_from_coeffs(rotation);sim.initialize_agent(0,state);replay.initialize_agent(0,state);positions=[sim.get_agent(0).get_state().position.tolist()];actions=[];boundaries=[];error=None;error_kind=None
raw_steps=Path(_args.output).with_suffix('.executed.jsonl').open('x')
try:
 assert safe(positions[0]),'source_body_initial_collision'
 for i,target in enumerate(task['targets'][1:],1):
  oracle=BodyOracle(sim,planner,target,radius=.25,max_nodes=5000)
  if seed is not None:
   boundaries_seed=seed['reached_reference_boundaries'];end=boundaries_seed[i-1]['action_index'];start=boundaries_seed[i-2]['action_index'] if i>1 else 0;oracle.plan=list(seed['actions'][start:end])
  for step in range(1500):
   action=oracle.next_action()
   if action==0:break
   assert len(actions)<10000,'episode_budget_exhausted';previous=positions[-1];sim.step(action);p=sim.get_agent(0).get_state().position.tolist();actions.append(action);positions.append(p);raw_steps.write(json.dumps({'action_index':len(actions)-1,'action':int(action),'position_repr':repr(p),'finite':all(math.isfinite(v) for v in p)})+'\n');raw_steps.flush();assert all(math.isfinite(v) for v in p),'nonfinite_actual_pose';assert sim.pathfinder.is_navigable(p),'actual_offmesh';assert abs(p[1]-previous[1])<=.5,'actual_vertical_limit';assert safe(p),'source_body_actual_collision';assert continuous_clear(previous,p),'actual_continuous_source_collision'
  else:raise RuntimeError('segment_budget_exhausted')
  assert oracle.distance(positions[-1])<=.25,'reference_target_not_reached';boundaries.append({'reference_index':i,'action_index':len(actions)});print('reference',i,'actions',len(actions),stats,flush=True)
except Exception as e:
 error=repr(e);message=str(e)
 if isinstance(e,RuntimeError) and (message.startswith('legal_action_search_exhausted:') or message=='segment_budget_exhausted'):error_kind='SEARCH_OR_BUDGET_FAILURE'
 elif isinstance(e,AssertionError) and message in ['source_body_initial_collision','episode_budget_exhausted','actual_offmesh','actual_vertical_limit','source_body_actual_collision','actual_continuous_source_collision','reference_target_not_reached']:error_kind='SOURCE_OR_NATIVE_GATE_FAILURE'
 else:error_kind='INFRASTRUCTURE_FAILURE'
max_error=0
for i,act in enumerate(actions):replay.step(act);max_error=max(max_error,math.dist(replay.get_agent(0).get_state().position.tolist(),positions[i+1]))
for s in sims:s.close()
raw_steps.close()
out=Path(_args.output);atomic_json(out,{'status':'PASS_DIAGNOSTIC' if error is None and max_error<=1e-5 else 'FAILED_DIAGNOSTIC','task_key':task['task_key'],'source_record_sha256':task['source_record_sha256'],'guard_manifest_sha256':digest(_args.manifest),'geometry_reference_sha256':digest(reference),'native_geometry_sha256':nr['native_geometry_sha256'],'native_geometry_receipt_sha256':native['receipt_sha256'],'source_guard_mode':'exact_continuous_linear_sweep','sweep_helper_sha256':digest(sweep_reference),'candidate_tasks_sha256':m['candidate_tasks_sha256'],'candidate_static_audit_sha256':m['candidate_static_audit_sha256'],'native_plan_inputs':seed_info,'seed_mode':'prior_native_plan_revalidated' if seed is not None else 'unseeded_previously_static','executed_steps_path':str(Path(_args.output).with_suffix('.executed.jsonl')),'actual_poststep_sweep_checked':True,'helper_sha256':digest(helper),'oracle_sha256':digest(Path(__file__).with_name('robust_oracle.py')),'error':error,'error_kind':error_kind,'stats':stats,'targets':task['targets'],'rotation':rotation,'actions':actions,'positions':positions,'boundaries':boundaries,'max_replay_error':max_error,'mesh_sha256':digest(asset['navmesh_path']),'scene_sha256':digest(gp),'script_sha256':digest(__file__),'limits':'Additional conservative full-body source-geometry oracle check, no relaxation of native gates. Failure is not proof of physical impossibility. No model policy change.'});print(out,error,stats,flush=True)

if error_kind=="INFRASTRUCTURE_FAILURE":sys.exit(2)
