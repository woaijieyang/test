"""Diagnose retained failures and replay old plans without changing any acceptance gate."""
import os,sys,math,json,hashlib,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION')
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
os.sched_setaffinity(0,[min(os.sched_getaffinity(0))])
sys.path[:0]=[str(Path.cwd()/'.cache/geometry-tools'),str(Path.cwd()/'scripts'),str(Path.cwd()/'tests/landmark_diagnostics')]
import numpy as np,trimesh,habitat_sim
from habitat_sim.utils.common import quat_from_coeffs
from workspace import ROOT,atomic_json,digest
b=ROOT/'outputs/landmark-connectivity';out=b/'recast626-unresolved-paired-v1';out.mkdir(exist_ok=False)
cov=json.loads((b/'recast626-source-guard-coverage-100k.json').read_text());unresolved=set(cov['unresolved'])
m=json.loads((b/'full-native-v11/manifest.json').read_text());tasks={t['task_key']:t for t in m['tasks'] if t['task_key'] in unresolved};profile=json.loads(Path(m['profile_path']).read_text())
assert digest(m['profile_path'])==cov['profile_sha256']
helper=ROOT/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';text=helper.read_text();exec(text[text.index('def clip('):text.index('records=[]')])
sc='mJXqzFtmKg4';gp=ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb';mesh=trimesh.load(str(gp),force='scene',process=False).to_geometry();mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float));tri=np.asarray(mesh.triangles);lo=tri.min(axis=1);hi=tri.max(axis=1)
worker=ROOT/'tests/landmark_diagnostics/recast626_source_guard_worker.py';w=worker.read_text();regioncache={};posecache={};stats={'checked_poses':0,'rejected_poses':0,'rejected_transitions':0};exec(w[w.index('def safe(p):'):w.index('class BodyOracle')])
def contacts(p):
 p=np.asarray(p);ids=np.flatnonzero((lo[:,0]<p[0]+.1)&(hi[:,0]>p[0]-.1)&(lo[:,2]<p[2]+.1)&(hi[:,2]>p[2]-.1)&(lo[:,1]<p[1]+1.5)&(hi[:,1]>p[1]+1e-5));rows=[]
 for j in ids:
  poly=clip(list(tri[j]),p[1]+1e-5,True)
  if len(poly)<3:continue
  poly=clip(poly,p[1]+1.5,False)
  if len(poly)>=3 and distance(poly,p)<.1-1e-6:
   rows.append({'triangle':int(j),'triangle_vertices':tri[j].tolist(),'normal_y':float(mesh.face_normals[j,1]),'clipped_height_min':float(min(x[1] for x in poly)-p[1]),'clipped_height_max':float(max(x[1] for x in poly)-p[1]),'horizontal_distance':distance(poly,p)})
 return rows
cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;a=habitat_sim.agent.AgentConfiguration();a.height=1.5;a.radius=.1;a.sensor_specifications=[];a.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))}
sims=[habitat_sim.Simulator(habitat_sim.Configuration(cfg,[a])) for _ in range(2)];sim,replay=sims;asset=profile['assets'][f'mp3d/{sc}/{sc}.glb']
for s in sims:assert s.pathfinder.load_nav_mesh(asset['navmesh_path'])
def reset(s,p,q):
 st=habitat_sim.AgentState();st.position=p;st.rotation=q;s.initialize_agent(0,st)
def dist(p,t):
 z=habitat_sim.ShortestPath();z.requested_start=p;z.requested_end=t
 return float(z.geodesic_distance) if sim.pathfinder.find_path(z) else None
def sweep(p,q):
 n=max(1,math.ceil(math.dist(p,q)/.05));bad=[]
 for i in range(1,n+1):
  v=np.asarray(p)+(np.asarray(q)-p)*i/n
  if not safe(v):bad.append({'sample':i,'samples':n,'position':v.tolist(),'endpoint':i==n,'contacts':contacts(v)})
 return bad
base={};old={}
for run,dest in [('recast626-source-guard-scene-v1',base),('recast626-source-guard-old-control-v1',old)]:
 for p in (b/run/'episodes').glob('*.json'):
  d=json.loads(p.read_text())
  if d['task_key'] in unresolved:dest[d['task_key']]=(p,d)
records=[]
for key,t in sorted(tasks.items()):
 p,d=base[key];reset(sim,d['positions'][0],quat_from_coeffs(d['rotation']))
 for act in d['actions']:sim.step(act)
 st=sim.get_agent(0).get_state();assert math.dist(st.position,d['positions'][-1])<=1e-5
 probes=[]
 for turns in range(24):
  reset(sim,st.position,st.rotation)
  for j in range(turns):sim.step(2)
  sim.step(1);q=sim.get_agent(0).get_state().position.tolist();bad=sweep(st.position,q)
  probes.append({'left_turns':turns,'endpoint':q,'movement':math.dist(st.position,q),'endpoint_safe':safe(q),'sweep_rejected':bool(bad),'bad_samples':bad})
 row={'task_key':key,'source_record_sha256':t['source_record_sha256'],'prefix_evidence':str(p),'prefix_sha256':digest(p),'failed_reference_index':len(d['boundaries'])+1,'last_position':st.position.tolist(),'probes':probes}
 op,od=old[key];row['old_control_status']=od['status']
 if od['status']=='PASS_DIAGNOSTIC':
  rotation=quat_from_coeffs(od['rotation']);reset(sim,t['targets'][0],rotation);reset(replay,t['targets'][0],rotation);pos=[sim.get_agent(0).get_state().position.tolist()];badsteps=[];bounds=[];replay_error=0
  oldbounds={x['action_index']:[] for x in od['boundaries']}
  for x in od['boundaries']:oldbounds[x['action_index']].append(x['reference_index'])
  initial_safe=safe(pos[0])
  for k,act in enumerate(od['actions'],1):
   sim.step(act);q=sim.get_agent(0).get_state().position.tolist();bad=sweep(pos[-1],q)
   if bad:badsteps.append({'action_index':k,'samples':bad})
   pos.append(q);replay.step(act);replay_error=max(replay_error,math.dist(q,replay.get_agent(0).get_state().position))
   for ri in oldbounds.get(k,[]):bounds.append({'reference_index':ri,'action_index':k,'distance':dist(q,t['targets'][ri])})
  native=all(sim.pathfinder.is_navigable(x) for x in pos) and all(abs(x[1]-y[1])<=.5 for x,y in zip(pos,pos[1:]))
  passed=initial_safe and not badsteps and native and replay_error<=1e-5 and len(bounds)==len(t['targets'])-1 and all(x['distance'] is not None and x['distance']<=.25 for x in bounds) and len(od['actions'])<=10000 and all(y-x<=1500 for x,y in zip([0]+[x['action_index'] for x in bounds],[x['action_index'] for x in bounds]))
  row['old_plan_new_mesh']={'status':'PASS_DIAGNOSTIC' if passed else 'FAILED_DIAGNOSTIC','old_evidence':str(op),'old_sha256':digest(op),'initial_safe':initial_safe,'native_gates':native,'bad_steps':badsteps,'boundaries':bounds,'actions':od['actions'],'positions':pos,'rotation':od['rotation'],'max_replay_error':replay_error}
 atomic_json(out/(key.replace(':','-')+'.json'),row)
 records.append({'task_key':key,'failed_reference_index':row['failed_reference_index'],'safe_forward_directions':sum(x['movement']>1e-5 and x['endpoint_safe'] and not x['sweep_rejected'] for x in probes),'endpoint_clear_but_interpolation_rejected':sum(x['endpoint_safe'] and x['sweep_rejected'] for x in probes),'old_control_status':od['status'],'old_plan_new_mesh':row.get('old_plan_new_mesh',{}).get('status'),'evidence_sha256':digest(out/(key.replace(':','-')+'.json'))});print(records[-1],flush=True)
for s in sims:s.close()
atomic_json(out/'summary.json',{'status':'DIAGNOSIS_COMPLETE_NOT_ACCEPTED','time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'script_sha256':digest(__file__),'worker_sha256':digest(worker),'helper_sha256':digest(helper),'profile_sha256':digest(m['profile_path']),'mesh_sha256':digest(asset['navmesh_path']),'scene_sha256':digest(gp),'coverage_sha256':digest(b/'recast626-source-guard-coverage-100k.json'),'records':records,'limitations':'Probes reset only a diagnostic simulator; they are not executed episode solutions. Old plans are actually executed and independently replayed, without target changes. Failed plans remain failures. Source interpolation guard unchanged; contact classification does not prove impossibility or justify removing checks.'})
