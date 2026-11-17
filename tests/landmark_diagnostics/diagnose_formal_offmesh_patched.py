"""Read-only replay of actual formal offmesh findings, never patch recorded states."""
import os,json,math,sys,datetime
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import digest,atomic_json
assert os.environ.get('CASE1_PROTECTION')
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
os.nice(15)
import numpy as np,habitat_sim
from habitat_sim.utils.common import quat_from_coeffs
binding=Path(habitat_sim._ext.habitat_sim_bindings.__file__);binding_receipt=json.loads((R/'outputs/connectivity/pathfinder-height-boundary-binding-v2/validation.json').read_text());assert digest(binding)==binding_receipt['patched_binding_sha256']
report_path=R/'outputs/connectivity/r2r-full-precompletion-v1.json'
audit=json.loads(report_path.read_text());assert audit['status']=='FAIL' and len(audit['errors'])==5
run=R/'outputs/awarevln-r2r-valunseen-endpoint9-20261015-v2'
manifest=json.loads((run/'run_manifest.json').read_text())
profile_path=R/'data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json'
assert digest(profile_path)==manifest['navmesh_sha256']==audit['profile_sha256']
profile=json.loads(profile_path.read_text())
index={r['task_key']:r for r in map(json.loads,(run/'results.jsonl').read_text().splitlines())}
O=R/'outputs/connectivity/r2r-offmesh-patched-replay-v1';O.mkdir(exist_ok=False)
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
rows=[]
for error in audit['errors']:
    row=index[error['task_key']];trace=run/row['trace_path'];assert digest(trace)==row['trace_sha256']
    events=list(map(json.loads,trace.read_text().splitlines()))
    actions=[e for e in events if e['kind']=='primitive_action']
    scene=error['task_key'].split('|')[3];asset=profile['assets'][scene]
    assert digest(asset['navmesh_path'])==asset['navmesh_sha256']
    cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False
    agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;agent.sensor_specifications=[]
    agent.action_space={0:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=0)),1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))}
    sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));assert sim.pathfinder.load_nav_mesh(asset['navmesh_path'])
    reset=events[0]['state_evaluator_only'];state=habitat_sim.AgentState();state.position=reset['position'];state.rotation=quat_from_coeffs(reset['rotation_xyzw']);sim.initialize_agent(0,state)
    maximum=math.dist(sim.get_agent(0).get_state().position,reset['position']);replayed_offmesh=[]
    for i,e in enumerate(actions,1):
        if e['action']!=0:sim.step(e['action'])
        actual=sim.get_agent(0).get_state().position.tolist();maximum=max(maximum,math.dist(actual,e['after_evaluator_only']['position']))
        if not sim.pathfinder.is_navigable(actual):replayed_offmesh.append({'index':i,'position':actual})
    e=actions[error['index']-1];assert e['after_evaluator_only']['position']==error['position']
    before=e['before_evaluator_only'];state.position=before['position'];state.rotation=quat_from_coeffs(before['rotation_xyzw']);sim.initialize_agent(0,state)
    sim.step(e['action']);one=sim.get_agent(0).get_state().position.tolist()
    position=error['position'];snap=list(sim.pathfinder.snap_point(position))
    q=habitat_sim.ShortestPath();q.requested_start=before['position'];q.requested_end=position;connected=sim.pathfinder.find_path(q)
    rows.append({'task_key':error['task_key'],'scene':scene,'action_index':error['index'],'action':e['action'],
                 'before':before,'actual':position,'snap_query_only':snap,'snap_horizontal_m':math.hypot(snap[0]-position[0],snap[2]-position[2]),
                 'snap_vertical_m':abs(snap[1]-position[1]),'original_is_navigable':sim.pathfinder.is_navigable(position),
                 'full_replay_max_error':maximum,'full_replayed_offmesh':replayed_offmesh,
                 'one_step_replayed_position':one,'one_step_error':math.dist(one,position),
                 'one_step_is_navigable':sim.pathfinder.is_navigable(one),'from_before_path_finite':bool(connected and math.isfinite(q.geodesic_distance)),
                 'mesh_sha256':asset['navmesh_sha256'],'trace_sha256':digest(trace)})
    sim.close()
atomic_json(O/'validation.json',{'status':'COMPLETE_PATCHED_OFFMESH_REPLAY_NOT_MODEL_EVALUATION','binding_sha256':digest(binding),'records':rows,'count':len(rows),
    'auditor_receipt_sha256':digest(report_path),'profile_sha256':digest(profile_path),'script_sha256':digest(__file__),
    'time':datetime.datetime.now().astimezone().isoformat(),
    'limits':'Full replay and isolated one-step probe are distinguished. snap_point is queried for diagnosis only; no saved pose or runtime state is corrected during full replay.'})
print([{k:r[k] for k in ['task_key','snap_horizontal_m','snap_vertical_m','full_replay_max_error','one_step_error','one_step_is_navigable']} for r in rows])

