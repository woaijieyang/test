"""Freeze every source record, including unresolved records, for native motion validation."""
import os,json,sys,math,hashlib,collections,zipfile
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
os.environ['CUDA_VISIBLE_DEVICES']=''
import habitat_sim
pp=ROOT/'data/derived/navmeshes/landmark-published-recovery-v3/profile.json';profile=json.loads(pp.read_text());raw=Path('/data/zy/vln/data/raw_data/landmark-rxr');alignment=json.loads(Path('outputs/landmark-connectivity/official-GT-alignment-v3.json').read_text());aligned={(r['split'],r['instruction_id']):r for r in alignment['records']};known=json.loads(Path('outputs/landmark-connectivity/published-identity-nodes.json').read_text());identities={(r['scene'],r['node']):r for r in known['nodes']};recovery=json.loads(Path('outputs/landmark-connectivity/missing96-profile-v3-projection.json').read_text());recovered={(r['scene'],r['node']):r for r in recovery['records']};finders={};snapcache={};pathcache={};native={(r['scene'],r['node']):r['native_candidates'][0] for r in json.loads(Path('outputs/landmark-connectivity/native-mapping.json').read_text())['nodes']};tasks=[];ledger=[];counts=collections.Counter();sources=[]
def finder(sc):
 if sc not in finders:
  pf=habitat_sim.PathFinder();asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];assert pf.load_nav_mesh(asset['navmesh_path']);finders[sc]=pf
 return finders[sc]
def snap(sc,point):
 key=(sc,tuple(point))
 if key not in snapcache:
  q=list(point) if finder(sc).is_navigable(point) else list(finder(sc).snap_point(point));ok=all(math.isfinite(v) for v in q) and finder(sc).is_navigable(q) and math.hypot(q[0]-point[0],q[2]-point[2])<.5 and abs(q[1]-point[1])<=.5;snapcache[key]=(q,ok)
 return snapcache[key]
def reachable(sc,a,b):
 key=(sc,tuple(a),tuple(b))
 if key not in pathcache:
  q=habitat_sim.ShortestPath();q.requested_start=a;q.requested_end=b;pathcache[key]=bool(finder(sc).find_path(q)) and math.isfinite(q.geodesic_distance)
 return pathcache[key]
for split in ('train','val_seen','val_unseen'):
 rp=raw/f'LandmarkRxR_{split}.json';rows=json.loads(rp.read_text());sources.append({'path':str(rp),'sha256':digest(rp)})
 for row in rows:
  key=str(row['instruction_id']);sc=row['scan'];item={'task_key':split+':'+key,'split':split,'instruction_id':key,'path_id':str(row['path_id']),'scene':sc,'original_viewpoint_path':row['path'],'heading':float(row['heading']),'instruction_sha256':hashlib.sha256(row['instruction'].encode()).hexdigest(),'source_record_sha256':hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest()};a=aligned[(split,key)];points=[];methods=[];errors=[]
  if a['status']=='STATIC_ALIGNMENT_PASS_PENDING_MOTION':
   seeds=a['reference_target_positions'];methods=['official_GT_monotone_alignment']*len(seeds)
  else:
   seeds=[]
   for node in row['path']:
    r=identities[(sc,node)];method=r['method'];point=r['position']
    if method=='UNRESOLVED_no_direct_identity':
     choices=recovered[(sc,node)]['bounded_downward_candidates']
     if choices:point=choices[0]['position'];method='published_method_bounded_downward_candidate'
     else:point=None;errors.append({'kind':'unresolved_viewpoint','node':node})
    seeds.append(point);methods.append(method)
  for i,seed in enumerate(seeds):
   if seed is None:points.append(None);continue
   point,ok=snap(sc,seed)
   if not ok:errors.append({'kind':'unsafe_or_missing_ground_projection','index':i,'node':row['path'][i]});points.append(None)
   else:
    points.append(point)
    if methods[i]=='official_GT_monotone_alignment' and math.dist(point,native[(sc,row['path'][i])])>.5:errors.append({'kind':'reference_alignment_displacement_exceeded','index':i})
  if all(p is not None for p in points):
   for i,(start,end) in enumerate(zip(points,points[1:])):
    if not reachable(sc,start,end):errors.append({'kind':'unreachable_reference_edge','index':i,'nodes':row['path'][i:i+2]})
  segments=[]
  for i,sub in enumerate(row['sub_paths']):
   positions=[j for j in range(len(row['path'])-len(sub)+1) if row['path'][j:j+len(sub)]==sub]
   if len(positions)!=1:errors.append({'kind':'ambiguous_subpath','segment':i})
   else:segments.append({'index':i,'start':positions[0],'end':positions[0]+len(sub)-1,'instruction_sha256':hashlib.sha256(row['sub_instructions'][i].encode()).hexdigest()})
  item.update(targets=points,mapping_methods=methods,segments=segments,static_errors=errors,status='STATIC_BLOCKED_PRESERVED' if errors else 'READY_FOR_NATIVE_MOTION');tasks.append(item);counts[item['status']]+=1
  for error in errors:counts[error['kind']]+=1
  counts['total_records']+=1
assert len(tasks)==33954 and len({t['task_key'] for t in tasks})==33954
out=ROOT/'outputs/landmark-connectivity/full-native-v3';out.mkdir(exist_ok=False)
manifest={'status':'FROZEN_DIAGNOSTIC_NOT_ACCEPTED','profile_path':str(pp),'profile_sha256':digest(pp),'source_records':33954,'subpaths':166663,'body':{'height':1.5,'radius':.1},'actions':{'forward_m':.25,'turn_degrees':15},'motion_gate':{'goal_radius_m':.25,'max_vertical_step_m':.5,'max_actions_per_segment':1500,'max_actions_per_episode':10000,'replay_tolerance_m':1e-5},'counts':dict(counts),'sources':sources,'builder_sha256':digest(__file__),'tasks':tasks}
atomic_json(out/'manifest.json',manifest);print(json.dumps(dict(counts)))
