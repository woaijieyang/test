"""Independent native replay and direct source-triangle checks of collision events."""
import argparse,collections,datetime,gzip,json,math,os,struct,sys
from pathlib import Path
P=argparse.ArgumentParser();P.add_argument('--condition',required=True);P.add_argument('--cpu',type=int,required=True);args=P.parse_args()
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from source_collision_filter import SourceCollisionFilter
from swept_cylinder_reference import triangle_linear_sweep_distance
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.sched_setaffinity(0,[args.cpu]);os.nice(15)
import numpy as np,habitat_sim
from habitat_sim.utils.common import quat_from_coeffs
B=R/'outputs/connectivity/eu6-source-collision-response-v1';m=json.loads((B/'manifest.json').read_text());v=json.loads((B/args.condition/'validation.json').read_text());assert v['manifest_sha256']==digest(B/'manifest.json')
c=m['conditions'][args.condition];binding=Path(habitat_sim._ext.habitat_sim_bindings.__file__);assert digest(binding)==c['binding_sha256'];assert digest(R/'tests/landmark_diagnostics/source_collision_filter.py')==m['filter_sha256']
assert digest(c['profile_path'])==c['profile_sha256'];profile=json.loads(Path(c['profile_path']).read_text());asset=profile['assets'][m['scene_id']];assert digest(asset['navmesh_path'])==asset['navmesh_sha256']
gp=Path(m['native_geometry_path']);assert digest(gp)==m['native_geometry_sha256'];raw=gp.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);vertices=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);indices=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=vertices[indices].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);cache={}
def direct_sweep(a,b):
    key=(tuple(float(x) for x in a),tuple(float(x) for x in b))
    if key in cache:return cache[key]
    a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float);lower=np.minimum(a,b);upper=np.maximum(a,b)
    ids=np.flatnonzero((lo[:,0]<upper[0]+.1)&(hi[:,0]>lower[0]-.1)&(lo[:,2]<upper[2]+.1)&(hi[:,2]>lower[2]-.1)&(lo[:,1]<upper[1]+1.5)&(hi[:,1]>lower[1]+1e-5))
    hit=None
    for j in ids:
        distance=triangle_linear_sweep_distance(tri[j],a,b)
        if distance<.1-1e-6:hit={'triangle':int(j),'distance':float(distance)};break
    cache[key]=hit;return hit
cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;agent.sensor_specifications=[];agent.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))}
sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));assert sim.pathfinder.load_nav_mesh(asset['navmesh_path']);controls=sim.get_agent(0).controls;native_filter=controls.move_filter_fn;guard=SourceCollisionFilter(native_filter,sim.pathfinder.is_navigable,direct_sweep);controls.move_filter_fn=guard
arithmetic=json.loads((B/'filter-return-arithmetic-diagnosis.json').read_text());assert digest(R/arithmetic['object_controls_path'])==arithmetic['object_controls_sha256']
O=B/(args.condition+'-independent-v2');O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':args.cpu})
rows=[];reasons=collections.Counter();actions=0;events_count=0
try:
    original={r['task_key']:r for r in m['records']};assert len(v['records'])==len(original)==132
    for record in v['records']:
        p=Path(record['result_path']);assert digest(p)==record['result_sha256'];d=json.load(gzip.open(p,'rt'));key=d['task_key'];assert d['manifest_sha256']==digest(B/'manifest.json') and d['source_trace_sha256']==original[key]['trace_sha256']
        if d['status']=='INITIAL_SOURCE_BLOCKED_PRESERVED':
            assert len(d['positions'])==1 and not d['actions'] and direct_sweep(d['positions'][0],d['positions'][0]) is not None
            rows.append({'task_key':key,'status':d['status'],'replayed':False,'source_result_sha256':digest(p)});continue
        assert d['status']=='STRICT_SOURCE_CLEAR_OPENLOOP_ONLY' and len(d['positions'])==len(d['actions'])+1
        state=habitat_sim.AgentState();state.position=d['positions'][0];state.rotation=quat_from_coeffs(d['rotation']);sim.initialize_agent(0,state);guard.events.clear();maximum=0.;saved_events=collections.defaultdict(list)
        for event in d['filter_events']:saved_events[event['action_index']].append(event)
        assert direct_sweep(d['positions'][0],d['positions'][0]) is None
        for i,action in enumerate(d['actions'],1):
            before=sim.get_agent(0).get_state().position.tolist();event_start=len(guard.events)
            if action:sim.step(action)
            after=sim.get_agent(0).get_state().position.tolist();maximum=max(maximum,math.dist(after,d['positions'][i]));assert sim.pathfinder.is_navigable(after) and abs(after[1]-before[1])<=.5
            assert direct_sweep(after,after) is None and direct_sweep(before,after) is None
            produced=guard.events[event_start:];assert len(produced)==len(saved_events[i])
            if not produced:assert after==before
            for event,saved in zip(produced,saved_events[i]):
                assert event['before']==saved['before']==before and event['requested']==saved['requested'] and event['native_candidate']==saved['native_candidate'] and event['rejected_reason']==saved['rejected_reason']
                returned=np.asarray(before if event['rejected_reason'] else event['native_candidate'],dtype=np.float32);requested=np.asarray(event['requested'],dtype=np.float32)
                expected_actual=(requested+(returned-requested)).astype(np.float32).astype(float).tolist()
                assert after==expected_actual
                events_count+=1;reasons[event['rejected_reason'] or 'accepted_native_endpoint']+=1
                if event['rejected_reason']=='exact_source_swept_contact':assert direct_sweep(before,event['native_candidate']) is not None
            actions+=1
        assert maximum<=1e-5
        rows.append({'task_key':key,'status':'PASS_INDEPENDENT_EXPERIMENTAL_RESPONSE_REPLAY','actions':len(d['actions']),'replay_error':maximum,'source_result_sha256':digest(p),'replayed':True})
    assert {r['task_key'] for r in rows}==set(original)
    atomic_json(O/'validation.json',{'status':'COMPLETE_INDEPENDENT_RESPONSE_AUDIT_NOT_PROTOCOL_ACCEPTANCE','scope':132,'executed':sum(r['replayed'] for r in rows),'initial_blocked':sum(not r['replayed'] for r in rows),'actual_actions_replayed':actions,'filter_events_checked':events_count,'event_reasons':dict(reasons),'rows':rows,'condition_manifest_sha256':digest(B/'manifest.json'),'source_validation_sha256':digest(B/args.condition/'validation.json'),'source_geometry_sha256':digest(gp),'binding_sha256':digest(binding),'native_arithmetic_receipt_sha256':digest(B/'filter-return-arithmetic-diagnosis.json'),'script_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat(),'limits':'Fresh process and native Agent replay. Independent direct triangle AABB traversal shares the tested exact swept-distance primitive; not an independently implemented geometry theorem. Checks safety and each filter decision, not goalreachability, model quality, or authorization/adoption of altered collisionresponse.'})
    print(args.condition,dict(reasons),'actions',actions)
finally:sim.close()

