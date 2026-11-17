"""Independent native replay and exact source sweep of one endpoint115 execution."""
import argparse,ast,json,math,os,sys,struct
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--result',required=True);p.add_argument('--output',required=True);p.add_argument('--cpu',type=int,required=True);a=p.parse_args()
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.sched_setaffinity(0,[a.cpu]);os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import digest,atomic_json
from swept_cylinder_reference import triangle_linear_sweep_distance
import numpy as np,habitat_sim
from habitat_sim.utils.common import quat_from_coeffs
m=json.loads(Path(a.manifest).read_text());d=json.loads(Path(a.result).read_text());assert digest(__file__)==m['auditor_sha256'] and d['guard_manifest_sha256']==digest(a.manifest) and d['script_sha256']==m['worker_sha256']
assert digest(m['profile_path'])==m['profile_sha256'];profile=json.loads(Path(m['profile_path']).read_text());tpath=Path(m['task_paths'][d['task_key']]);assert digest(tpath)==m['task_files'][d['task_key']];t=json.loads(tpath.read_text());assert t['targets']==d['targets'] and t['start_rotation']==d['rotation'] and t['source_record_sha256']==d['source_record_sha256']
asset=profile['assets'][f"mp3d/{t['scene']}/{t['scene']}.glb"];assert digest(asset['navmesh_path'])==asset['navmesh_sha256']==d['mesh_sha256'];geo_path=Path(m['native_geometry']['receipt_path']);assert digest(geo_path)==m['native_geometry']['receipt_sha256'];geo=json.loads(geo_path.read_text());gp=Path(geo['native_geometry_path']);assert digest(gp)==geo['native_geometry_sha256']==d['native_geometry_sha256'];raw=gp.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);assert len(raw)==8+12*nv+12*nt;vertices=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=vertices[ix].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);cache={};regions={}
helper=R/'tests/landmark_diagnostics/audit_prb_step_interpretations.py';assert digest(helper)==m['independent_sweep_traversal_sha256'];functions=[n for n in ast.parse(helper.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='sweep'];assert len(functions)==1;exec(compile(ast.Module(body=functions,type_ignores=[]),str(helper),'exec'))
assert digest(R/'tests/landmark_diagnostics/swept_cylinder_reference.py')==m['sweep_helper_sha256']
assert len(d['positions'])==len(d['actions'])+1 and len(d['actions'])<=10000 and all(x in (1,2,3) for x in d['actions']) and np.isfinite(d['positions']).all()
logged=[json.loads(line) for line in Path(d['executed_steps_path']).read_text().splitlines()];assert len(logged)==len(d['actions']) and all(r['action_index']==i and r['action']==d['actions'][i] and r['finite'] and ast.literal_eval(r['position_repr'])==d['positions'][i+1] for i,r in enumerate(logged))
cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;agent.sensor_specifications=[];agent.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))};sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));assert sim.pathfinder.load_nav_mesh(asset['navmesh_path']);state=habitat_sim.AgentState();state.position=t['targets'][0];state.rotation=quat_from_coeffs(t['start_rotation']);sim.initialize_agent(0,state)
positions=[sim.get_agent(0).get_state().position.tolist()];err=math.dist(positions[0],d['positions'][0]);alerts=[]
def check_pose(point,i):
    hit=sweep(point,point)
    if hit:alerts.append({'position':i,'kind':'source_pose',**hit})
    if not sim.pathfinder.is_navigable(point):alerts.append({'position':i,'kind':'offmesh'})
check_pose(positions[0],0)
for i,action in enumerate(d['actions'],1):
    before=positions[-1];sim.step(action);after=sim.get_agent(0).get_state().position.tolist();positions.append(after);err=max(err,math.dist(after,d['positions'][i]));check_pose(after,i);hit=sweep(before,after)
    if hit:alerts.append({'position':i,'kind':'source_sweep',**hit})
    if abs(after[1]-before[1])>.5 or math.hypot(after[0]-before[0],after[2]-before[2])>((.25 if action==1 else 0)+1e-4):alerts.append({'position':i,'kind':'displacement'})
assert err<=1e-5;assert [b['reference_index'] for b in d['boundaries']]==list(range(1,len(d['boundaries'])+1));previous=0
for b in d['boundaries']:
    index=b['action_index'];assert previous<=index<len(positions) and index-previous<=1500;previous=index;q=habitat_sim.ShortestPath();q.requested_start=positions[index];q.requested_end=t['targets'][b['reference_index']];assert sim.pathfinder.find_path(q) and q.geodesic_distance<=.25
if d['status']=='PASS_DIAGNOSTIC':assert not d['error'] and len(d['boundaries'])==len(t['targets'])-1
else:assert d['status']=='FAILED_DIAGNOSTIC' and d['error']
contradiction=bool(alerts) and (d['status']=='PASS_DIAGNOSTIC' or d['error_kind']=='SEARCH_OR_BUDGET_FAILURE')
result={'task_key':d['task_key'],'status':'INDEPENDENT_CONTRADICTION' if contradiction else 'PASS_STRICT_MOTION_REPLAY' if d['status']=='PASS_DIAGNOSTIC' else 'FAILURE_PRESERVED','worker_status':d['status'],'error':d['error'],'error_kind':d['error_kind'],'source_alerts':alerts,'max_replay_error':err,'actions':len(d['actions']),'completed_targets':len(d['boundaries']),'expected_targets':len(t['targets'])-1,'result_sha256':digest(a.result),'manifest_sha256':digest(a.manifest),'auditor_sha256':digest(__file__),'independent_replay':True,'strict_sweep':'exact_continuous_linear','limits':'Native Oracle reachability diagnostic, not model evaluation; finite search failure is not proof of impossibility.'}
sim.close();assert not Path(a.output).exists();atomic_json(a.output,result)
if contradiction:sys.exit(3)
