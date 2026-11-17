"""Ground route targets before final semantic/connected-component acceptance.
Preserve prior coordinates where still valid, without trusting PASS as evidence.
All proposals obey the same source-anchor bounds and actual mesh membership.
"""
import os,sys,json,math,collections,copy
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[10:11]);os.nice(10)
import habitat_sim
oldpath=ROOT/'outputs/landmark-connectivity/full-native-v4/manifest.json';newpath=ROOT/'outputs/landmark-connectivity/full-native-v4/manifest.json';old=json.loads(oldpath.read_text());new=json.loads(newpath.read_text());new['profile_path']=str(ROOT/'data/derived/navmeshes/landmark-two-scene-coarse-v7/profile.json');new['profile_sha256']=digest(new['profile_path']);prior={t['task_key']:t for t in old['tasks']};profile=json.loads(Path(new['profile_path']).read_text());native={(r['scene'],r['node']):r['native_candidates'][0] for r in json.loads(Path('outputs/landmark-connectivity/native-mapping.json').read_text())['nodes']};identity={(r['scene'],r['node']):r for r in json.loads(Path('outputs/landmark-connectivity/published-identity-nodes.json').read_text())['nodes']};finders={};components=collections.defaultdict(list);cache={};offsets=[(0,0)]+[(r*math.cos(i*2*math.pi/n),r*math.sin(i*2*math.pi/n)) for r,n in ((.1,18),(.15,30),(.2,36),(.25,48),(.3,60),(.35,72)) for i in range(n)];tasks=[];ledger=[];counts=collections.Counter()
def finder(sc):
 if sc not in finders:
  pf=habitat_sim.PathFinder();asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];assert pf.load_nav_mesh(asset['navmesh_path']);finders[sc]=pf
 return finders[sc]
def connected(pf,a,b):
 q=habitat_sim.ShortestPath();q.requested_start=a;q.requested_end=b;return bool(pf.find_path(q)) and math.isfinite(q.geodesic_distance)
def component(sc,p):
 pf=finder(sc);key=(sc,round(float(pf.island_radius(p)),6));reps=components[key]
 for i,q in enumerate(reps):
  if connected(pf,p,q):return (key[1],i)
 reps.append(p);return(key[1],len(reps)-1)
ring_cache={}
def options(sc,node,previous,current,expand=False):
 source=identity[(sc,node)]
 if (sc,node) in native:anchor=native[(sc,node)];kind='official_reference_node'
 elif source['method']!='UNRESOLVED_no_direct_identity':anchor=source['position'];kind=source['method']
 elif current is not None:anchor=current;kind='bounded_camera_projection'
 elif previous is not None:anchor=previous;kind='bounded_camera_projection'
 else:return {},None,'unresolved'
 ck=(sc,node,tuple(anchor),tuple(previous) if previous is not None else None,tuple(current) if current is not None else None)
 pf=finder(sc)
 def collect(seeds):
  found={}
  for rank,seed in seeds:
   q=list(pf.snap_point(seed))
   if not all(math.isfinite(x) for x in q) or not pf.is_navigable(q):continue
   delta=math.dist(q,anchor)
   if delta>.5:continue
   if rank==3 and math.hypot(q[0]-anchor[0],q[2]-anchor[2])>.350001:continue
   if math.dist(q,list(pf.snap_point(q)))>1e-5:continue
   if kind=='bounded_camera_projection':
    camera=source['camera_position']
    if math.hypot(q[0]-camera[0],q[2]-camera[2])>=.5 or not 0<=camera[1]-q[1]<=2:continue
   label=component(sc,q);item={'position':q,'rank':rank,'anchor':anchor,'anchor_kind':kind,'displacement':delta}
   if label not in found or (rank,delta)<(found[label]['rank'],found[label]['displacement']):found[label]=item
  return found
 if ck not in cache:
  seeds=[]
  if previous is not None:seeds.append((0,previous))
  if current is not None:seeds.append((1,current))
  seeds.append((2,anchor));cache[ck]=collect(seeds)
 found=dict(cache[ck])
 if expand:
  rk=(sc,node,kind,tuple(anchor))
  if rk not in ring_cache:ring_cache[rk]=collect([(3,[anchor[0]+dx,anchor[1],anchor[2]+dz]) for dx,dz in offsets[1:]])
  for label,value in ring_cache[rk].items():
   if label not in found:found[label]=value
 return found,anchor,kind
parent_ledger={r['task_key']:r for r in json.loads((ROOT/'outputs/landmark-connectivity/full-native-v4/mapping-ledger.json').read_text())['records']}
for task in new['tasks']:
 if task['scene'] not in ('V2XKFyX4ASd','s8pcmisQ38h'):
  tasks.append(dict(task));ledger.append(parent_ledger[task['task_key']]);counts['ready' if task['status']=='READY_FOR_NATIVE_MOTION' else 'blocked']+=1;continue
 oldtask=prior[task['task_key']];sc=task['scene'];choices=[];anchors=[];kinds=[]
 for node,a,b in zip(task['original_viewpoint_path'],oldtask['targets'],task['targets']):
  c,anchor,kind=options(sc,node,a,b);choices.append(c);anchors.append(anchor);kinds.append(kind)
 minimum=[{k for k,v in c.items() if v['rank']==min(x['rank'] for x in c.values())} if c else set() for c in choices]
 common=set(minimum[0]) if minimum else set()
 for c in minimum[1:]:common.intersection_update(c)
 if not common:
  choices=[options(sc,node,a,b,True)[0] for node,a,b in zip(task['original_viewpoint_path'],oldtask['targets'],task['targets'])]
  common=set(choices[0]) if choices else set()
  for c in choices[1:]:common.intersection_update(c)
 out=dict(task)
 if common:
  label=min(common,key=lambda c:sum(d[c]['rank']*1000+d[c]['displacement'] for d in choices));selected=[d[label] for d in choices];points=[d['position'] for d in selected];assert all(connected(finder(sc),a,b) for a,b in zip(points,points[1:]));out.update(targets=points,static_errors=[],status='READY_FOR_NATIVE_MOTION',mapping_methods=['grounded_'+d['anchor_kind'] for d in selected]);counts['ready']+=1;counts['changed_from_first_round']+=any(a is None or math.dist(a,b)>1e-5 for a,b in zip(oldtask['targets'],points));ledger.append({'task_key':task['task_key'],'status':'STATIC_PASS_PENDING_MOTION','choices':selected})
 else:
  out.update(status='STATIC_BLOCKED_PRESERVED',static_errors=[{'kind':'no_grounded_source_bounded_common_component','missing_candidate_indices':[i for i,c in enumerate(choices) if not c]}]);counts['blocked']+=1;ledger.append({'task_key':task['task_key'],'status':'UNRESOLVED','candidate_component_counts':[len(c) for c in choices]})
 tasks.append(out)
 if len(tasks)%2000==0:print(len(tasks),dict(counts),flush=True)
assert len(tasks)==33954
out=ROOT/'outputs/landmark-connectivity/full-native-v8';out.mkdir(exist_ok=False);result=dict(new);result.update(tasks=tasks,counts=dict(counts),status='GROUNDED_ROUTE_CANDIDATE_PENDING_MOTION',builder_sha256=digest(__file__),parent_manifest_sha256=digest(newpath));atomic_json(out/'manifest.json',result);atomic_json(out/'mapping-ledger.json',{'counts':dict(counts),'records':ledger,'limits':'No raw records or scene geometry altered. Common-component choice and source displacement are mandatory; no acceptance from coordinate mapping alone.'});print(dict(counts))
