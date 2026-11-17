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
B=ROOT/'outputs/landmark-connectivity';O=B/'step-envelope-hypothesis-v1';O.mkdir(exist_ok=False)
m=json.loads((B/'full-native-v11/manifest.json').read_text());profile=json.loads(Path(m['profile_path']).read_text());sc='mJXqzFtmKg4';asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];gp=ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb';mesh=trimesh.load(str(gp),force='scene',process=False).to_geometry();mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float));tri=np.asarray(mesh.triangles);lo=tri.min(axis=1);hi=tri.max(axis=1)
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
parent=B/'native-prefix-curve-diagnostic-v1/validation.json';records=[]
for r in json.loads(parent.read_text())['records']:
 a=r['start'];b=r['end'];climb=profile['assets'][f'mp3d/{sc}/{sc}.glb']['build_settings']['agent_max_climb'];assert abs(b[1]-a[1])<=climb and math.hypot(b[0]-a[0],b[2]-a[2])<=.25+1e-5
 corner=[b[0],a[1],b[2]] if b[1]<a[1] else [a[0],b[1],a[2]]
 linear=sweep(a,b);first=sweep(a,corner);second=sweep(corner,b)
 row={'task_key':r['task_key'],'action_index':r['action_index'],'start':a,'end':b,'hypothetical_corner':corner,'profile_climb_limit':climb,'absolute_vertical_change':abs(b[1]-a[1]),'horizontal_displacement':math.hypot(b[0]-a[0],b[2]-a[2]),'linear_swept_contacts':linear,'hypothetical_step_swept_contacts':[first,second],'native_endpoint_error_from_prior_replay':r['prefix_endpoint_error']};atomic_json(O/(r['task_key'].replace(':','-')+'.json'),row);records.append({'task_key':r['task_key'],'linear_contacts':len(linear),'step_contacts':len(first)+len(second)})
actual.close();prefix.close()
atomic_json(O/'validation.json',{'status':'ALTERNATIVE_KINEMATIC_CURVE_HYPOTHESIS_NOT_ACCEPTANCE','records':records,'native_prefix_receipt_sha256':digest(parent),'scene_sha256':digest(gp),'profile_sha256':digest(m['profile_path']),'sweep_reference_sha256':digest(ROOT/'tests/landmark_diagnostics/swept_cylinder_reference.py'),'script_sha256':digest(__file__),'reference_work':'https://github.com/bulletphysics/bullet3/blob/master/src/BulletDynamics/Character/btKinematicCharacterController.cpp','limits':'Bullet-style up/forward/down decomposition motivates only this hypothesis; Habitat is not Bullet KCC. These continuous geometric curves are not recorded native sub-trajectories and have not replaced any acceptance gate. No motion, body dimension, dataset or profile was changed.'});print(records)
