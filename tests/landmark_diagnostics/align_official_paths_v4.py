"""Diagnostic monotone Landmark alignment to official continuous demonstrations."""
import os,sys,json,gzip,collections,math,hashlib
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2])
import numpy as np,habitat_sim
raw=Path('/data/zy/vln/data/raw_data/landmark-rxr');ce=Path('/data/zy/vln/data/raw_data/eval_annotations/rxr_vlnce_v0');pp=ROOT/'data/derived/navmeshes/landmark-published-recovery-v3/profile.json';profile=json.loads(pp.read_text());finders={};positions_cache={};path_cache={}
def finder(sc):
 if sc not in finders:
  asset=profile['assets'][sc];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path']);finders[sc]=pf
 return finders[sc]
def position(sc,p):
 key=(sc,tuple(p))
 if key not in positions_cache:
  pf=finder(sc);new=list(pf.snap_point(p));ok=all(math.isfinite(x) for x in new) and pf.is_navigable(new) and math.hypot(new[0]-p[0],new[2]-p[2])<=.15 and abs(new[1]-p[1])<=.2;positions_cache[key]=(new,ok)
 return positions_cache[key]
def reachable(sc,a,b):
 key=(sc,tuple(a),tuple(b))
 if key not in path_cache:
  q=habitat_sim.ShortestPath();q.requested_start=a;q.requested_end=b;path_cache[key]=bool(finder(sc).find_path(q)) and math.isfinite(q.geodesic_distance)
 return path_cache[key]
report={'status':'DIAGNOSTIC_NOT_ACCEPTED','profile_sha256':digest(pp),'splits':{},'records':[],'sources':[],'alignment_rule':'Nondecreasing dynamic programming on exact official reference sequence versus official dense GT; first and last indices fixed; <=0.5m 3D reference distance; no source annotations changed.'}
for split in ('train','val_seen','val_unseen'):
 rp=raw/f'LandmarkRxR_{split}.json';ep=ce/split/f'{split}_guide.json.gz';gp=ce/split/f'{split}_guide_gt.json.gz';rows=json.loads(rp.read_text());eps={str(e['instruction']['instruction_id']):e for e in json.load(gzip.open(ep,'rt'))['episodes']};gt=json.load(gzip.open(gp,'rt'));counts=collections.Counter()
 for row in rows:
  key=str(row['instruction_id']);record={'split':split,'instruction_id':key,'scene':row['scan'],'path_id':str(row['path_id'])};counts['total']+=1;e=eps.get(key)
  if e is None:record['status']='NO_OFFICIAL_PATH';counts['no_official_path']+=1;report['records'].append(record);continue
  assert e['scene_id']==f"mp3d/{row['scan']}/{row['scan']}.glb" and str(e['trajectory_id'])==str(row['path_id']) and len(e['reference_path'])==len(row['path'])
  assert row['instruction'].strip().strip('"').strip()==e['instruction']['instruction_text'].strip().strip('"').strip()
  sc=e['scene_id'];ref=np.asarray(e['reference_path']);locations=gt[str(e['episode_id'])]['locations'];converted=[position(sc,p) for p in locations];points=np.array([x[0] for x in converted]);valid=np.array([x[1] for x in converted]);cost=np.linalg.norm(ref[:,None,:]-points[None,:,:],axis=2);cost[:,~valid]=np.inf;cost[cost>.5]=np.inf;cost[0,1:]=np.inf;cost[-1,:-1]=np.inf;dp=cost[0].copy();back=[]
  for i in range(1,len(ref)):
   best=np.inf;idx=0;prev=np.zeros(len(points),dtype=int);values=np.empty(len(points))
   for j,v in enumerate(dp):
    if v<best:best=v;idx=j
    values[j]=best;prev[j]=idx
   dp=cost[i]+values;back.append(prev)
  errors=[];indices=[]
  if not np.isfinite(dp[-1]):errors.append('no_ordered_alignment_within_0point5m')
  else:
   indices=[len(points)-1]
   for prev in reversed(back):indices.append(int(prev[indices[-1]]))
   indices.reverse();target=[points[i].tolist() for i in indices]
   if any(not reachable(sc,a,b) for a,b in zip(target,target[1:])):errors.append('aligned_targets_disconnected')
   if not valid.all():errors.append('official_GT_contains_unresolved_position')
   elif any(not reachable(sc,a,b) for a,b in zip(points.tolist(),points[1:].tolist())):errors.append('official_GT_adjacent_disconnected')
   record.update(reference_target_positions=target,gt_location_indices=indices,max_reference_displacement=max(float(cost[i,j]) for i,j in enumerate(indices)),adjusted_GT_positions=sum(math.dist(a,b)>1e-7 for a,b in zip(locations,points.tolist())))
  record.update(status='STATIC_ALIGNMENT_PASS_PENDING_MOTION' if not errors else 'ALIGNMENT_UNRESOLVED',ce_episode_id=str(e['episode_id']),errors=errors);counts[record['status']]+=1
  for error in errors:counts[error]+=1
  report['records'].append(record)
 report['splits'][split]=dict(counts);print(split,dict(counts),flush=True)
 for p in (rp,ep,gp):report['sources'].append({'path':str(p),'sha256':digest(p)})
 atomic_json(ROOT/'outputs/landmark-connectivity/official-GT-alignment-v4.partial.json',report)
report['auditor_sha256']=digest(__file__);atomic_json(ROOT/'outputs/landmark-connectivity/official-GT-alignment-v4.json',report)
