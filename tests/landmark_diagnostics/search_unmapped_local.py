import os,sys,json,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:1])
import habitat_sim
r=json.loads(Path('outputs/landmark-connectivity/missing96-bounded-projection.json').read_text());profile=json.loads(Path('data/derived/navmeshes/landmark-official-paths-candidate-v2/profile.json').read_text());offsets=[(0,0)]+[(radius*math.cos(i*2*math.pi/n),radius*math.sin(i*2*math.pi/n)) for radius,n in ((.1,18),(.15,30),(.2,36),(.25,48),(.3,60),(.35,72)) for i in range(n)];finders={};records=[]
for row in r['records']:
 if row['bounded_downward_candidates']:continue
 sc=row['scene'];p=row['camera_position']
 if sc not in finders:
  pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(profile['assets'][f'mp3d/{sc}/{sc}.glb']['navmesh_path']);finders[sc]=pf
 pf=finders[sc];candidates={}
 for dx,dz in offsets:
  for j in range(101):
   q=list(pf.snap_point([p[0]+dx,p[1]-.02*j,p[2]+dz]))
   if not all(math.isfinite(x) for x in q):continue
   horizontal=math.hypot(q[0]-p[0],q[2]-p[2]);drop=p[1]-q[1]
   if horizontal>=.5 or not 0<=drop<=2 or not pf.is_navigable(q):continue
   candidates[tuple(round(v,5) for v in q)]={'position':q,'horizontal_m':horizontal,'camera_drop_m':drop}
 selected=sorted(candidates.values(),key=lambda x:(x['horizontal_m'],-x['camera_drop_m']))[:64];records.append({'scene':sc,'node':row['node'],'camera_position':p,'candidate_count':len(candidates),'closest_candidates':selected});print(sc,row['node'],len(candidates),flush=True)
 atomic_json(ROOT/'outputs/landmark-connectivity/missing38-local-search.partial.json',{'records':records})
atomic_json(ROOT/'outputs/landmark-connectivity/missing38-local-search.json',{'status':'DIAGNOSTIC_NOT_ACCEPTED','rule':'264 published sampling-ring offsets plus center; downward 2m sampled every .02m; original XY displacement remains strictly below .5m. Top64 candidates retained, no semantic equivalence claimed.','records':records,'found_nodes':sum(bool(x['candidate_count']) for x in records),'missing_nodes':sum(not x['candidate_count'] for x in records),'script_sha256':digest(__file__)})
