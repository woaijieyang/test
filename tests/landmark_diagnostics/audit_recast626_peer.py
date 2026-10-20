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
b=ROOT/'outputs/landmark-connectivity';out=b/'recast626-peer-independent-audit-v1';out.mkdir(exist_ok=False)
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

r=b/'recast626-source-guard-peer-v1';v=json.loads((r/'validation.json').read_text());gm=json.loads((r/'manifest.json').read_text());assert digest(r/'manifest.json')==v['manifest_sha256'];rows=[]
for row in v['results']:
 if row['status']!='PASS_DIAGNOSTIC':continue
 p=Path(row['result_path']);assert digest(p)==row['sha256'];d=json.loads(p.read_text());t=tasks[d['task_key']];assert d['guard_manifest_sha256']==digest(r/'manifest.json');assert d['script_sha256']==gm['worker_sha256'];assert d['targets']==t['targets'] and d['source_record_sha256']==t['source_record_sha256'];assert d['mesh_sha256']==digest(asset['navmesh_path']) and d['scene_sha256']==digest(gp)
 assert len(d['positions'])==len(d['actions'])+1 and all(x in (1,2,3) for x in d['actions']) and len(d['actions'])<=10000
 assert safe(d['positions'][0]);reset(replay,t['targets'][0],quat_from_coeffs(d['rotation']));err=math.dist(replay.get_agent(0).get_state().position,d['positions'][0]);bad=[]
 for i,act in enumerate(d['actions']):
  replay.step(act);actual=replay.get_agent(0).get_state().position.tolist();err=max(err,math.dist(actual,d['positions'][i+1]));assert all(math.isfinite(x) for x in actual) and replay.pathfinder.is_navigable(actual);assert abs(actual[1]-d['positions'][i][1])<=.5
  bad.extend(sweep(d['positions'][i],actual))
 assert not bad and err<=1e-5
 assert [x['reference_index'] for x in d['boundaries']]==list(range(1,len(t['targets'])))
 prev=0
 for x in d['boundaries']:
  assert prev<=x['action_index']<=len(d['actions']) and x['action_index']-prev<=1500;prev=x['action_index'];distance_to_target=dist(d['positions'][x['action_index']],t['targets'][x['reference_index']]);assert distance_to_target is not None and distance_to_target<=.25
 rows.append({'task_key':d['task_key'],'status':'PASS_INDEPENDENT_REPLAY_AND_GEOMETRY','actual_actions':len(d['actions']),'max_replay_error':err,'source_contacts':len(bad),'result_path':str(p),'sha256':digest(p)})
assert len(rows)==1
for sim in sims:sim.close()
atomic_json(out/'validation.json',{'status':'PASS_ONE_ADDITIONAL_DIAGNOSTIC_PROOF','script_sha256':digest(__file__),'profile_sha256':digest(m['profile_path']),'manifest_sha256':digest(r/'manifest.json'),'rows':rows,'limits':'One feasibility proof only, not overall acceptance or model performance.'})
print(rows)
