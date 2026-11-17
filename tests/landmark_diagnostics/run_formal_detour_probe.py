"""Expose frozen Detour movement/query intermediates using isolated original archives."""
import os,sys,json,subprocess,math,datetime
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
import habitat_sim
from habitat_sim.utils.common import quat_from_coeffs
O=R/'outputs/connectivity/r2r-detour-step-v1';O.mkdir(exist_ok=False)
C=R/'.cache/r2r-detour-step-v1';C.mkdir(exist_ok=False)
receipt=R/'outputs/connectivity/r2r-offmesh-diagnosis-v2/validation.json';diagnosis=json.loads(receipt.read_text())
profile=json.loads((R/'data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json').read_text())
command_record=json.loads((R/'outputs/landmark-connectivity/tiled-navmesh-fixture-v3/commands.json').read_text())
archives=command_record['archives_before'];assert all(digest(p)==h for p,h in archives.items())
source=R/'tests/landmark_diagnostics/probe_detour_step.cpp'
compile_args=[str(source) if x.endswith('/tiled_navmesh_fixture.cpp') else x for x in command_record['compile']]
compile_args[compile_args.index('-o')+1]=str(C/'probe')
atomic_json(O/'compile-command.json',{'command':compile_args,'archives':archives,'source_sha256':digest(source)})
with (O/'compile.log').open('xb') as log:subprocess.run(compile_args,stdout=log,stderr=subprocess.STDOUT,check=True)
records=[]
for i,r in enumerate(diagnosis['records']):
    asset=profile['assets'][r['scene']];assert digest(asset['navmesh_path'])==r['mesh_sha256']
    cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False
    ac=habitat_sim.agent.AgentConfiguration();ac.height=1.5;ac.radius=.1;ac.sensor_specifications=[];ac.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25))}
    sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[ac]));assert sim.pathfinder.load_nav_mesh(asset['navmesh_path'])
    normalized=O/(r['scene'].split('/')[1]+'.navmesh')
    if not normalized.exists():assert sim.pathfinder.save_nav_mesh(str(normalized))
    state=habitat_sim.AgentState();state.position=r['before']['position'];state.rotation=quat_from_coeffs(r['before']['rotation_xyzw']);agent=sim.initialize_agent(0,state)
    original_filter=agent.controls.move_filter_fn
    # Diagnostic unfiltered desired endpoint only. It is not an executed proof or accepted trajectory.
    agent.controls.move_filter_fn=lambda start,end:end
    sim.step(1);desired=sim.get_agent(0).get_state().position.tolist()
    agent.controls.move_filter_fn=original_filter
    sim.initialize_agent(0,state);sim.step(1);actual=sim.get_agent(0).get_state().position.tolist();assert math.dist(actual,r['actual'])==0
    cmd=[str(C/'probe'),str(normalized),*[str(x) for x in r['before']['position']],*[str(x) for x in desired],*[str(x) for x in r['actual']]]
    proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True);(O/(str(i)+'.raw.json')).write_text(proc.stdout);probe=json.loads(proc.stdout)
    projection_error=math.dist(probe['projected_observed'],r['snap_query_only']);movement_error=math.dist(probe['move_after_height'],r['actual'])
    assert projection_error<1e-6 and movement_error<1e-4,('control_mismatch',projection_error,movement_error)
    records.append({'task_key':r['task_key'],'desired_unfiltered_probe_only':desired,'normalized_mesh_sha256':digest(normalized),
                    'projection_control_error':projection_error,'movement_control_error':movement_error,**probe})
    sim.close()
assert all(digest(p)==h for p,h in archives.items())
atomic_json(O/'validation.json',{'status':'PASS_FROZEN_DETOUR_INTERMEDIATE_CONTROL_NOT_REPAIR','records':records,
    'diagnosis_sha256':digest(receipt),'source_sha256':digest(source),'script_sha256':digest(__file__),'binary_sha256':digest(C/'probe'),
    'original_archives_unchanged':True,'time':datetime.datetime.now().astimezone().isoformat(),
    'limits':'Private query replica omits Habitat island-system nudge. Movement and projection errors explicitly checked against original binding. No installed libraries, source geometry, model inputs, or recorded trajectories changed.'})
print([{k:r[k] for k in ['task_key','movement_control_error','projection_control_error','height_status','observed_over_last_polygon','last_visited_ref','observed_nearest_ref']} for r in records])

