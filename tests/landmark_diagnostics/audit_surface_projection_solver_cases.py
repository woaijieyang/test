import os,sys,json,math,collections,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from bounded_triangle_projection import closest_in_horizontal_disk
import numpy as np,habitat_sim
B=R/'outputs/landmark-connectivity';O=B/'vfua-component-surface-projection-v1';source=O/'validation.json';v=json.loads(source.read_text());m=json.loads((B/'full-native-v11/manifest.json').read_text());profile=json.loads(Path(m['profile_path']).read_text());sc='VFuaQ6m2Qom';asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert digest(asset['navmesh_path'])==v['mesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path']);verts=np.asarray(pf.build_navmesh_vertices(),float);idx=np.asarray(pf.build_navmesh_vertex_indices(),int).reshape(-1,3);tri=verts[idx];native={(r['scene'],r['node']):r['native_candidates'][0] for r in json.loads((B/'native-mapping.json').read_text())['nodes']};identity={(r['scene'],r['node']):r for r in json.loads((B/'published-identity-nodes.json').read_text())['nodes']};rows=[];counts=collections.Counter()
for node,index in sorted({(r['node'],r['triangle']) for r in v['constrained_solver_failures']}):
 info=identity[(sc,node)];anchor=native.get((sc,node),info['position']);assert anchor is not None;q=closest_in_horizontal_disk(tri[index],anchor,.35);row={'node':node,'triangle':index,'anchor':anchor}
 if q is None:label='NO_POINT_FOUND_IN_HORIZONTAL_TRIANGLE_INTERSECTION'
 else:
  E=np.column_stack((tri[index,1]-tri[index,0],tri[index,2]-tri[index,0]));uv,*_=np.linalg.lstsq(E,q-tri[index,0],rcond=None);assert np.linalg.norm(tri[index,0]+E@uv-q)<1e-7 and min(uv)>=-1e-7 and sum(uv)<=1+1e-7;distance=math.dist(anchor,q.tolist());row.update(candidate=q.tolist(),source_distance=distance,horizontal_distance=math.hypot(q[0]-anchor[0],q[2]-anchor[2]))
  if distance>.5:label='CLOSEST_CONSTRAINED_POINT_OUTSIDE_SOURCE_SPHERE'
  else:
   snap=list(pf.snap_point(q));row['snap']=snap;row['snap_residual']=math.dist(q.tolist(),snap) if all(math.isfinite(x) for x in snap) else None;label='VALID_BOUNDED_NATIVE_SURFACE_POINT' if row['snap_residual'] is not None and row['snap_residual']<=1e-5 and pf.is_navigable(q) else 'NATIVE_MEMBERSHIP_UNRESOLVED'
 row['classification']=label;counts[label]+=1;rows.append(row)
atomic_json(O/'solver-case-geometry-audit.json',{'status':'COMPLETE_CONSTRAINED_PROJECTION_DIAGNOSTIC','original_failure_occurrences':len(v['constrained_solver_failures']),'unique_node_triangle_pairs':len(rows),'counts':dict(counts),'rows':rows,'source_validation_sha256':digest(source),'projection_helper_sha256':digest(R/'tests/landmark_diagnostics/bounded_triangle_projection.py'),'script_sha256':digest(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Same horizontal.35 and source sphere.5. No bounds expanded, coordinate adoption or actual-motion proof. Numerical negatives are not physical infeasibility proofs.'});print(dict(counts),len(rows))
