import sys,json,os,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'.cache/geometry-tools'));sys.path.insert(0,str(Path.cwd()/'scripts'))
import numpy as np,trimesh,habitat_sim
from workspace import atomic_json,ROOT
os.environ['CUDA_VISIBLE_DEVICES']=''
rows=json.loads(Path('outputs/landmark-connectivity/fine-candidate-nodes.json').read_text())['nodes']
for sc,variant in [('XcA2TqTSSAj','fine05_climb02'),('kEZ7cmS4wCh','coarse05_climb02')]:
 pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(f'outputs/landmark-connectivity/mesh-search/{sc}-{variant}.navmesh');subset=[r for r in rows if r['scene']==sc];points={r['node']:list(pf.snap_point(r['candidate_seed'])) for r in subset}
 def connected(a,b):
  q=habitat_sim.ShortestPath();q.requested_start=a;q.requested_end=b;return bool(pf.find_path(q)) and math.isfinite(q.geodesic_distance)
 candidates=[r for r in subset if r['method']=='official_rxr_reference'];anchor=max(candidates,key=lambda r:pf.island_radius(points[r['node']]))['node'];origin=points[anchor]
 verts=np.asarray(pf.build_navmesh_vertices());inds=np.asarray(pf.build_navmesh_vertex_indices()).reshape(-1,3);tris=verts[inds];centers=tris.mean(axis=1);keep=np.array([connected(origin,c.tolist()) for c in centers]);component=tris[keep];out=[]
 for row in subset:
  point=points[row['node']]
  if connected(origin,point):continue
  seed=np.array(row['candidate_seed']);samefloor=component[(component[:,:,1].min(axis=1)<=seed[1]+.25)&(component[:,:,1].max(axis=1)>=seed[1]-.25)]
  if not len(samefloor):best=None;distance=None
  else:
   near=trimesh.triangles.closest_point(samefloor,np.tile(seed,(len(samefloor),1)));dist=np.linalg.norm(near-seed,axis=1);i=dist.argmin();best=near[i].tolist();distance=float(dist[i])
  out.append({'node':row['node'],'seed':row['candidate_seed'],'current':point,'nearest_main_component_same_floor':best,'distance':distance})
 atomic_json(ROOT/f'outputs/landmark-connectivity/component-distance-{sc}.json',{'scene':sc,'variant':variant,'anchor':anchor,'disconnected_nodes':out});print(sc,len(out),[(x['node'],x['distance']) for x in out[:8]],flush=True)
