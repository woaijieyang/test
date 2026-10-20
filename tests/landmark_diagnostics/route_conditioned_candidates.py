"""Published local waypoint sampling with whole-route component consistency."""
import os,sys,json,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[9:10]);os.nice(10)
import habitat_sim
run=ROOT/'outputs/landmark-connectivity/full-native-v3';m=json.loads((run/'manifest.json').read_text());profile=json.loads(Path(m['profile_path']).read_text());native={(r['scene'],r['node']):r['native_candidates'][0] for r in json.loads(Path('outputs/landmark-connectivity/native-mapping.json').read_text())['nodes']};identity={(r['scene'],r['node']):r for r in json.loads(Path('outputs/landmark-connectivity/published-identity-nodes.json').read_text())['nodes']};finders={};buckets=collections.defaultdict(list);cache={};offsets=[(0,0)]+[(r*math.cos(i*2*math.pi/n),r*math.sin(i*2*math.pi/n)) for r,n in ((.1,18),(.15,30),(.2,36),(.25,48),(.3,60),(.35,72)) for i in range(n)];records=[];counts=collections.Counter()
def finder(sc):
 if sc not in finders:
  pf=habitat_sim.PathFinder();asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];assert pf.load_nav_mesh(asset['navmesh_path']);finders[sc]=pf
 return finders[sc]
def connected(pf,a,b):
 q=habitat_sim.ShortestPath();q.requested_start=a;q.requested_end=b;return bool(pf.find_path(q)) and math.isfinite(q.geodesic_distance)
def component(sc,p):
 pf=finder(sc);key=(sc,round(float(pf.island_radius(p)),6));reps=buckets[key]
 for i,q in enumerate(reps):
  if connected(pf,p,q):return (key[1],i)
 reps.append(p);return (key[1],len(reps)-1)
def candidates(sc,node,method,current):
 if method=='official_GT_monotone_alignment':anchor=native[(sc,node)];origin='official_reference'
 elif identity[(sc,node)]['method']!='UNRESOLVED_no_direct_identity':anchor=identity[(sc,node)]['position'];origin=identity[(sc,node)]['method']
 elif current is not None:anchor=current;origin='prior_bounded_projection'
 else:return {}
 ck=(sc,node,origin,tuple(anchor))
 if ck in cache:return cache[ck]
 pf=finder(sc);choices={}
 for dx,dz in offsets:
  q=list(pf.snap_point([anchor[0]+dx,anchor[1],anchor[2]+dz]))
  if not all(math.isfinite(v) for v in q) or not pf.is_navigable(q):continue
  horizontal=math.hypot(q[0]-anchor[0],q[2]-anchor[2]);total=math.dist(q,anchor)
  if horizontal>.350001 or total>.5:continue
  if origin=='prior_bounded_projection':
   camera=identity[(sc,node)]['camera_position']
   if math.hypot(q[0]-camera[0],q[2]-camera[2])>=.5 or not 0<=camera[1]-q[1]<=2:continue
  label=component(sc,q);item={'position':q,'anchor':anchor,'anchor_kind':origin,'horizontal_displacement':horizontal,'euclidean_displacement':total,'cost':total*total}
  if label not in choices or item['cost']<choices[label]['cost']:choices[label]=item
 cache[ck]=choices;return choices
for task in m['tasks']:
 if task['status']!='STATIC_BLOCKED_PRESERVED':continue
 sc=task['scene'];choices=[candidates(sc,n,method,p) for n,method,p in zip(task['original_viewpoint_path'],task['mapping_methods'],task['targets'])];common=set(choices[0]) if choices else set()
 for c in choices[1:]:common.intersection_update(c)
 result={'task_key':task['task_key'],'scene':sc,'candidate_component_counts':[len(c) for c in choices],'original_errors':task['static_errors']}
 if common:
  label=min(common,key=lambda c:sum(x[c]['cost'] for x in choices));selected=[x[label] for x in choices];points=[x['position'] for x in selected];assert all(connected(finder(sc),a,b) for a,b in zip(points,points[1:]));result.update(status='STATIC_CANDIDATE_PENDING_MOTION',targets=points,selected_candidates=selected);counts['static_candidate_pass']+=1
 else:result['status']='UNRESOLVED_NO_COMMON_VALID_COMPONENT';counts['unresolved']+=1
 records.append(result)
 if len(records)%200==0:print(len(records),dict(counts),flush=True)
assert len(records)==3471
atomic_json(ROOT/'outputs/landmark-connectivity/route-conditioned-candidates.json',{'status':'DIAGNOSTIC_NOT_ACCEPTED','counts':dict(counts),'records':records,'parent_manifest_sha256':digest(run/'manifest.json'),'script_sha256':digest(__file__),'bounds':{'sampling_radius':.35,'euclidean_displacement':.5,'body_height':1.5,'body_radius':.1},'limits':'Original node IDs, order, instructions and source geometry remain unchanged. Candidate positions must be native-navigable and share one reachable component across the full route; actual motion and independent replay still mandatory.'})
print(dict(counts))
