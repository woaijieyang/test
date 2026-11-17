"""Recheck formerly None camera seeds on already-built meshes, no new mesh search."""
import os,sys,json,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[28:29]);os.nice(15)
import habitat_sim
b=ROOT/'outputs/landmark-connectivity';mp=b/'full-native-v8/manifest.json';m=json.loads(mp.read_text());held=set(json.loads((b/'constraint-blockers.json').read_text())['task_keys']);identity={(x['scene'],x['node']):x for x in json.loads((b/'published-identity-nodes.json').read_text())['nodes']};nodes={}
for t in m['tasks']:
 if t['status']!='STATIC_BLOCKED_PRESERVED' or t['task_key'] in held:continue
 for node,seed in zip(t['original_viewpoint_path'],t['targets']):
  if seed is None and identity[(t['scene'],node)]['method']=='UNRESOLVED_no_direct_identity':nodes.setdefault((t['scene'],node),[]).append(t['task_key'])
profile=json.loads(Path(m['profile_path']).read_text());meshes=collections.defaultdict(dict)
for sc,node in nodes:
 asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];meshes[sc][asset['navmesh_path']]={'name':'current','sha256':asset['navmesh_sha256']}
 p=b/'static-scene-search-v1'/(sc+'.json')
 if p.exists():
  for v in json.loads(p.read_text())['variants']:meshes[sc][v['mesh_path']]={'name':v['variant'],'sha256':v['mesh_sha256']}
for name in ['remaining3342-additional-scenes-v2','remaining3342-fine-corridor-v1','remaining3342-gap-study-v1']:
 p=b/name/'summary.json'
 for sc in json.loads(p.read_text())['scenes']:
  if sc['scene'] not in meshes:continue
  for v in sc['variants']:meshes[sc['scene']][v['mesh_path']]={'name':name+'/'+v['name'],'sha256':v['mesh_sha256']}
rows=[];positive=[]
for sc,assets in meshes.items():
 for path,meta in assets.items():
  pf=habitat_sim.PathFinder();assert digest(path)==meta['sha256'];assert pf.load_nav_mesh(path)
  for (scene,node),tasks in nodes.items():
   if scene!=sc:continue
   camera=identity[(scene,node)]['camera_position'];candidates={}
   for i in range(101):
    q=list(pf.snap_point([camera[0],camera[1]-.02*i,camera[2]]))
    if not all(math.isfinite(x) for x in q) or not pf.is_navigable(q):continue
    h=math.hypot(q[0]-camera[0],q[2]-camera[2]);drop=camera[1]-q[1]
    if h>=.5 or not 0<=drop<=2 or math.dist(q,list(pf.snap_point(q)))>1e-5:continue
    candidates[tuple(round(v,6) for v in q)]={'position':q,'horizontal':h,'drop':drop}
   row={'scene':scene,'node':node,'task_keys':tasks,'mesh':path,'mesh_name':meta['name'],'mesh_sha256':meta['sha256'],'bounded_candidates':list(candidates.values())};rows.append(row)
   if candidates:positive.append({'scene':scene,'node':node,'mesh_name':meta['name'],'candidates':len(candidates),'tasks':len(tasks)})
atomic_json(b/'none-seed-recheck-v1.json',{'status':'DIAGNOSTIC_COMPLETE','unique_unresolved_nodes':len(nodes),'profile_node_checks':len(rows),'positive_checks':positive,'records':rows,'manifest_sha256':digest(mp),'script_sha256':digest(__file__),'limits':'Fresh bounded downward projection only; no adoption, source-geometry or whole-route acceptance. Held114 unchanged. Tests whether early None return misses candidates on existing meshes.'});print('nodes',len(nodes),'checks',len(rows),'positive',positive)
