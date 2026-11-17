"""Native Agent fixtures for an experimental source collision response."""
import os,sys,json,math,struct,datetime
from pathlib import Path
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from source_collision_filter import SourceCollisionFilter
from swept_cylinder_reference import triangle_linear_sweep_distance
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import numpy as np,quaternion,habitat_sim
O=R/'outputs/connectivity/source-collision-filter-fixtures-v1';O.mkdir(exist_ok=False)
B=R/'outputs/landmark-connectivity/tiled-navmesh-fixture-v3'
reference=json.loads((R/'outputs/connectivity/pathfinder-height-boundary-binding-v2/validation.json').read_text());binding=Path(habitat_sim._ext.habitat_sim_bindings.__file__);assert digest(binding)==reference['control_binding_sha256']
def execute(pf,geometry,start,reverse,guarded):
    def sweep(a,b):
        for i,triangle in enumerate(geometry):
            d=triangle_linear_sweep_distance(triangle,np.array(a),np.array(b))
            if d<.1-1e-6:return {'triangle':i,'distance':float(d)}
        return None
    guard=SourceCollisionFilter(pf.try_step,pf.is_navigable,sweep)
    graph=habitat_sim.SceneGraph();config=habitat_sim.AgentConfiguration();config.height=1.5;config.radius=.1;config.sensor_specifications=[];config.action_space={'move_forward':habitat_sim.ActionSpec('move_forward',habitat_sim.ActuationSpec(amount=.25))}
    controls=habitat_sim.agent.controls.ObjectControls(move_filter_fn=guard if guarded else pf.try_step)
    agent=habitat_sim.Agent(graph.get_root_node().create_child(),config,controls=controls)
    state=habitat_sim.AgentState();state.position=start;state.rotation=quaternion.from_rotation_vector([0,math.pi/2 if reverse else -math.pi/2,0]);agent.set_state(state);positions=[agent.get_state().position.tolist()];collisions=[]
    for _ in range(6):collisions.append(bool(agent.act('move_forward')));positions.append(agent.get_state().position.tolist())
    contacts=[i for i,(a,b) in enumerate(zip(positions,positions[1:])) if sweep(a,b) is not None]
    return {'positions':positions,'collisions':collisions,'guard_events':guard.events,'contact_segments':contacts}
rows=[]
for resolution in ['uniform','mixed']:
    mesh=B/(resolution+'_floor.navmesh');pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(str(mesh));raw=(B/(resolution+'_floor.geometry.bin')).read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);vertices=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);indices=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);floor=vertices[indices].astype(float)
    for mode in ['floor','source_wall_omitted_from_navmesh','above_body_wall']:
        if mode=='floor':geometry=floor
        else:
            y0=0 if mode=='source_wall_omitted_from_navmesh' else 2.;y1=y0+2.5;wall=np.array([[[.875,y0,-1],[.875,y1,-1],[.875,y1,2]],[[.875,y0,-1],[.875,y1,2],[.875,y0,2]]]);geometry=np.concatenate([floor,wall])
        for reverse in [False,True]:
            start=list(pf.snap_point([1.75 if reverse else .25,0,.5]));expected=list(pf.snap_point([.25 if reverse else 1.75,0,.5]))
            original=execute(pf,geometry,start,reverse,False);first=execute(pf,geometry,start,reverse,True);second=execute(pf,geometry,start,reverse,True)
            assert first==second and not first['contact_segments'] and all(pf.is_navigable(p) for p in first['positions'])
            if mode=='source_wall_omitted_from_navmesh':
                assert original['contact_segments'] and math.dist(original['positions'][-1],expected)<=1e-5
                assert any(first['collisions']) and math.dist(first['positions'][-1],expected)>.25
                assert all(p[0]>=.975-1e-5 if reverse else p[0]<=.775+1e-5 for p in first['positions'])
                assert any(e['rejected_reason']=='exact_source_swept_contact' for e in first['guard_events'])
            else:
                assert first['positions']==original['positions'] and first['collisions']==original['collisions']
                assert math.dist(first['positions'][-1],expected)<=1e-5 and all(e['rejected_reason'] is None for e in first['guard_events'])
            for event,after in zip(first['guard_events'],first['positions'][1:]):
                assert after==(event['before'] if event['rejected_reason'] else event['native_candidate'])
            rows.append({'resolution':resolution,'mode':mode,'reverse':reverse,'native_control':original,'guarded':first,'independent_agent_replay_identical':True,'mesh_sha256':digest(mesh)})
    bad_start=list(pf.snap_point([.875,0,.5]));wall=np.array([[[.875,0,-1],[.875,2.5,-1],[.875,2.5,2]],[[.875,0,-1],[.875,2.5,2],[.875,0,2]]])
    try:execute(pf,np.concatenate([floor,wall]),bad_start,False,True)
    except RuntimeError as error:assert str(error)=='invalid_initial_source_body'
    else:raise AssertionError('invalid initial state silently accepted')
atomic_json(O/'validation.json',{'status':'PASS_EXPERIMENTAL_FILTER_NATIVE_FIXTURES_NOT_PROTOCOL_ADOPTION','direction_cases':len(rows),'guarded_agent_executions':24,'guarded_primitive_actions':144,'initial_invalid_rejections':2,'records':rows,'binding_sha256':digest(binding),'filter_sha256':digest(R/'tests/landmark_diagnostics/source_collision_filter.py'),'checker_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat(),'limits':'Explicitly changes collision response when native mesh omits source obstacles. Not installed or authorized as formal protocol. Only originalnative endpoint or unchangedstart returned. Fixedgoal-free physics predicate; no model/goal/reference information. Syntheticfixtures do not prove scene reachability or model accuracy.'})
print('PASS12DIRECTIONS144GUARDEDACTIONS2INVALIDINITIALS')

