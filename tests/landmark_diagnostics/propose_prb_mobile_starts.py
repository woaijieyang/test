"""Separate true lack of legal forward actions from coarse search-key aliasing at six starts."""
import os,sys,json,math,ast,struct,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from robust_oracle import RobustOracle
from projected_distance_reference import projected_distance
from swept_cylinder_reference import triangle_linear_sweep_distance
import numpy as np,habitat_sim,psutil
from habitat_sim.utils.common import quat_from_coeffs
u=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:u[i])]);B=R/'outputs/landmark-connectivity';run=B/'full-source-guard-pRb-detail-exact-v1';O=B/'prb-start-mobility-candidates-v1';O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});m=json.loads((run/'guarded/manifest.json').read_text());v=json.loads((run/'guarded/validation.json').read_text());selected=[r for r in v['results'] if r.get('error')=="RuntimeError('legal_action_search_exhausted:24')"];assert len(selected)==6;assert digest(m['candidate_tasks_path'])==m['candidate_tasks_sha256'];tasks={t['task_key']:t for t in json.loads(Path(m['candidate_tasks_path']).read_text())['tasks']};geo=json.loads(Path(m['native_geometry']['receipt_path']).read_text());assert digest(geo['native_geometry_path'])==geo['native_geometry_sha256'];raw=Path(geo['native_geometry_path']).read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);vv=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=vv[ix].astype(float)
worker=R/'tests/landmark_diagnostics/source_guard_repaired_profile_exact_worker.py';helper=R/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';assert digest(worker)==m['worker_sha256'] and digest(helper)==m['helper_sha256'];wt=ast.parse(worker.read_text());ht=ast.parse(helper.read_text());defs=[next(n for n in ht.body if isinstance(n,ast.FunctionDef) and n.name=='clip')]+[next(n for n in wt.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name) for name in ['safe','continuous_clear','BodyOracle']];ns={'np':np,'math':math,'tri':tri,'lo':tri.min(axis=1),'hi':tri.max(axis=1),'regioncache':{},'posecache':{},'transition_cache':{},'sweep_regions':{},'stats':{'checked_poses':0,'rejected_poses':0,'rejected_transitions':0},'distance':projected_distance,'triangle_linear_sweep_distance':triangle_linear_sweep_distance,'RobustOracle':RobustOracle};exec(compile(ast.Module(body=defs,type_ignores=[]),str(worker),'exec'),ns);BodyOracle=ns['BodyOracle']
profile=json.loads(Path(m['profile_path']).read_text());asset=profile['assets']['mp3d/pRbA3pwrgk9/pRbA3pwrgk9.glb'];assert digest(m['profile_path'])==m['profile_sha256'] and digest(asset['navmesh_path'])==asset['navmesh_sha256'];cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;a=habitat_sim.agent.AgentConfiguration();a.height=1.5;a.radius=.1;a.sensor_specifications=[];a.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))};sims=[habitat_sim.Simulator(habitat_sim.Configuration(cfg,[a])) for _ in range(2)];sim,planner=sims
for x in sims:assert x.pathfinder.load_nav_mesh(asset['navmesh_path'])
prior_path=Path(m['proposal_rows_path']);assert digest(prior_path)==m['proposal_rows_sha256'];prior=json.loads(prior_path.read_text());prior_rows={r['task_key']:r for r in prior['rows']};old_tasks=json.loads(Path(m['candidate_tasks_path']).read_text())['tasks'];new_tasks=json.loads(json.dumps(old_tasks));new_index={t['task_key']:t for t in new_tasks};new_rows=json.loads(json.dumps(prior['rows']));row_index={r['task_key']:r for r in new_rows};initial_proof=B/'prb-initial-action-key-audit-v1/validation.json';ip=json.loads(initial_proof.read_text());assert ip['profile_sha256']==m['profile_sha256'] and all(r['source_legal_directions']==0 for r in ip['records']);rings=[(r*math.cos(i*2*math.pi/n),r*math.sin(i*2*math.pi/n)) for r,n in ((.1,18),(.15,30),(.2,36),(.25,48),(.3,60),(.35,72)) for i in range(n)];reports=[];changed=[]
def initialize(task,q,target_sim):
 yaw=(-task['heading']+math.pi)%(2*math.pi)-math.pi;st=habitat_sim.AgentState();st.position=q;st.rotation=quat_from_coeffs([0,math.sin(yaw/2),0,math.cos(yaw/2)]);target_sim.initialize_agent(0,st)
def eligible_move(task,q):
 initialize(task,q,sim);oracle=BodyOracle(sim,planner,task['targets'][1],radius=.25,max_nodes=5000)
 for k in range(24):
  state=oracle.snapshot(sim);new=oracle.transition(state,1)
  if new is not None:
   initialize(task,q,sim);positions=[sim.get_agent(0).get_state().position.tolist()];actions=[2]*k+[1]
   for action in actions:
    sim.step(action);end=sim.get_agent(0).get_state().position.tolist();assert ns['safe'](end) and ns['continuous_clear'](np.array(positions[-1]),np.array(end));assert abs(end[1]-positions[-1][1])<=.5;positions.append(end)
   assert math.dist(positions[-1],new[0])<=1e-5;initialize(task,q,planner);error=0.
   for i,action in enumerate(actions):planner.step(action);error=max(error,math.dist(planner.get_agent(0).get_state().position,positions[i+1]))
   assert error<=1e-5 and oracle.searches==0
   return {'actions':actions,'positions':positions,'replay_error':error,'translation_m':math.dist(positions[-1],positions[0]),'search_nodes_expanded':0}
  sim.step(2)
 return None
for result in selected:
 task=tasks[result['task_key']];old=task['targets'][0];choice=prior_rows[task['task_key']]['choices'][0];anchor=choice['anchor'];kind=choice['anchor_kind'];camera=choice['camera'];candidates={};rejections={}
 for rank,seed in [(0,old),(2,anchor)]+[(3,[anchor[0]+dx,anchor[1],anchor[2]+dz]) for dx,dz in rings]:
  q=list(sim.pathfinder.snap_point(seed));key=tuple(q)
  if not all(math.isfinite(x) for x in q) or not sim.pathfinder.is_navigable(q) or math.dist(q,list(sim.pathfinder.snap_point(q)))>1e-5:continue
  delta=math.dist(q,anchor)
  if delta>.5 or (rank>=3 and math.hypot(q[0]-anchor[0],q[2]-anchor[2])>.350001):continue
  if kind=='bounded_camera_projection' and not(math.hypot(q[0]-camera[0],q[2]-camera[2])<.5 and 0<=camera[1]-q[1]<=2):continue
  if not ns['safe'](q):continue
  query=habitat_sim.ShortestPath();query.requested_start=q;query.requested_end=task['targets'][1]
  if not sim.pathfinder.find_path(query) or not math.isfinite(query.geodesic_distance):continue
  item={'position':q,'rank':rank,'anchor':anchor,'anchor_kind':kind,'displacement':delta,'camera':camera,'change_from_current_start_m':math.dist(q,old)}
  if key not in candidates or rank<candidates[key]['rank']:candidates[key]=item
 ordered=sorted(candidates.values(),key=lambda c:(c['change_from_current_start_m'],c['displacement'],c['rank'],c['position']));tested=[];winner=None
 for c in ordered:
  # Original exact pose already has a bound24-heading no-exit receipt; do not repeat it.
  if c['position']==old:tested.append({'position':c['position'],'legal_first_action':False,'reused_original24_heading_audit':True});continue
  witness=eligible_move(task,c['position']);tested.append({'position':c['position'],'legal_first_action':witness is not None})
  if witness is not None:winner=(c,witness);break
 record={'task_key':task['task_key'],'old_start':old,'source_anchor':anchor,'source_anchor_kind':kind,'static_candidates':len(ordered),'mobility_candidates_tested':tested,'status':'NO_NEW_MOBILE_START_IN_EXISTING_PROPOSALS'}
 if winner:
  c,witness=winner;new_index[task['task_key']]['targets'][0]=c['position'];new_index[task['task_key']]['mapping_methods'][0]='source_body_guarded_'+kind+'_initial_motion_checked';row_index[task['task_key']]['choices'][0]={k:v for k,v in c.items() if k!='change_from_current_start_m'};row_index[task['task_key']]['changed']=True;record.update(status='BOUNDED_MOBILE_START_PENDING_FULL_ROUTE',new_start=c['position'],change_from_current_start_m=c['change_from_current_start_m'],source_displacement_m=c['displacement'],first_action_witness=witness);changed.append(task['task_key'])
 reports.append(record);atomic_json(O/'state.json',{'status':'RUNNING','completed':len(reports),'expected':6,'mobile_start_candidates':len(changed)})
for x in sims:x.close()
assert len(reports)==6 and len(new_tasks)==660
for oldt,newt in zip(old_tasks,new_tasks):
 assert oldt['task_key']==newt['task_key']
 if oldt['task_key'] not in changed:assert oldt==newt
 else:assert {k:v for k,v in oldt.items() if k not in ['targets','mapping_methods']}=={k:v for k,v in newt.items() if k not in ['targets','mapping_methods']} and oldt['targets'][1:]==newt['targets'][1:]
atomic_json(O/'candidate_tasks.json',{'tasks':new_tasks,'limits':'Only named six failed-task starts may change; all660 retained, remainingtargets/headings/originalsource records unchanged. No adoption.'});atomic_json(O/'mobility-probes.json',{'records':reports,'changed_task_keys':changed,'source_manifest_sha256':digest(run/'guarded/manifest.json'),'original_initial_action_audit_sha256':digest(initial_proof),'script_sha256':digest(__file__),'limits':'Existing bounded ring positions only. A legal first native step and replay are not whole-route proof; unchanged5000 search/actions/geometry. No model episodes rerun.'});atomic_json(O/'validation.json',{'status':'BOUNDED_START_MOBILITY_PROPOSAL_PENDING_INDEPENDENT_AND_FULL_ROUTE','scene':'pRbA3pwrgk9','expected_tasks':660,'rows':new_rows,'changed_task_keys':changed,'counts':{'SOURCE_CLEAR_TARGETS_COMMON_COMPONENT_PENDING_MOTION':660},'parent_manifest_sha256':m['parent_manifest_sha256'],'parent_profile_sha256':m['source_profile_sha256'],'profile_path':m['profile_path'],'profile_sha256':m['profile_sha256'],'native_geometry_receipt_path':m['native_geometry']['receipt_path'],'native_geometry_receipt_sha256':m['native_geometry']['receipt_sha256'],'prior_static_path':str(prior_path),'prior_static_sha256':digest(prior_path),'prior_candidate_tasks_sha256':m['candidate_tasks_sha256'],'mobility_probes_sha256':digest(O/'mobility-probes.json'),'script_sha256':digest(__file__),'limits':'Only bounded initial pose selection changes for originally immobile failures. All660 denominator preserved; independent static verification and fresh complete routes required.'});atomic_json(O/'state.json',{'status':'COMPLETE_PROPOSAL_NOT_ACCEPTED','mobile_start_candidates':len(changed),'changed_task_keys':changed});print('changed',changed)
