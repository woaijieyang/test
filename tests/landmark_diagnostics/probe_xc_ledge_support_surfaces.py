"""Source-surface-derived in-cell probes, not a mesh, annotation or gate change."""
import os,sys,json,struct,math,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from projected_distance_reference import projected_distance
import numpy as np,habitat_sim,psutil
u=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:u[i])])
O=R/'outputs/landmark-connectivity/native-stage-trace-xc-v3';D=O/'ledge-source-surfaces-v1';D.mkdir(exist_ok=False);atomic_json(D/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
raw=(O/'native-1.bin').read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);v=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=v[ix].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);norm=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);length=np.linalg.norm(norm,axis=1);ny=np.divide(abs(norm[:,1]),length,out=np.zeros(len(tri)),where=length>1e-12)
settings=json.loads((O/'validation.json').read_text())['native_build_config'];cs,ch=settings[:2];records=json.loads((O/'ledge-bridges-v2/validation.json').read_text())['removed_bridge_spans'];m=json.loads((R/'outputs/landmark-connectivity/full-native-v11/manifest.json').read_text());profile=json.loads(Path(m['profile_path']).read_text());asset=profile['assets']['mp3d/XcA2TqTSSAj/XcA2TqTSSAj.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path'])
def clip_axis(poly,axis,bound,keep_above):
 result=[]
 if not poly:return result
 for a,b in zip(poly,[*poly[1:],poly[0]]):
  ina=a[axis]>=bound if keep_above else a[axis]<=bound;inb=b[axis]>=bound if keep_above else b[axis]<=bound
  if ina:result.append(a)
  if ina!=inb:result.append(a+(b-a)*((bound-a[axis])/(b[axis]-a[axis])))
 return result
rows=[]
for record in records:
 center=np.array(record['world_center']);bounds=[(0,center[0]-cs/2,center[0]+cs/2),(2,center[2]-cs/2,center[2]+cs/2),(1,center[1]-ch,center[1]+ch)];floorids=np.flatnonzero((lo[:,0]<=center[0]+cs/2)&(hi[:,0]>=center[0]-cs/2)&(lo[:,2]<=center[2]+cs/2)&(hi[:,2]>=center[2]-cs/2)&(lo[:,1]<=center[1]+ch)&(hi[:,1]>=center[1]-ch)&(ny>=math.cos(math.pi/4)-1e-9));candidates={}
 for j in floorids:
  poly=list(tri[j])
  for axis,low,high in bounds:poly=clip_axis(clip_axis(poly,axis,low,True),axis,high,False)
  if len(poly)<3:continue
  pts=poly+[np.mean(poly,axis=0)]+[(a+b)/2 for a,b in zip(poly,[*poly[1:],poly[0]])]
  for q in pts:
   key=tuple(float(x) for x in q)
   if key not in candidates:candidates[key]={'position':q.tolist(),'support_triangle':int(j)}
 colliderids=np.flatnonzero((lo[:,0]<center[0]+cs/2+.1)&(hi[:,0]>center[0]-cs/2-.1)&(lo[:,2]<center[2]+cs/2+.1)&(hi[:,2]>center[2]-cs/2-.1)&(lo[:,1]<center[1]+ch+1.5)&(hi[:,1]>center[1]-ch+1e-5))
 outcomes=[]
 for key,c in candidates.items():
  q=np.array(key);first=None
  for j in colliderids:
   poly=clip_axis(list(tri[j]),1,q[1]+1e-5,True);poly=clip_axis(poly,1,q[1]+1.5,False)
   if len(poly)<3:continue
   d=projected_distance(poly,q)
   if d<.1-1e-6:first={'triangle':int(j),'distance':d,'maximum_contact_height':float(max(p[1] for p in poly)-q[1])};break
  hit=None
  if first is None:
   sn=pf.snap_point(q);hit={'native_snap':sn.tolist(),'snap_distance':float(np.linalg.norm(sn-q)) if np.isfinite(sn).all() else None,'is_navigable':bool(pf.is_navigable(q))}
  outcomes.append({**c,'source_body_clear':first is None,'first_contact':first,'native':hit})
 row={'raw_index':record['raw_index'],'center':center.tolist(),'source_surface_triangles':len(floorids),'candidates':outcomes,'body_clear_count':sum(c['source_body_clear'] for c in outcomes),'scope':'Same source cell xz and +/-one native height voxel; only source surface vertices, edge midpoints and face centroids. Body and collision threshold unchanged; no acceptance or source-anchor movement.'};rows.append(row);atomic_json(D/'state.json',{'status':'RUNNING','cells_done':len(rows),'clear_cells':sum(r['body_clear_count']>0 for r in rows)})
atomic_json(D/'validation.json',{'status':'COMPLETE_SOURCE_SURFACE_PROBES_NOT_ACCEPTANCE','rows':rows,'cells':len(rows),'clear_cells':sum(r['body_clear_count']>0 for r in rows),'total_candidates':sum(len(r['candidates']) for r in rows),'source_geometry_sha256':digest(O/'native-1.bin'),'bridge_receipt_sha256':digest(O/'ledge-bridges-v2/validation.json'),'active_navmesh_sha256':asset['navmesh_sha256'],'script_sha256':digest(__file__),'distance_reference_sha256':digest(R/'tests/landmark_diagnostics/projected_distance_reference.py'),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Finite geometry-derived samples are not an exhaustive certificate or stable support test. A clear source point or native snap does not prove entire route, accepted source bounds, native actions or replay.'});atomic_json(D/'state.json',{'status':'COMPLETE','cells':len(rows),'clear_cells':sum(r['body_clear_count']>0 for r in rows),'candidates':sum(len(r['candidates']) for r in rows)});print((D/'state.json').read_text())
