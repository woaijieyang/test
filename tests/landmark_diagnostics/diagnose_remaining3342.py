"""Diagnose the authorized 3342 remaining tasks; retain the separate 114 unchanged."""
import os,sys,json,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[10:11]);os.nice(10)
import habitat_sim
b=ROOT/'outputs/landmark-connectivity';manifest=b/'full-native-v8/manifest.json';m=json.loads(manifest.read_text());profile=json.loads(Path(m['profile_path']).read_text());held=set(json.loads((b/'constraint-blockers.json').read_text())['task_keys']);groups=collections.defaultdict(list)
for t in m['tasks']:
 if t['status']=='STATIC_BLOCKED_PRESERVED' and t['task_key']not in held:groups[t['scene']].append(t)
assert sum(map(len,groups.values()))==3342
out=b/'remaining3342-v1';out.mkdir(exist_ok=False);scenes=[]
for sc,ts in sorted(groups.items(),key=lambda kv:-len(kv[1])):
 pf=habitat_sim.PathFinder();asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];assert pf.load_nav_mesh(asset['navmesh_path']);points={};edges={};taskrows=[]
 for t in ts:
  converted=[];missing=[]
  for i,(node,p) in enumerate(zip(t['original_viewpoint_path'],t['targets'])):
   key=(node,tuple(p) if p is not None else None)
   if key not in points:
    q=list(pf.snap_point(p)) if p is not None else None;ok=q is not None and all(math.isfinite(x) for x in q) and pf.is_navigable(q);points[key]={'node':node,'input_position':p,'mesh_position':q if ok else None,'input_to_mesh_distance':math.dist(p,q) if ok else None}
   q=points[key]['mesh_position'];converted.append(q)
   if q is None:missing.append(i)
  failed=[]
  for i,(a,c) in enumerate(zip(converted,converted[1:])):
   if a is None or c is None:continue
   key=(t['original_viewpoint_path'][i],t['original_viewpoint_path'][i+1],tuple(a),tuple(c))
   if key not in edges:
    path=habitat_sim.ShortestPath();path.requested_start=a;path.requested_end=c;ok=pf.find_path(path) and math.isfinite(path.geodesic_distance);edges[key]={'nodes':list(key[:2]),'start':a,'end':c,'reachable':bool(ok),'euclidean':math.dist(a,c),'task_keys':[]}
   if not edges[key]['reachable']:edges[key]['task_keys'].append(t['task_key']);failed.append(list(key[:2]))
  taskrows.append({'task_key':t['task_key'],'missing_target_indices':missing,'disconnected_edges':failed,'source_record_sha256':t['source_record_sha256']})
 record={'scene':sc,'task_count':len(ts),'navmesh_sha256':asset['navmesh_sha256'],'points':list(points.values()),'disconnected_edges':[v for v in edges.values() if not v['reachable']],'tasks':taskrows};atomic_json(out/(sc+'.json'),record);scenes.append({'scene':sc,'task_count':len(ts),'disconnected_pairs':len(record['disconnected_edges']),'missing_targets':sum(bool(x['missing_target_indices']) for x in taskrows)});print(scenes[-1],flush=True)
atomic_json(out/'summary.json',{'status':'DIAGNOSTIC_COMPLETE','analyzed_tasks':3342,'held_tasks':114,'original_total':33954,'scenes':scenes,'manifest_sha256':digest(manifest),'script_sha256':digest(__file__),'limits':'Diagnostic projections of existing target candidates, not an alternative acceptance protocol or actual agent motion. All 33954 original records retained.'})
