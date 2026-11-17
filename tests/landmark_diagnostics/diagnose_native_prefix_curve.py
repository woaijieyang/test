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
B=ROOT/'outputs/landmark-connectivity';O=B/'native-prefix-curve-diagnostic-v1';O.mkdir(exist_ok=False)
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
reports=[]
for key in ['train:14625','train:14626']:
 file=next(p for p in (B/'recast626-unresolved-paired-v1').glob('train-*.json') if json.loads(p.read_text())['task_key']==key);d=json.loads(file.read_text());plan=d['old_plan_new_mesh'];assert len(plan['bad_steps'])==1;index=plan['bad_steps'][0]['action_index'];assert plan['actions'][index-1]==1;reset(actual,plan['positions'][0],quat_from_coeffs(plan['rotation']))
 for action in plan['actions'][:index-1]:actual.step(action)
 before=actual.get_agent(0).get_state();assert math.dist(before.position,plan['positions'][index-1])<=1e-5;actual.step(1);end=actual.get_agent(0).get_state().position.copy();assert math.dist(end,plan['positions'][index])<=1e-5;cache={}
 def at(t):
  if t in cache:return cache[t]
  reset(prefix,before.position,before.rotation);prefix.get_agent(0).agent_config.action_space[1].actuation.amount=.25*t
  if t:prefix.step(1)
  p=prefix.get_agent(0).get_state().position.copy();proposal=np.asarray(before.position+quat_rotate_vector(before.rotation,np.array([0,0,-.25*t])),dtype=np.float32);filtered=prefix.pathfinder.try_step(before.position,proposal)
  cache[t]={'position':p.tolist(),'kernel_delta':math.dist(p,filtered),'body_contacts':contacts(p),'linear_position':(before.position+(end-before.position)*t).tolist()};cache[t]['linear_contacts']=contacts(cache[t]['linear_position']);return cache[t]
 for i in range(21):at(i/20)
 for depth in range(10):
  times=sorted(cache);more=[]
  for a,b in zip(times,times[1:]):
   if math.dist(cache[a]['position'],cache[b]['position'])>.025:more.append((a+b)/2)
  if not more:break
  for t in more:at(t)
 times=sorted(cache);endpoint_error=math.dist(cache[1.]['position'],end);kernel_error=max(x['kernel_delta'] for x in cache.values());max_jump=max(math.dist(cache[a]['position'],cache[b]['position']) for a,b in zip(times,times[1:]));assert endpoint_error<=1e-5 and kernel_error<=1e-5
 row={'task_key':key,'action_index':index,'actual_action':1,'actual_amount':.25,'start':before.position.tolist(),'end':end.tolist(),'prefix_endpoint_error':endpoint_error,'prefix_vs_try_step_max_error':kernel_error,'sample_count':len(cache),'max_adjacent_prefix_distance':max_jump,'native_prefix_contact_samples':sum(bool(x['body_contacts']) for x in cache.values()),'linear_contact_samples':sum(bool(x['linear_contacts']) for x in cache.values()),'max_curve_vs_linear_distance':max(math.dist(x['position'],x['linear_position']) for x in cache.values()),'samples':[{'fraction':t,**cache[t]} for t in times],'input_sha256':digest(file)};atomic_json(O/(key.replace(':','-')+'.json'),row);reports.append({k:v for k,v in row.items() if k!='samples'});print(reports[-1],flush=True)
 assert actual.get_agent(0).agent_config.action_space[1].actuation.amount==.25
actual.close();prefix.close()
atomic_json(O/'validation.json',{'status':'PREFIX_KERNEL_DIAGNOSIS_NOT_ACCEPTANCE','profile_sha256':digest(m['profile_path']),'mesh_sha256':digest(asset['navmesh_path']),'scene_sha256':digest(gp),'script_sha256':digest(__file__),'reference_geometry_sha256':digest(ROOT/'tests/landmark_diagnostics/projected_distance_reference.py'),'records':reports,'limits':'Prefix amounts are probes on a separate simulator, not added/executed episode actions or proof of a unique native continuous physical trajectory. Original full action and recorded endpoints are unchanged. No gate automatically replaced by this comparison.'})
