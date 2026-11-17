"""Conservative support-surface audit for still-unmapped camera viewpoints."""
import sys,os,json,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'.cache/geometry-tools'));sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[8:9]);os.nice(10)
import trimesh,numpy as np
r=json.loads(Path('outputs/landmark-connectivity/missing96-profile-v3-projection.json').read_text());groups=collections.defaultdict(list)
for row in r['records']:
 if not row['bounded_downward_candidates']:groups[row['scene']].append(row)
def clip_y(poly,bound,above):
 out=[]
 for a,b in zip(poly,poly[1:]+poly[:1]):
  ia=a[1]>=bound if above else a[1]<=bound;ib=b[1]>=bound if above else b[1]<=bound
  if ia:out.append(a)
  if ia!=ib:out.append(a+(bound-a[1])/(b[1]-a[1])*(b-a))
 return out
def horizontal_distance(poly,p):
 p=p[[0,2]];vertices=[v[[0,2]] for v in poly];cross=[];dist=[]
 for a,b in zip(vertices,vertices[1:]+vertices[:1]):
  d=b-a;v=p-a;cross.append(d[0]*v[1]-d[1]*v[0]);length=float(np.dot(d,d));t=float(np.clip(np.dot(v,d)/length,0,1)) if length>1e-14 else 0;dist.append(float(np.linalg.norm(p-(a+t*d))))
 if all(x>=-1e-8 for x in cross) or all(x<=1e-8 for x in cross):return 0.
 return min(dist)
records=[]
for sc,rows in sorted(groups.items()):
 source=ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb';mesh=trimesh.load(str(source),force='scene',process=False).to_geometry();mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],dtype=float));tri=np.asarray(mesh.triangles);lo=tri.min(axis=1);hi=tri.max(axis=1);slopes=np.abs(mesh.face_normals[:,1])>=math.cos(math.pi/4)-1e-9
 for row in rows:
  camera=np.array(row['camera_position']);mask=slopes&(lo[:,0]<=camera[0]+.5)&(hi[:,0]>=camera[0]-.5)&(lo[:,2]<=camera[2]+.5)&(hi[:,2]>=camera[2]-.5)&(lo[:,1]<=camera[1])&(hi[:,1]>=camera[1]-2);hits=[]
  for index in np.flatnonzero(mask):
   poly=clip_y(list(tri[index]),camera[1]-2,True)
   if len(poly)<3:continue
   poly=clip_y(poly,camera[1],False)
   if len(poly)<3:continue
   d=horizontal_distance(poly,camera)
   if d<.5:hits.append({'triangle':int(index),'horizontal_distance':d,'vertices':tri[index].tolist()})
  records.append({'scene':sc,'node':row['node'],'camera_position':row['camera_position'],'potential_support_triangle_count':len(hits),'no_potential_support_inside_allowed_region':not hits,'nearest_candidates':sorted(hits,key=lambda h:h['horizontal_distance'])[:3],'scene_sha256':digest(source)});print(sc,row['node'],'support_triangles',len(hits),flush=True)
report={'status':'GEOMETRY_DIAGNOSTIC_COMPLETE','bounds':{'horizontal_displacement_strictly_below_m':.5,'downward_interval_m':[0,2],'maximum_surface_slope_deg':45},'coordinate_transform':'Habitat MP3D (x,z,-y)','method':'Clip source mesh triangles to vertical interval, include both normal orientations conservatively, test distance to exact projected triangle polygons. Surface existence is necessary but not sufficient for full 1.5m/.1m body clearance.','records':records,'no_support_count':sum(r['no_potential_support_inside_allowed_region'] for r in records),'with_surface_but_unmapped_count':sum(not r['no_potential_support_inside_allowed_region'] for r in records),'script_sha256':digest(__file__)};atomic_json(ROOT/'outputs/landmark-connectivity/unmapped-support-geometry.json',report)
