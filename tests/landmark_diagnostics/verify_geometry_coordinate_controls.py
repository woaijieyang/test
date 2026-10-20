import os,sys,json,zipfile,math
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'.cache/geometry-tools'));sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[11:12]);os.nice(10)
import numpy as np,trimesh,habitat_sim
r=json.loads(Path('outputs/landmark-connectivity/unmapped-support-geometry.json').read_text());scenes=sorted({x['scene'] for x in r['records'] if x['no_potential_support_inside_allowed_region']});z=zipfile.ZipFile('outputs/landmark-connectivity/habitat_mp3d_connectivity_graphs.zip');results=[]
for sc in scenes:
 mesh=trimesh.load(str(ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb'),force='scene',process=False).to_geometry();mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float));tri=np.asarray(mesh.triangles);xz=tri[:,:,[0,2]];a=xz[:,1]-xz[:,0];b=xz[:,2]-xz[:,0];den=a[:,0]*b[:,1]-a[:,1]*b[:,0];valid=abs(den)>1e-10;pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(str(ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.navmesh'));nodes=json.loads(z.read('habitat_mp3d_connectivity_graphs/'+sc+'.json'))['nodes'];keys=sorted(nodes);selected=[keys[int(i*(len(keys)-1)/9)] for i in range(10)];rows=[]
 for key in selected:
  p=np.array(list(pf.snap_point(nodes[key])));d=p[[0,2]]-xz[:,0];u=np.zeros(len(tri));v=np.zeros(len(tri));u[valid]=(d[valid,0]*b[valid,1]-b[valid,0]*d[valid,1])/den[valid];v[valid]=(a[valid,0]*d[valid,1]-d[valid,0]*a[valid,1])/den[valid];inside=valid&(u>=0)&(v>=0)&(u+v<=1);heights=tri[:,0,1]+u*(tri[:,1,1]-tri[:,0,1])+v*(tri[:,2,1]-tri[:,0,1]);distances=np.abs(heights[inside]-p[1]);rows.append({'published_node':key,'navmesh_position':p.tolist(),'nearest_source_surface_vertical_distance':float(distances.min()) if len(distances) else None})
 results.append({'scene':sc,'controls':rows,'within_0point3m':sum(x['nearest_source_surface_vertical_distance'] is not None and x['nearest_source_surface_vertical_distance']<=.3 for x in rows)});print(sc,results[-1]['within_0point3m'],[round(x['nearest_source_surface_vertical_distance'],4) if x['nearest_source_surface_vertical_distance'] is not None else None for x in rows],flush=True)
atomic_json(ROOT/'outputs/landmark-connectivity/geometry-coordinate-controls.json',{'scope':'60 independent published navigable node controls across the six no-support scenes','results':results,'transform':'x,z,-y','limits':'Coordinate-frame sanity check only; does not change or replace endpoint/route/motion acceptance.','script_sha256':digest(__file__)})
