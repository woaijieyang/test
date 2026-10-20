import os,sys,json,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
os.environ['CUDA_VISIBLE_DEVICES']=''
import habitat_sim
source=json.loads(Path('outputs/landmark-connectivity/published-identity-nodes.json').read_text());profile=json.loads(Path('data/derived/navmeshes/landmark-published-recovery-v3/profile.json').read_text());records=[];finders={};counts=collections.Counter()
for row in source['missing_identity_details']:
 scene=row['scene'];key=f'mp3d/{scene}/{scene}.glb'
 if scene not in finders:
  pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(profile['assets'][key]['navmesh_path']);finders[scene]=pf
 pf=finders[scene];p=row['camera_position'];candidates={}
 for i in range(101):
  sample=[p[0],p[1]-.02*i,p[2]];q=list(pf.snap_point(sample))
  if not all(math.isfinite(x) for x in q):continue
  horizontal=math.hypot(q[0]-p[0],q[2]-p[2]);drop=p[1]-q[1]
  if horizontal>=.5 or not 0<=drop<=2 or not pf.is_navigable(q):continue
  candidates[tuple(round(x,5) for x in q)]={'position':q,'horizontal_m':horizontal,'camera_drop_m':drop}
 values=sorted(candidates.values(),key=lambda v:(v['horizontal_m'],-v['camera_drop_m']));counts['nodes']+=1;counts['with_candidate']+=bool(values);counts['no_candidate']+=not values
 records.append({**row,'bounded_downward_candidates':values,'status':'CANDIDATES_PENDING_ROUTE_AND_MOTION' if values else 'UNMAPPABLE_WITH_PUBLISHED_BOUNDS'})
atomic_json(ROOT/'outputs/landmark-connectivity/missing96-profile-v3-projection.json',{'status':'DIAGNOSTIC_NOT_ACCEPTED','rule':{'max_downward_m':2,'horizontal_limit_exclusive_m':.5,'sampling_interval_m':.02,'selection':'minimum horizontal displacement; candidates preserved, no automatic acceptance'},'counts':dict(counts),'records':records,'script_sha256':digest(__file__)});print(json.dumps(dict(counts)))
