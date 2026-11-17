"""Localize candidate regressions along previously reachable native shortest paths."""
import os,sys,json,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[10:11]);os.nice(10)
import habitat_sim
b=ROOT/'outputs/landmark-connectivity';old=json.loads((b/'full-native-v4/manifest.json').read_text());tasks={t['task_key']:t for t in old['tasks']};keys=json.loads((b/'full-native-v6/static-transition-audit.json').read_text())['regressions'];profile=json.loads(Path(old['profile_path']).read_text());study=json.loads((b/'official33-mesh-study-v2/summary.json').read_text());v=next(v for s in study['results'] if s['scene']=='V2XKFyX4ASd' for v in s['variants'] if v['name']=='climb03');sc='V2XKFyX4ASd';original=profile['assets'][f'mp3d/{sc}/{sc}.glb'];a=habitat_sim.PathFinder();z=habitat_sim.PathFinder();assert a.load_nav_mesh(original['navmesh_path']);assert z.load_nav_mesh(v['mesh_path'])
def path(pf,x,y):
 q=habitat_sim.ShortestPath();q.requested_start=x;q.requested_end=y;ok=pf.find_path(q);return ok and math.isfinite(q.geodesic_distance),q
pairs={}
for k in keys:
 t=tasks[k]
 for i,(x,y) in enumerate(zip(t['targets'],t['targets'][1:])):
  xx=list(z.snap_point(x));yy=list(z.snap_point(y));ok,q=path(z,xx,yy)
  if ok:continue
  key=(t['original_viewpoint_path'][i],t['original_viewpoint_path'][i+1]);entry=pairs.setdefault(key,{'nodes':list(key),'original_start':x,'original_end':y,'new_start':xx,'new_end':yy,'task_keys':[]});entry['task_keys'].append(k)
for row in pairs.values():
 ok,q=path(a,row['original_start'],row['original_end']);assert ok;corners=[list(p) for p in q.points];samples=[]
 for start,end in zip(corners,corners[1:]):
  steps=max(1,math.ceil(math.dist(start,end)/.05))
  samples.extend([[start[j]+(end[j]-start[j])*i/steps for j in range(3)] for i in range(steps)])
 samples.append(corners[-1]);points=[]
 for p in samples:
  n=list(z.snap_point(p));finite=all(math.isfinite(x) for x in n);points.append({'old_path_position':p,'new_projection':n if finite else None,'distance':math.dist(p,n) if finite else None,'reachable_from_new_start':bool(finite and path(z,row['new_start'],n)[0])})
 changes=[i for i in range(1,len(points)) if points[i]['reachable_from_new_start']!=points[i-1]['reachable_from_new_start']]
 row.update(original_geodesic=float(q.geodesic_distance),sample_count=len(points),component_crossings=[{'before':points[i-1],'after':points[i]} for i in changes],max_projection_distance=max((p['distance'] for p in points if p['distance'] is not None),default=None))
 print(row['nodes'],len(row['task_keys']),len(changes),flush=True)
atomic_json(b/'V2-regression-boundaries.json',{'status':'DIAGNOSTIC_ONLY','task_count':len(keys),'unique_failed_directed_pairs':len(pairs),'original_mesh_sha256':digest(original['navmesh_path']),'candidate_mesh_sha256':digest(v['mesh_path']),'records':list(pairs.values()),'script_sha256':digest(__file__),'limits':'Projects old native shortest paths to localize changed connectivity; projections are diagnostic only, never execution actions.'})
