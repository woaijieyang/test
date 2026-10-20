"""Locate geometric gaps between navmesh components for prioritized remaining scenes."""
import os,sys,json,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[10:11]);os.nice(10)
import numpy as np,habitat_sim
from scipy.spatial import cKDTree
b=ROOT/'outputs/landmark-connectivity';profile=json.loads(Path(json.loads((b/'full-native-v8/manifest.json').read_text())['profile_path']).read_text());results=[]
out=b/'remaining3342-all-gaps-v1';out.mkdir(exist_ok=False)
atomic_json(out/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
for sc in [r['scene'] for r in json.loads((b/'remaining3342-v1/summary.json').read_text())['scenes']]:
 data=json.loads((b/'remaining3342-v1'/(sc+'.json')).read_text());pf=habitat_sim.PathFinder();asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert pf.load_nav_mesh(asset['navmesh_path']);vertices=np.asarray(pf.build_navmesh_vertices());indices=np.asarray(pf.build_navmesh_vertex_indices()).reshape(-1,3);tri=vertices[indices];reps=[];radii=[];groups=collections.defaultdict(list)
 def connected(a,c):
  q=habitat_sim.ShortestPath();q.requested_start=a;q.requested_end=c;return pf.find_path(q) and math.isfinite(q.geodesic_distance)
 def component(p):
  radius=round(float(pf.island_radius(p)),6)
  for i,(r,q) in enumerate(zip(radii,reps)):
   if r==radius and connected(p,q):return i
  radii.append(radius);reps.append(list(p));return len(reps)-1
 for edge in data['disconnected_edges']:
  edge['start_component']=component(edge['start']);edge['end_component']=component(edge['end'])
 needed=len(reps)
 for i,t in enumerate(tri):
  p=t.mean(axis=0);radius=round(float(pf.island_radius(p)),6)
  for label in range(needed):
   if radii[label]==radius and connected(p,reps[label]):groups[label].extend(indices[i].tolist());break
 arrays={k:vertices[np.unique(v)] for k,v in groups.items()};cache={};rows=[]
 for edge in data['disconnected_edges']:
  key=tuple(sorted([edge['start_component'],edge['end_component']]))
  if key not in cache:
   if any(k not in arrays for k in key):cache[key]={'status':'NO_TRIANGLE_COMPONENT_MATCH'};continue
   a=arrays[key[0]];c=arrays[key[1]];dist,ix=cKDTree(c).query(a);i=int(np.argmin(dist));p=a[i];q=c[ix[i]];cache[key]={'status':'LOCATED','vertex_gap':float(dist[i]),'horizontal_gap':math.hypot(float(p[0]-q[0]),float(p[2]-q[2])),'vertical_gap':abs(float(p[1]-q[1])),'boundary_a':p.tolist(),'boundary_b':q.tolist()}
  rows.append({'nodes':edge['nodes'],'task_count':len(edge['task_keys']),'component_pair':key,**cache[key]})
 result={'scene':sc,'mesh_sha256':digest(asset['navmesh_path']),'vertices':len(vertices),'triangles':len(tri),'needed_components':needed,'edges':rows};atomic_json(out/(sc+'-gaps.json'),result);results.append(result);atomic_json(out/'state.json',{'status':'RUNNING','completed_scenes':len(results)});print(sc,'components',needed,'component_pairs',len(cache),[(round(x.get('vertex_gap',-1),3),round(x.get('vertical_gap',-1),3)) for x in cache.values()],flush=True)
atomic_json(out/'prioritized-gap-summary.json',{'status':'DIAGNOSTIC_ONLY','scenes':results,'script_sha256':digest(__file__),'limits':'Closest mesh vertices localize gaps; they do not prove a collision-free continuous passage or justify changing acceptance bounds.'})

atomic_json(out/'state.json',{'status':'COMPLETE','completed_scenes':len(results)})
