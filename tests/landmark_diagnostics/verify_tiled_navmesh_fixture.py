"""Load original-archive fixtures into frozen Habitat and execute actual Agent controls twice."""
import os,sys,json,math,struct,datetime,inspect
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OMP_NUM_THREADS"]="1";os.environ["OPENBLAS_NUM_THREADS"]="1"
R=Path.cwd();sys.path[:0]=[str(R/"scripts"),str(R/"tests/landmark_diagnostics")]
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
import numpy as np,quaternion,habitat_sim
O=R/"outputs/landmark-connectivity/tiled-navmesh-fixture-v3";assert not (O/"habitat-validation.json").exists();native=json.loads((O/"native-validation.json").read_text());assert len(native["cases"])==6
binding=Path(habitat_sim._ext.habitat_sim_bindings.__file__)
# Compare against the actual frozen binding identity recorded by the isolated-control receipt.
reference=json.loads((R/"outputs/landmark-connectivity/recast626-isolated-binding-v1/validation.json").read_text());assert digest(binding)==reference["control_binding_sha256"]
def execute(pf,start,reverse):
 graph=habitat_sim.SceneGraph();config=habitat_sim.AgentConfiguration();config.height=1.5;config.radius=.1;config.sensor_specifications=[];config.action_space={"move_forward":habitat_sim.ActionSpec("move_forward",habitat_sim.ActuationSpec(amount=.25))};controls=habitat_sim.agent.controls.ObjectControls(move_filter_fn=pf.try_step);agent=habitat_sim.Agent(graph.get_root_node().create_child(),config,controls=controls);state=habitat_sim.AgentState();state.position=start;state.rotation=quaternion.from_rotation_vector([0,math.pi/2 if reverse else -math.pi/2,0]);agent.set_state(state);positions=[list(agent.get_state().position)];collisions=[]
 for i in range(6):collisions.append(bool(agent.act("move_forward")));positions.append(list(agent.get_state().position))
 return np.array(positions,dtype=float),collisions
rows=[]
try:
 for case in native["cases"]:
  name=case["case"];pf=habitat_sim.PathFinder();mesh=O/(name+".navmesh");assert pf.load_nav_mesh(str(mesh));raw=(O/(name+".geometry.bin")).read_bytes();nv,nt=struct.unpack("<ii",raw[:8]);v=np.frombuffer(raw,dtype="<f4",offset=8,count=nv*3).reshape(nv,3);idx=np.frombuffer(raw,dtype="<i4",offset=8+nv*12,count=nt*3).reshape(nt,3);tri=v[idx].astype(float);directions=[]
  for reverse in [False,True]:
   start=np.asarray(pf.snap_point([1.75 if reverse else .25,0,.5]),dtype=float);end=np.asarray(pf.snap_point([.25 if reverse else 1.75,0,.5]),dtype=float);assert np.isfinite(start).all() and np.isfinite(end).all() and pf.is_navigable(start) and pf.is_navigable(end);q=habitat_sim.ShortestPath();q.requested_start=start;q.requested_end=end;found=bool(pf.find_path(q));assert found==case["expected_connected"]
   if found:assert math.isfinite(q.geodesic_distance) and abs(q.geodesic_distance-1.5)<1e-5
   else:assert not math.isfinite(q.geodesic_distance)
   poses,collisions=execute(pf,start,reverse);replay,replay_collisions=execute(pf,start,reverse);assert np.isfinite(poses).all();error=float(np.max(np.linalg.norm(poses-replay,axis=1)));assert error<=1e-6 and collisions==replay_collisions;reached=float(np.linalg.norm(poses[-1]-end))<=1e-5;assert reached==case["expected_connected"]
   assert all(pf.is_navigable(p) and np.linalg.norm(p-np.array(pf.snap_point(p)))<1e-5 for p in poses)
   hits=[]
   for i,(a,b) in enumerate(zip(poses,poses[1:])):
    assert np.linalg.norm((b-a)[[0,2]])<=.25001 and abs(b[1]-a[1])<=.3
    for j,t in enumerate(tri):
     if triangle_linear_sweep_distance(t,a,b)<.1-1e-6:hits.append([i,j])
   assert not hits,(name,reverse,hits)
   if found:assert not any(collisions)
   else:assert any(collisions)
   directions.append({"reverse":reverse,"path_found":found,"geodesic_distance":float(q.geodesic_distance) if found else None,"reached":reached,"primitive_actions":6,"positions":poses.tolist(),"collision_flags":collisions,"independent_agent_replay_error":error,"source_contact_segments":len(hits)})
  atomic_json(O/(name+"-habitat.json"),{"case":name,"directions":directions,"mesh_sha256":digest(mesh),"geometry_sha256":digest(O/(name+".geometry.bin"))});rows.append({"case":name,"expected_connected":case["expected_connected"],"directions_checked":2,"actions_per_agent_execution":6,"agent_executions":4,"report_sha256":digest(O/(name+"-habitat.json"))})
 atomic_json(O/"habitat-validation.json",{"status":"PASS_ORIGINAL_HABITAT_MIXED_TILE_LOAD_AGENT_ACTIONS_SOURCE_AND_REPLAY_FIXTURES","cases":rows,"case_count":6,"independent_agent_executions":24,"primitive_action_executions":144,"binding_sha256":digest(binding),"agent_source_sha256":digest(inspect.getfile(habitat_sim.Agent)),"checker_sha256":digest(__file__),"native_validation_sha256":digest(O/"native-validation.json"),"limits":"Syntheticflatfloor/thinwall/gap only. OriginalHabitat Agent.act+PathFinder.try_step, noRenderer/model/MP3D run. Same/mixedresolution seamlessfloor succeeds bothdirections; wall/gap block bothdirections. Does not establish production mixedprofile compatibility or acceptance.","time":datetime.datetime.now().isoformat()});atomic_json(O/"state.json",{"status":"COMPLETE_FIXTURE_COMPATIBILITY_ONLY"});print("PASS6FIXTURES144ACTIONS")
except Exception as e:atomic_json(O/"habitat-failure.json",{"status":"FAILED","error":repr(e)});raise
