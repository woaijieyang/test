"""Apply existing bounded ring proposals plus native source-body filter, without adopting targets."""
import os,sys,json,math,struct,collections,argparse,re,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
P=argparse.ArgumentParser();P.add_argument('--scene',required=True);P.add_argument('--run',required=True);P.add_argument('--profile',required=True);args=P.parse_args();assert re.fullmatch('[A-Za-z0-9]{11}',args.scene) and re.fullmatch('[A-Za-z0-9-]+',args.run)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from projected_distance_reference import projected_distance
import numpy as np,habitat_sim,psutil
usage=psutil.cpu_percent(interval=1,percpu=True);available=[i for i in sorted(os.sched_getaffinity(0))[:64] if i not in [22,24,27,30]];os.sched_setaffinity(0,[min(available,key=lambda i:usage[i])])
B=R/'outputs/landmark-connectivity';O=B/args.run;O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
parent=B/'full-native-v11/manifest.json';m=json.loads(parent.read_text());sc=args.scene;tasks=[t for t in m['tasks'] if t['scene']==sc];assert tasks;candidate_profile=Path(args.profile).resolve();assert candidate_profile.is_relative_to(R/'data/derived/navmeshes');profile=json.loads(candidate_profile.read_text());asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path']);native={(r['scene'],r['node']):r['native_candidates'][0] for r in json.loads((B/'native-mapping.json').read_text())['nodes']};identity={(r['scene'],r['node']):r for r in json.loads((B/'published-identity-nodes.json').read_text())['nodes']};geo_path=B/f'full-source-native-{sc}-v1/validation.json';geo=json.loads(geo_path.read_text());assert geo['scene']==sc;gp=Path(geo['native_geometry_path']);assert digest(gp)==geo['native_geometry_sha256'];assert digest(R/f'data/scene_datasets/mp3d/{sc}/{sc}.glb')==geo['scene_sha256'];raw=gp.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);vertices=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=vertices[ix].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1)
def clip(poly,y,above):
 out=[]
 for a,b in zip(poly,poly[1:]+poly[:1]):
  aa=a[1]>=y if above else a[1]<=y;bb=b[1]>=y if above else b[1]<=y
  if aa:out.append(a)
  if aa!=bb:out.append(a+(y-a[1])/(b[1]-a[1])*(b-a))
 return out
regions={};poses={}
def contact(point):
 key=tuple(float(x) for x in point)
 if key in poses:return poses[key]
 q=np.array(point);cell=tuple(math.floor(float(v)/.5) for v in q)
 if cell not in regions:
  a=np.array(cell)*.5;b=a+.5;regions[cell]=np.flatnonzero((lo[:,0]<b[0]+.1)&(hi[:,0]>a[0]-.1)&(lo[:,2]<b[2]+.1)&(hi[:,2]>a[2]-.1)&(lo[:,1]<b[1]+1.5)&(hi[:,1]>a[1]))
 hit=None
 for j in regions[cell]:
  if lo[j,0]>=q[0]+.1 or hi[j,0]<=q[0]-.1 or lo[j,2]>=q[2]+.1 or hi[j,2]<=q[2]-.1 or lo[j,1]>=q[1]+1.5 or hi[j,1]<=q[1]+1e-5:continue
  poly=clip(list(tri[j]),q[1]+1e-5,True)
  if len(poly)<3:continue
  poly=clip(poly,q[1]+1.5,False)
  if len(poly)>=3:
   d=projected_distance(poly,q)
   if d<.1-1e-6:hit={'triangle':int(j),'distance':d,'maximum_height':float(max(p[1] for p in poly)-q[1])};break
 poses[key]=hit;return hit
components=[]
def connected(a,b):
 q=habitat_sim.ShortestPath();q.requested_start=a;q.requested_end=b;return bool(pf.find_path(q)) and math.isfinite(q.geodesic_distance)
def component(q):
 for i,p in enumerate(components):
  if connected(q,p):return i
 components.append(q);return len(components)-1
rings=[(r*math.cos(i*2*math.pi/n),r*math.sin(i*2*math.pi/n)) for r,n in ((.1,18),(.15,30),(.2,36),(.25,48),(.3,60),(.35,72)) for i in range(n)];cache={};ledgers=[]
def options(node,current):
 key=(node,tuple(current));source=identity[(sc,node)]
 if key in cache:return cache[key]
 if (sc,node) in native:anchor=native[(sc,node)];kind='official_reference_node'
 elif source['method']!='UNRESOLVED_no_direct_identity':anchor=source['position'];kind=source['method']
 else:anchor=current;kind='bounded_camera_projection'
 seeds=[(0,current),(2,anchor)]+[(3,[anchor[0]+dx,anchor[1],anchor[2]+dz]) for dx,dz in rings];found={};counts=collections.Counter();seen=set();initial=contact(current)
 for rank,seed in seeds:
  q=list(pf.snap_point(seed));qk=tuple(q)
  if qk in seen:continue
  seen.add(qk)
  if not all(math.isfinite(v) for v in q) or not pf.is_navigable(q) or math.dist(q,list(pf.snap_point(q)))>1e-5:counts['not_actual_mesh_point']+=1;continue
  delta=math.dist(q,anchor)
  if delta>.5 or (rank==3 and math.hypot(q[0]-anchor[0],q[2]-anchor[2])>.350001):counts['source_bound']+=1;continue
  if kind=='bounded_camera_projection':
   camera=source['camera_position']
   if math.hypot(q[0]-camera[0],q[2]-camera[2])>=.5 or not 0<=camera[1]-q[1]<=2:counts['camera_bound']+=1;continue
  hit=contact(q)
  if hit:counts['source_body_contact']+=1;continue
  label=component(q);item={'position':q,'rank':rank,'anchor':anchor,'anchor_kind':kind,'displacement':delta,'camera':source['camera_position']};counts['source_clear']+=1
  if label not in found or (rank,delta)<(found[label]['rank'],found[label]['displacement']):found[label]=item
 result={'node':node,'original_target':current,'original_body_contact':initial,'anchor':anchor,'anchor_kind':kind,'components':found,'candidate_counts':dict(counts)};cache[key]=result;ledgers.append(result);return result
rows=[];proposals=[]
for task in tasks:
 opts=[options(node,p) for node,p in zip(task['original_viewpoint_path'],task['targets'])];common=set.intersection(*(set(o['components']) for o in opts)) if opts else set()
 if common:
  label=min(common,key=lambda c:sum(o['components'][c]['rank']*1000+o['components'][c]['displacement'] for o in opts));chosen=[o['components'][label] for o in opts];points=[c['position'] for c in chosen];assert all(connected(a,b) for a,b in zip(points,points[1:]));changed=any(math.dist(a,b)>1e-5 for a,b in zip(points,task['targets']));row={'task_key':task['task_key'],'status':'SOURCE_CLEAR_TARGETS_COMMON_COMPONENT_PENDING_MOTION','changed':changed,'choices':chosen};proposals.append({**task,'targets':points,'mapping_methods':['source_body_guarded_'+c['anchor_kind'] for c in chosen]})
 else:row={'task_key':task['task_key'],'status':'NO_SOURCE_CLEAR_COMMON_COMPONENT','missing_candidate_indices':[i for i,o in enumerate(opts) if not o['components']]};proposals.append(task)
 rows.append(row)
 if len(rows)%30==0:atomic_json(O/'state.json',{'status':'RUNNING','tasks':len(rows),'expected':len(tasks),'unique_node_occurrences':len(cache),'pose_queries':len(poses)})
status='CANDIDATE_ALL_TASKS_STATIC_SOURCE_CLEAR_PENDING_MOTION' if all(r['status']=='SOURCE_CLEAR_TARGETS_COMMON_COMPONENT_PENDING_MOTION' for r in rows) else 'PARTIAL_CANDIDATE_NOT_ADOPTABLE';atomic_json(O/'candidate_tasks.json',{'tasks':proposals,'limits':'Proposals only; failed tasks retained unchanged, never silently excluded. No running manifest or source annotation modified.'});atomic_json(O/'validation.json',{'status':status,'scene':sc,'expected_tasks':len(tasks),'counts':dict(collections.Counter(r['status'] for r in rows)),'rows':rows,'nodes':ledgers,'parent_manifest_sha256':digest(parent),'parent_profile_sha256':m['profile_sha256'],'profile_path':str(candidate_profile),'profile_sha256':digest(candidate_profile),'native_geometry_receipt_sha256':digest(geo_path),'script_sha256':digest(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Existing ring radii and all original source bounds, body and collision thresholds retained. Point/source/common-component checks are not actual-motion or global adoption. All tasks retained; no new geometry or forced values.'});atomic_json(O/'state.json',{'status':status,'tasks':len(rows),'counts':dict(collections.Counter(r['status'] for r in rows))});print((O/'state.json').read_text())
