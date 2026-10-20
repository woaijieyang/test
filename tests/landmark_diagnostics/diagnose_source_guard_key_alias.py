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
b=ROOT/'outputs/landmark-connectivity';out=b/'source-guard-key-alias-v1';out.mkdir(exist_ok=False)
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

from robust_oracle import RobustOracle
import heapq,itertools
class AliasOracle(RobustOracle):
 def transition(self,state,action):
  new=super().transition(state,action)
  if new is None:return None
  if sweep(state[0],new[0]):return None
  return new
 def search(self,start):
  counter=itertools.count();queue=[(self.distance(start[0])/.25,0.,next(counter),start,[])];best={self.key(start):0.};representative={self.key(start):start};expanded=0;self.alias_count=0;self.divergent=[];self.max_alias_position_delta=0.
  while queue and expanded<self.max_nodes:
   _,cost,_,state,path=heapq.heappop(queue);key=self.key(state)
   if cost>best.get(key,math.inf)+1e-9:continue
   if self.distance(state[0])<=self.radius:self.expanded=expanded;return path
   expanded+=1
   for action in (1,2,3):
    new=self.transition(state,action)
    if new is None:continue
    k=self.key(new);g=cost+(1. if action==1 else .15)
    if g>=best.get(k,math.inf)-1e-9:
     prior=representative[k];delta=math.dist(prior[0],new[0]);self.max_alias_position_delta=max(self.max_alias_position_delta,delta)
     if delta>1e-6:
      self.alias_count+=1;pa=self.transition(prior,1);pb=self.transition(new,1)
      if (pa is None)!=(pb is None) and len(self.divergent)<30:self.divergent.append({'key':list(k),'retained_position':prior[0].tolist(),'pruned_position':new[0].tolist(),'retained_rotation':[float(prior[1].real),*map(float,prior[1].imag)],'pruned_rotation':[float(new[1].real),*map(float,new[1].imag)],'position_difference':delta,'retained_forward_legal':pa is not None,'pruned_forward_legal':pb is not None,'retained_cost':best[k],'pruned_cost':g})
     continue
    best[k]=g;representative[k]=new;heapq.heappush(queue,(g+self.distance(new[0])/.25,g,next(counter),new,path+[action]))
  self.expanded=expanded;raise RuntimeError('legal_action_search_exhausted:'+str(expanded))
reports=[]
for key in ['train:39659','train:36008','train:36009']:
 p=next(p for p in (b/'recast626-source-guard-scene-v1/episodes').glob('*.json') if json.loads(p.read_text())['task_key']==key);d=json.loads(p.read_text());reset(sim,d['positions'][0],quat_from_coeffs(d['rotation']))
 for a in d['actions']:sim.step(a)
 assert math.dist(sim.get_agent(0).get_state().position,d['positions'][-1])<=1e-5
 target=d['targets'][len(d['boundaries'])+1];oracle=AliasOracle(sim,replay,target,radius=.25,max_nodes=5000);error=None;plan=None
 try:plan=oracle.search(oracle.snapshot(sim))
 except RuntimeError as e:error=str(e)
 row={'task_key':key,'prefix_path':str(p),'prefix_sha256':digest(p),'expanded':oracle.expanded,'search_error':error,'search_plan_length':len(plan) if plan is not None else None,'pruned_nonidentical_states':oracle.alias_count,'max_alias_position_delta':oracle.max_alias_position_delta,'divergent_forward_legality':oracle.divergent};atomic_json(out/(key.replace(':','-')+'.json'),row);reports.append(row);print(key,oracle.expanded,oracle.alias_count,len(oracle.divergent),flush=True)
for sim in sims:sim.close()
atomic_json(out/'validation.json',{'status':'DIAGNOSIS_ONLY_NOT_ACCEPTANCE','profile_sha256':digest(m['profile_path']),'script_sha256':digest(__file__),'oracle_sha256':digest(ROOT/'tests/landmark_diagnostics/robust_oracle.py'),'helper_sha256':digest(helper),'records':reports,'limits':'Instrumented original1cm position key and5000 limit only. Same-key states with different legal forward outcomes indicate potential false pruning, not a proven complete route. No actual policy/mesh/gate change.'})
