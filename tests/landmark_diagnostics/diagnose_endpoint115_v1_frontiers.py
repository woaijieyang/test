"""Diagnose every v1 search-frontier failure without rerunning navigation searches."""
import ast,collections,datetime,json,math,os,struct,sys
from pathlib import Path
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import digest,atomic_json
from swept_cylinder_reference import triangle_linear_sweep_distance
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
import numpy as np,habitat_sim,psutil
from habitat_sim.utils.common import quat_from_coeffs
usage=psutil.cpu_percent(interval=1,percpu=True);eligible=[i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i]<15 and i not in [1,7,8,9,6,12,18,20,22,24,27,30]];assert eligible;os.sched_setaffinity(0,[min(eligible,key=lambda i:usage[i])])
B=R/'outputs/connectivity/endpoint115-full-motion-v1';O=R/'outputs/connectivity/endpoint115-v1-frontier-diagnostic-v1';O.mkdir(exist_ok=False)
rows=json.loads((B/'results-index.json').read_text());selected=[r for r in rows if r.get('error_kind')=='SEARCH_OR_BUDGET_FAILURE' and r['error']!="RuntimeError('legal_action_search_exhausted:5000')"];assert selected
helper=R/'tests/landmark_diagnostics/audit_prb_step_interpretations.py';functions=[n for n in ast.parse(helper.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='sweep'];assert len(functions)==1;exec(compile(ast.Module(body=functions,type_ignores=[]),str(helper),'exec'))
cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;a=habitat_sim.agent.AgentConfiguration();a.height=1.5;a.radius=.1;a.sensor_specifications=[];a.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))};sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[a]));planner=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[a]));reports=[];previous_scene=None
for row in selected:
 assert digest(row['result_path'])==row['result_sha256'] and digest(row['audit_path'])==row['audit_sha256'];d=json.loads(Path(row['result_path']).read_text());scene=d['task_key'].split('|')[3].split('/')[1];m=json.loads((B/'scenes'/(scene+'.json')).read_text());assert digest(B/'scenes'/(scene+'.json'))==d['guard_manifest_sha256'];profile=json.loads(Path(m['profile_path']).read_text());asset=profile['assets'][f'mp3d/{scene}/{scene}.glb'];assert digest(asset['navmesh_path'])==d['mesh_sha256'];assert digest(helper)==m['independent_sweep_traversal_sha256']
 if scene!=previous_scene:
  geo=json.loads(Path(m['native_geometry']['receipt_path']).read_text());assert digest(m['native_geometry']['receipt_path'])==m['native_geometry']['receipt_sha256'];raw=Path(geo['native_geometry_path']).read_bytes();assert digest(geo['native_geometry_path'])==geo['native_geometry_sha256'];nv,nt=struct.unpack('<ii',raw[:8]);v=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+12*nv).reshape(nt,3);tri=v[ix].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);cache={};regions={}
  for s in [sim,planner]:assert s.pathfinder.load_nav_mesh(asset['navmesh_path'])
  previous_scene=scene
 state=habitat_sim.AgentState();state.position=d['targets'][0];state.rotation=quat_from_coeffs(d['rotation']);sim.initialize_agent(0,state)
 for action in d['actions']:sim.step(action)
 state=sim.get_agent(0).get_state();start=state.position.tolist();assert math.dist(start,d['positions'][-1])<=1e-5;target=d['targets'][len(d['boundaries'])+1];probes=[]
 for action in [1,2,3]:
  planner.get_agent(0).set_state(state);before=planner.get_agent(0).get_state().position.tolist();planner.step(action);end=planner.get_agent(0).get_state().position.tolist();q=habitat_sim.ShortestPath();q.requested_start=end;q.requested_end=target;connected=bool(planner.pathfinder.find_path(q) and math.isfinite(q.geodesic_distance));probes.append({'action':action,'start_after_set_state':before,'end':end,'horizontal_m':math.hypot(end[0]-start[0],end[2]-start[2]),'vertical_m':abs(end[1]-start[1]),'navigable':bool(planner.pathfinder.is_navigable(end)),'target_connected':connected,'source_pose_contact':sweep(end,end),'source_sweep_contact':sweep(start,end)})
 reports.append({'task_key':d['task_key'],'failure':d['error'],'result_sha256':row['result_sha256'],'prefix_actions':len(d['actions']),'last_actual_position':start,'last_actual_source_contact':sweep(start,start),'next_target':target,'probes':probes})
for s in [sim,planner]:s.close()
atomic_json(O/'validation.json',{'status':'COMPLETE_RECORDED_FRONTIER_NATIVE_PROBES_NOT_ROUTE_ACCEPTANCE','records':reports,'count':len(reports),'source_results_index_snapshot_sha256':digest(B/'results-index.json'),'script_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat(),'limits':'No added search budget or alternative trajectories. Exhausted frontiers are algorithmic failures, not physical impossibility. Probes use separate simulator reset; actual execution prefixes remain unchanged.'});print('frontiers',len(reports))
