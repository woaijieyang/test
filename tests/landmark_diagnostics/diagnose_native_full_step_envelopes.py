"""Compare endpoint-linear interpolation with prefix queries of the unchanged native movement kernel."""
import os,sys,json,math,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
sys.path[:0]=[str(Path.cwd()/'scripts'),str(Path.cwd()/'tests/landmark_diagnostics'),str(Path.cwd()/'.cache/geometry-tools')]
from workspace import ROOT,atomic_json,digest
from projected_distance_reference import projected_distance
import numpy as np,trimesh,habitat_sim,psutil
from habitat_sim.utils.common import quat_from_coeffs,quat_rotate_vector
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])])
B=ROOT/'outputs/landmark-connectivity';O=B/'step-envelope-native-full-trace-v1';O.mkdir(exist_ok=False)
m=json.loads((B/'full-native-v11/manifest.json').read_text());profile=json.loads(Path(m['profile_path']).read_text());sc='mJXqzFtmKg4';asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];gp=ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb';native_receipt=B/'step-envelope-native-geometry-v1/validation.json';nr=json.loads(native_receipt.read_text());native_path=Path(nr['native_geometry_path']);assert digest(native_path)==nr['native_geometry_sha256'] and digest(gp)==nr['scene_sha256'];raw=native_path.read_bytes();nv,nt=np.frombuffer(raw[:8],dtype=np.int32);assert len(raw)==8+int(nv)*12+int(nt)*12;vertices=np.frombuffer(raw,dtype=np.float32,count=int(nv)*3,offset=8).reshape(-1,3).astype(float);indices=np.frombuffer(raw,dtype=np.int32,count=int(nt)*3,offset=8+int(nv)*12).reshape(-1,3);tri=vertices[indices];lo=tri.min(axis=1);hi=tri.max(axis=1)
helper=ROOT/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';s=helper.read_text();exec(s[s.index('def clip('):s.index('records=[]')])
def contacts(p):
 p=np.asarray(p);ids=np.flatnonzero((lo[:,0]<p[0]+.1)&(hi[:,0]>p[0]-.1)&(lo[:,2]<p[2]+.1)&(hi[:,2]>p[2]-.1)&(lo[:,1]<p[1]+1.5)&(hi[:,1]>p[1]+1e-5));out=[]
 for j in ids:
  poly=clip(list(tri[j]),p[1]+1e-5,True)
  if len(poly)<3:continue
  poly=clip(poly,p[1]+1.5,False)
  if len(poly)<3:continue
  dist=projected_distance(poly,p)
  if dist<.1-1e-6:out.append({'triangle':int(j),'distance':dist,'max_height':float(max(v[1] for v in poly)-p[1])})
 return out
def make():
 cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;a=habitat_sim.agent.AgentConfiguration();a.height=1.5;a.radius=.1;a.sensor_specifications=[];a.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))};sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[a]));assert sim.pathfinder.load_nav_mesh(asset['navmesh_path']);return sim
actual,prefix=make(),make();assert actual.get_agent(0).agent_config.action_space[1].actuation is not prefix.get_agent(0).agent_config.action_space[1].actuation
def reset(sim,p,q):
 st=habitat_sim.AgentState();st.position=p;st.rotation=q;sim.initialize_agent(0,st)

from swept_cylinder_reference import triangle_linear_sweep_distance
def sweep(a,b):
 a=np.array(a);b=np.array(b);low=np.minimum(a,b);high=np.maximum(a,b);ids=np.flatnonzero((lo[:,0]<high[0]+.1)&(hi[:,0]>low[0]-.1)&(lo[:,2]<high[2]+.1)&(hi[:,2]>low[2]-.1)&(lo[:,1]<high[1]+1.5)&(hi[:,1]>low[1]+1e-5));hits=[]
 for j in ids:
  d=triangle_linear_sweep_distance(tri[j],a,b)
  if d<.1-1e-6:hits.append({'triangle':int(j),'radial_distance':d,'vertices':tri[j].tolist()})
 return hits

reports=[]
for key in ['train:14625','train:14626']:
 input_path=B/'recast626-unresolved-paired-v1'/(key.replace(':','-')+'.json');row=json.loads(input_path.read_text());plan=row['old_plan_new_mesh'];t=next(t for t in m['tasks'] if t['task_key']==key);reset(actual,t['targets'][0],quat_from_coeffs(plan['rotation']));certificates=[];issues=[];replay_error=0.;positions=[actual.get_agent(0).get_state().position.tolist()];climb=asset.get('build_settings',{}).get('agent_max_climb');assert climb is not None
 for i,action in enumerate(plan['actions'],1):
  a=positions[-1];actual.step(action);b=actual.get_agent(0).get_state().position.tolist();positions.append(b);replay_error=max(replay_error,math.dist(b,plan['positions'][i]));assert actual.pathfinder.is_navigable(b) and abs(b[1]-a[1])<=.5
  linear=sweep(a,b);kind='linear';corner=None;step_hits=None
  if linear:
   if action==1 and 1e-5<abs(b[1]-a[1])<=climb and math.hypot(b[0]-a[0],b[2]-a[2])<=.25+1e-5:
    corner=[b[0],a[1],b[2]] if b[1]<a[1] else [a[0],b[1],a[2]];step_hits=[sweep(a,corner),sweep(corner,b)];kind='hypothetical_native_bounded_step' if not any(step_hits) else 'uncertified'
   else:kind='uncertified'
  if kind=='uncertified':issues.append({'action_index':i,'linear_hits':linear,'step_hits':step_hits})
  certificates.append({'action_index':i,'action':action,'start':a,'end':b,'kind':kind,'corner':corner,'linear_contact_count':len(linear)})
 for bound in plan['boundaries']:
  q=habitat_sim.ShortestPath();q.requested_start=positions[bound['action_index']];q.requested_end=t['targets'][bound['reference_index']];assert actual.pathfinder.find_path(q) and q.geodesic_distance<=.25
 assert replay_error<=1e-5 and len(plan['boundaries'])==len(t['targets'])-1 and len(plan['actions'])<=10000
 result={'status':'COMPLETE_GEOMETRIC_REALIZATION_HYPOTHESIS' if not issues else 'INCOMPLETE_GEOMETRIC_REALIZATION','task_key':key,'actual_primitive_actions':len(plan['actions']),'reference_points_checked':len(plan['boundaries']),'native_replay_error':replay_error,'hypothetical_step_segments':sum(c['kind']=='hypothetical_native_bounded_step' for c in certificates),'issues':issues,'certificates':certificates,'input_sha256':digest(input_path),'original_source_record_sha256':t['source_record_sha256'],'native_actions_changed':False,'native_endpoints_changed':False,'native_internal_curve_observed':False};atomic_json(O/(key.replace(':','-')+'.json'),result);reports.append({k:v for k,v in result.items() if k not in ['certificates','issues']});print(reports[-1],flush=True)
actual.close();prefix.close()
atomic_json(O/'validation.json',{'status':'DIAGNOSTIC_PROTOCOL_INTERPRETATION_REQUIRED','records':reports,'profile_sha256':digest(m['profile_path']),'scene_sha256':digest(gp),'native_geometry_receipt_sha256':digest(native_receipt),'native_geometry_sha256':digest(native_path),'sweep_reference_sha256':digest(ROOT/'tests/landmark_diagnostics/swept_cylinder_reference.py'),'script_sha256':digest(__file__),'limits':'Fresh native replay is real; the collision-free interior realization is a separate bounded step-model hypothesis. This has not cleared the original source-sweep gate or changed formal evaluation. No publication or accepted-count increment is authorized by this file.'})
