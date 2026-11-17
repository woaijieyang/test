"""Actual native counterexamples: planning rejection matches unchanged execution gate."""
import ast,json,math,os,sys
from pathlib import Path
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
from workspace import atomic_json,digest
from robust_oracle import RobustOracle
import habitat_sim
from habitat_sim.utils.common import quat_from_coeffs
B=R/'outputs/connectivity/endpoint115-full-motion-v1';O=R/'outputs/connectivity/endpoint115-horizontal-planner-regression-v1';O.mkdir(exist_ok=False)
w=R/'tests/landmark_diagnostics/endpoint115_motion_worker_v2.py';tree=ast.parse(w.read_text());cls=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='BodyOracle'];assert len(cls)==1
# This narrow native displacement test isolates the new rejection before source sweep.
# Full source checks remain active in the actual worker and full independent run.
continuous_clear=lambda a,b:True;stats={'rejected_transitions':0};exec(compile(ast.Module(body=cls,type_ignores=[]),str(w),'exec'))
rows=json.loads((B/'results-index.json').read_text());selected=[];scenes=set()
for row in rows:
 if row.get('error')!="AssertionError('actual_horizontal_limit')":continue
 d=json.loads(Path(row['result_path']).read_text());scene=d['task_key'].split('|')[3]
 if scene in scenes:continue
 selected.append(row);scenes.add(scene)
 if len(selected)==3:break
assert len(selected)>=2
cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;a=habitat_sim.agent.AgentConfiguration();a.height=1.5;a.radius=.1;a.sensor_specifications=[];a.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))};sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[a]));planner=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[a]));proof=[]
for row in selected:
 d=json.loads(Path(row['result_path']).read_text());scene=d['task_key'].split('|')[3].split('/')[1];m=json.loads((B/'scenes'/(scene+'.json')).read_text());assert digest(B/'scenes'/(scene+'.json'))==d['guard_manifest_sha256'];p=json.loads(Path(m['profile_path']).read_text());asset=p['assets'][f'mp3d/{scene}/{scene}.glb'];assert digest(asset['navmesh_path'])==d['mesh_sha256']
 for s in [sim,planner]:assert s.pathfinder.load_nav_mesh(asset['navmesh_path'])
 st=habitat_sim.AgentState();st.position=d['targets'][0];st.rotation=quat_from_coeffs(d['rotation']);sim.initialize_agent(0,st)
 for action in d['actions'][:-1]:sim.step(action)
 target=d['targets'][len(d['boundaries'])+1];original=RobustOracle(sim,planner,target);fixed=BodyOracle(sim,planner,target);state=original.snapshot(sim);assert math.dist(state[0],d['positions'][-2])<=1e-5
 proposed=original.transition(state,d['actions'][-1]);assert proposed is not None;distance=math.hypot(float(proposed[0][0]-state[0][0]),float(proposed[0][2]-state[0][2]));assert distance>.2501 and math.dist(proposed[0],d['positions'][-1])<=1e-5
 assert fixed.transition(state,d['actions'][-1]) is None
 turns=[]
 for action in [2,3]:
  old=original.transition(state,action);new=fixed.transition(state,action);assert old is not None and new is not None and math.dist(old[0],new[0])==0;turns.append(action)
 proof.append({'task_key':d['task_key'],'source_result_sha256':digest(row['result_path']),'horizontal_m':distance,'old_planner_accepts':True,'new_planner_rejects':True,'legal_turns_unchanged':turns})
for s in [sim,planner]:s.close()
atomic_json(O/'validation.json',{'status':'PASS_NATIVE_RECORDED_OVERSTEP_REJECTION','records':proof,'worker_v1_sha256':digest(R/'tests/landmark_diagnostics/endpoint115_motion_worker.py'),'worker_v2_sha256':digest(w),'script_sha256':digest(__file__),'limits':'Tests actualnative displacement only. Source callback is permissive solely to isolate this earlier rejection; not a source-contact or full-route acceptance test. Full worker retains exact source guard and independent execution audit.'});print('native counterexamples validated',len(proof))
