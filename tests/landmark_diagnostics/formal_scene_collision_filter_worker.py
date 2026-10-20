"""Frozen complete-scene action replay; never a replacement model evaluation."""
import argparse,ast,datetime,gzip,json,math,os,resource,struct,sys
from pathlib import Path
P=argparse.ArgumentParser();P.add_argument('--manifest',required=True);P.add_argument('--condition',required=True);P.add_argument('--cpu',type=int,required=True);args=P.parse_args()
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
from source_collision_filter import SourceCollisionFilter
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.sched_setaffinity(0,[args.cpu]);os.nice(15);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
import numpy as np,habitat_sim
from habitat_sim.utils.common import quat_from_coeffs
m=json.loads(Path(args.manifest).read_text());c=m['conditions'][args.condition]
assert digest(__file__)==m['worker_sha256'];assert digest(R/'tests/landmark_diagnostics/source_collision_filter.py')==m['filter_sha256']
binding=Path(habitat_sim._ext.habitat_sim_bindings.__file__)
assert digest(binding)==c['binding_sha256']
profile=json.loads(Path(c['profile_path']).read_text());assert digest(c['profile_path'])==c['profile_sha256'];asset=profile['assets'][m['scene_id']];assert digest(asset['navmesh_path'])==asset['navmesh_sha256']
native=Path(m['native_geometry_path']);assert digest(native)==m['native_geometry_sha256'];raw=native.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);assert len(raw)==8+12*nv+12*nt;vertices=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);indices=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=vertices[indices].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);cache={};regions={}
helper=Path(m['sweep_traversal_path']);assert digest(helper)==m['sweep_traversal_sha256'];functions=[n for n in ast.parse(helper.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='sweep'];assert len(functions)==1;exec(compile(ast.Module(body=functions,type_ignores=[]),str(helper),'exec'),globals())
O=Path(args.manifest).parent/args.condition;O.mkdir(exist_ok=False);(O/'episodes').mkdir();atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':args.cpu})
cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;ac=habitat_sim.agent.AgentConfiguration();ac.height=1.5;ac.radius=.1;ac.sensor_specifications=[];ac.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))}
sims=[habitat_sim.Simulator(habitat_sim.Configuration(cfg,[ac])) for _ in range(2)];sim,replay=sims
filters=[]
for s in sims:
    assert s.pathfinder.load_nav_mesh(asset['navmesh_path'])
    controls=s.get_agent(0).controls
    filtered=SourceCollisionFilter(controls.move_filter_fn,s.pathfinder.is_navigable,sweep)
    controls.move_filter_fn=filtered
    filters.append(filtered)
rows=[]
try:
    for original in m['records']:
        trace=Path(original['trace_path']);assert digest(trace)==original['trace_sha256'];events=list(map(json.loads,trace.read_text().splitlines()));assert events[0]['kind']=='reset' and events[-1]['kind']=='terminal'
        assert all(e['task_key']==original['task_key'] for e in events)
        action_events=[e for e in events if e['kind']=='primitive_action'];actions=[e['action'] for e in action_events];assert all(a in (0,1,2,3) for a in actions)
        reset=events[0]['state_evaluator_only'];state=habitat_sim.AgentState();state.position=reset['position'];state.rotation=quat_from_coeffs(reset['rotation_xyzw'])
        for s in sims:s.initialize_agent(0,state)
        positions=[sim.get_agent(0).get_state().position.tolist()];original_positions=[reset['position']]+[e['after_evaluator_only']['position'] for e in action_events]
        for f in filters:f.events.clear()
        initial_contact=sweep(positions[0],positions[0])
        if initial_contact is not None or not sim.pathfinder.is_navigable(positions[0]):
            output=O/'episodes'/(original['trace_sha256']+'.json.gz')
            payload={'task_key':original['task_key'],'condition':args.condition,'status':'INITIAL_SOURCE_BLOCKED_PRESERVED','manifest_sha256':digest(args.manifest),'positions':positions,'original_actions':actions,'actions':[],'rotation':reset['rotation_xyzw'],'source_trace_sha256':original['trace_sha256'],'initial_source_contact':initial_contact,'native_navigable':bool(sim.pathfinder.is_navigable(positions[0])),'limits':'Initialpose is not modified; all132 remain in denominator. No executed trajectory claimed.'}
            with gzip.open(output,'xt') as f:json.dump(payload,f)
            rows.append({'task_key':original['task_key'],'status':payload['status'],'actions':0,'original_action_count':len(actions),'executed':False,'result_path':str(output),'result_sha256':digest(output)})
            atomic_json(O/'state.json',{'status':'RUNNING_SOURCE_FILTER_DIAGNOSTIC','completed':len(rows),'expected':len(m['records'])})
            continue

        offmesh=[];body=[];chords=[];vertical=[];replay_error=0.
        for i in range(len(actions)+1):
            if i:
                action=actions[i-1]
                if action:
                    before_count=len(filters[0].events);sim.step(action);replay.step(action)
                    for event in filters[0].events[before_count:]:event['action_index']=i
                positions.append(sim.get_agent(0).get_state().position.tolist())
            p=positions[-1];assert all(math.isfinite(v) for v in p)
            replay_error=max(replay_error,math.dist(p,replay.get_agent(0).get_state().position.tolist()))
            if not sim.pathfinder.is_navigable(p):offmesh.append({'index':i,'position':p})
            hit=sweep(p,p)
            if hit:body.append({'index':i,**hit})
            if i:
                if abs(p[1]-positions[-2][1])>.5:vertical.append(i)
                hit=sweep(positions[-2],p)
                if hit:chords.append({'index':i,**hit})
        assert replay_error<=1e-5
        assert not offmesh and not body and not chords and not vertical
        assert len(filters[0].events)==len(filters[1].events)
        assert [{k:v for k,v in e.items() if k!='action_index'} for e in filters[0].events]==filters[1].events
        deviations=[math.dist(a,b) for a,b in zip(positions,original_positions)];maximum=max(deviations)
        if args.condition=='original_control':assert maximum<=1e-5,('native_control_mismatch',original['task_key'],maximum)
        status='STRICT_SOURCE_CLEAR_OPENLOOP_ONLY' if not (offmesh or body or chords or vertical) else 'OPENLOOP_GATE_FAILURE_PRESERVED'
        output=O/'episodes'/(original['trace_sha256']+'.json.gz')
        payload={'task_key':original['task_key'],'condition':args.condition,'status':status,'manifest_sha256':digest(args.manifest),'positions':positions,'actions':actions,'rotation':reset['rotation_xyzw'],'source_trace_sha256':original['trace_sha256'],'filter_events':filters[0].events[:],'filter_sha256':m['filter_sha256'],'offmesh':offmesh,'body_contacts':body,'chord_contacts':chords,'vertical_failures':vertical,'replay_error':replay_error,'max_difference_from_original':maximum,'changed_position_count':sum(d>1e-5 for d in deviations)}
        with gzip.open(output,'xt') as f:json.dump(payload,f)
        rows.append({'task_key':original['task_key'],'status':status,'actions':len(actions),'executed':True,'filter_rejections':sum(e['rejected_reason'] is not None for e in filters[0].events),'offmesh_count':len(offmesh),'body_contact_count':len(body),'chord_contact_count':len(chords),'vertical_failure_count':len(vertical),'replay_error':replay_error,'max_difference_from_original':maximum,'result_path':str(output),'result_sha256':digest(output)})
        atomic_json(O/'state.json',{'status':'RUNNING_COMPLETE_SCENE_OPENLOOP','completed':len(rows),'expected':len(m['records'])})
    assert len(rows)==len(m['records']) and {r['task_key'] for r in rows}=={r['task_key'] for r in m['records']}
    atomic_json(O/'validation.json',{'status':'COMPLETE_SCENE_OPENLOOP_NOT_MODEL_EVALUATION','records':rows,'expected':len(rows),'binding_sha256':digest(binding),'mesh_sha256':asset['navmesh_sha256'],'manifest_sha256':digest(args.manifest),'worker_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat(),'limits':'Experimental collision response changes simulator behavior; NOT adopted or a model evaluation. All132 tasks retained, initial12 source blockers not moved. Source filter can only accept nativeendpoint or rejectto unchangedstart, no intermediatepose, GT policy or new SR.'})
    atomic_json(O/'state.json',{'status':'COMPLETE_SCENE_OPENLOOP_NOT_ACCEPTANCE','completed':len(rows),'strict_clear':sum(r['status']=='STRICT_SOURCE_CLEAR_OPENLOOP_ONLY' for r in rows)})
except Exception as error:atomic_json(O/'state.json',{'status':'FAILED_DIAGNOSTIC_PRESERVED','completed':len(rows),'error':repr(error)});raise
finally:
    for s in sims:s.close()

