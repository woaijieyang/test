"""Native source support near the official V2X start, without modifying any mesh."""
import os,sys,json,struct,math
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from bounded_triangle_projection import closest_in_horizontal_disk
from swept_cylinder_reference import triangle_linear_sweep_distance
import numpy as np
B=R/'outputs/landmark-connectivity';O=B/'official-three-v2x-start-audit-v1';prior=json.loads((O/'validation.json').read_text());anchor=np.asarray(prior['shared_official_start']);catalog=json.loads((B/'native-source-catalog-v1/catalog.json').read_text());native=next(r for r in catalog['scenes'] if r['scene']==prior['scene']);assert digest(native['native_geometry_path'])==prior['native_geometry_sha256'];raw=Path(native['native_geometry_path']).read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);v=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=v[ix].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);ids=np.flatnonzero((lo[:,0]<=anchor[0]+.350001)&(hi[:,0]>=anchor[0]-.350001)&(lo[:,2]<=anchor[2]+.350001)&(hi[:,2]>=anchor[2]-.350001)&(lo[:,1]<=anchor[1]+.5)&(hi[:,1]>=anchor[1]-.5));rows=[]
for j in ids:
 t=tri[j];normal=np.cross(t[1]-t[0],t[2]-t[0]);norm=np.linalg.norm(normal)
 if norm<1e-12 or abs(normal[1])/norm<math.cos(math.pi/4):continue
 q=closest_in_horizontal_disk(t,anchor,.350001)
 if q is None or math.dist(q,anchor)>.5:continue
 candidates=np.flatnonzero((lo[:,0]<q[0]+.1)&(hi[:,0]>q[0]-.1)&(lo[:,2]<q[2]+.1)&(hi[:,2]>q[2]-.1)&(lo[:,1]<q[1]+1.5)&(hi[:,1]>q[1]+1e-5));contacts=[int(k) for k in candidates if triangle_linear_sweep_distance(tri[k],q,q)<.1-1e-6];rows.append({'triangle':int(j),'candidate':q.tolist(),'source_displacement_m':math.dist(q,anchor),'horizontal_displacement_m':math.hypot(q[0]-anchor[0],q[2]-anchor[2]),'absolute_normal_y':float(abs(normal[1])/norm),'body_contacts_at_closest_support':contacts})
# Center vertical ray is diagnostic across all scene heights, not a new permitted target domain.
ray=[]
for j in np.flatnonzero((lo[:,0]<=anchor[0])&(hi[:,0]>=anchor[0])&(lo[:,2]<=anchor[2])&(hi[:,2]>=anchor[2])):
 t=tri[j];A=np.stack([(t[1]-t[0])[[0,2]],(t[2]-t[0])[[0,2]]],axis=1)
 if abs(np.linalg.det(A))<1e-14:continue
 u,w=np.linalg.solve(A,anchor[[0,2]]-t[0,[0,2]])
 if min(u,w)<-1e-10 or u+w>1+1e-10:continue
 y=float(t[0,1]+u*(t[1,1]-t[0,1])+w*(t[2,1]-t[0,1]));normal=np.cross(t[1]-t[0],t[2]-t[0]);ray.append({'triangle':int(j),'height':y,'delta_from_anchor_m':y-float(anchor[1]),'absolute_normal_y':float(abs(normal[1])/np.linalg.norm(normal))})
p=O/'source-support-audit.json';assert not p.exists();atomic_json(p,{'status':'BOUNDED_NATIVE_SUPPORT_DIAGNOSTIC_NOT_REPAIR','official_start':anchor.tolist(),'aabb_candidate_triangles':len(ids),'slope_compatible_support_triangles':len(rows),'body_clear_closest_points':sum(not r['body_contacts_at_closest_support'] for r in rows),'records':rows,'center_ray_intersections':sorted(ray,key=lambda r:abs(r['delta_from_anchor_m'])),'source_receipt_sha256':digest(O/'validation.json'),'native_geometry_sha256':native['native_geometry_sha256'],'script_sha256':digest(__file__),'limits':'Source triangles within existing official-anchor sphere0.5/horizontal0.350001 only, both normal orientations conservatively considered. Closest support samples are not exhaustive body placements or a walkable corridor proof. No support patch or path is added, no target or acceptance threshold changed.'});print({'support_triangles':len(rows),'body_clear_closest_points':sum(not r['body_contacts_at_closest_support'] for r in rows),'nearest_center_ray':sorted(ray,key=lambda r:abs(r['delta_from_anchor_m']))[:3]})
