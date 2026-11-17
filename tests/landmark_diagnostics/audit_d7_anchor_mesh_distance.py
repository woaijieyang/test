"""Global nearest exported detail-triangle distance to the fixed D7 source anchor."""
import os,sys,json,math,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1"
R=Path.cwd();sys.path[:0]=[str(R/"scripts"),str(R/"tests/landmark_diagnostics")]
from workspace import atomic_json,digest
from bounded_triangle_projection import triangle_closest
import numpy as np,habitat_sim
B=R/"outputs/landmark-connectivity";O=B/"d7-fine-stage-v1";D=O/"anchor-mesh-distance-v1";D.mkdir(exist_ok=False)
v=json.loads((B/"D7-grounded-fine05-v1/validation.json").read_text());r=next(r for r in v["nodes"] if r["node"]=="ee8fc6e9d50b443c95e9265e9eb8d475");anchor=np.array(r["anchor"]);reports=[]
for label,path in [("current",R/"data/derived/navmeshes/landmark-recast626-mjx-v12/profile.json"),("candidate",Path(v["profile_path"]))]:
 profile=json.loads(path.read_text());asset=profile["assets"]["mp3d/D7N2EKCX4Sj/D7N2EKCX4Sj.glb"];assert digest(asset["navmesh_path"])==asset["navmesh_sha256"];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset["navmesh_path"]);vv=np.asarray(pf.build_navmesh_vertices(),dtype=float);ii=np.asarray(pf.build_navmesh_vertex_indices(),dtype=int).reshape(-1,3);tri=vv[ii];lo=tri.min(axis=1);hi=tri.max(axis=1);delta=np.maximum(np.maximum(lo-anchor,anchor-hi),0);lower=np.sum(delta*delta,axis=1);order=np.argsort(lower);best=math.inf;point=None;tid=None;checked=0
 for j in order:
  if lower[j]>best:break
  q=triangle_closest(anchor,tri[j]);distance=float((q-anchor)@(q-anchor));checked+=1
  if distance<best:best=distance;point=q;tid=int(j)
 snap=np.asarray(pf.snap_point(anchor),dtype=float);nearest_snap=np.asarray(pf.snap_point(point),dtype=float)
 reports.append({"label":label,"profile_sha256":digest(path),"navmesh_sha256":asset["navmesh_sha256"],"detail_triangles":len(tri),"triangles_exactly_checked":checked,"minimum_distance_m":math.sqrt(best),"closest_point":point.tolist(),"closest_triangle":tid,"closest_triangle_vertices":tri[tid].tolist(),"closest_point_native_is_navigable":bool(pf.is_navigable(point)),"closest_point_native_projection_error":float(np.linalg.norm(nearest_snap-point)),"native_anchor_snap":snap.tolist(),"native_anchor_snap_distance":float(np.linalg.norm(snap-anchor)),"any_exported_detail_surface_within_source_sphere":best<=.25})
atomic_json(D/"validation.json",{"status":"COMPLETE_FINAL_MESH_DISTANCE_DIAGNOSIS","node":r["node"],"anchor":anchor.tolist(),"source_radius_m":.5,"affected_regressions":15,"profiles":reports,"projection_helper_sha256":digest(R/"tests/landmark_diagnostics/bounded_triangle_projection.py"),"script_sha256":digest(__file__),"limits":"Global distance over exported native detail triangles using AABB lowerbound pruning. Native isNavigable/resnap checked for closestpoint. Not source-body or real-motion proof; no source bound change or extra sampled candidate adopted.","time":datetime.datetime.now().isoformat()});print(reports)
