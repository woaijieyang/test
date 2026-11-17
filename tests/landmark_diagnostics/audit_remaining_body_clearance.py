"""Sample source-geometry body clearance; negative samples are not an impossibility proof."""
import os,sys,json,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'.cache/geometry-tools'));sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[8:9]);os.nice(10)
import trimesh,numpy as np
r=json.loads(Path('outputs/landmark-connectivity/unmapped-support-geometry.json').read_text());groups=collections.defaultdict(list)
for x in r['records']:
 if not x['no_potential_support_inside_allowed_region']:groups[x['scene']].append(x)
def clip(poly,y,above):
 out=[]
 for a,b in zip(poly,poly[1:]+poly[:1]):
  ia=a[1]>=y if above else a[1]<=y;ib=b[1]>=y if above else b[1]<=y
  if ia:out.append(a)
  if ia!=ib:out.append(a+(y-a[1])/(b[1]-a[1])*(b-a))
 return out
def distance(poly,p):
 v=[x[[0,2]] for x in poly];q=p[[0,2]];cross=[];dist=[]
 for a,b in zip(v,v[1:]+v[:1]):
  e=b-a;w=q-a;cross.append(e[0]*w[1]-e[1]*w[0]);den=np.dot(e,e);t=np.clip(np.dot(w,e)/den,0,1) if den>1e-14 else 0;dist.append(float(np.linalg.norm(q-a-t*e)))
 if all(x>=-1e-9 for x in cross) or all(x<=1e-9 for x in cross):return 0.
 return min(dist)
records=[]
for sc,rows in sorted(groups.items()):
 path=ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb';sha=digest(path);mesh=trimesh.load(str(path),force='scene',process=False).to_geometry();mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float));tri=np.asarray(mesh.triangles);lo=tri.min(axis=1);hi=tri.max(axis=1);normal=mesh.face_normals[:,1]
 for row in rows:
  camera=np.array(row['camera_position']);near=(lo[:,0]<camera[0]+.61)&(hi[:,0]>camera[0]-.61)&(lo[:,2]<camera[2]+.61)&(hi[:,2]>camera[2]-.61)&(lo[:,1]<camera[1]+1.5)&(hi[:,1]>camera[1]-2);ids=np.flatnonzero(near);local=tri[ids];llo=lo[ids];lhi=hi[ids];support=local[normal[ids]>=math.cos(math.pi/4)-1e-9];tested=0;free=[];collision_count=0
  for ix in range(-19,20):
   for iz in range(-19,20):
    if math.hypot(ix*.025,iz*.025)>=.5:continue
    xz=camera[[0,2]]+[ix*.025,iz*.025]
    for t in support:
     a=t[1,[0,2]]-t[0,[0,2]];b=t[2,[0,2]]-t[0,[0,2]];d=xz-t[0,[0,2]];den=a[0]*b[1]-a[1]*b[0]
     if abs(den)<1e-10:continue
     u=(d[0]*b[1]-b[0]*d[1])/den;v=(a[0]*d[1]-d[0]*a[1])/den
     if u<0 or v<0 or u+v>1:continue
     y=t[0,1]+u*(t[1,1]-t[0,1])+v*(t[2,1]-t[0,1])+.02
     if not camera[1]-2<=y<=camera[1]:continue
     p=np.array([xz[0],y,xz[1]]);tested+=1;obstacles=np.flatnonzero((llo[:,0]<p[0]+.1)&(lhi[:,0]>p[0]-.1)&(llo[:,2]<p[2]+.1)&(lhi[:,2]>p[2]-.1)&(llo[:,1]<p[1]+1.5)&(lhi[:,1]>p[1]+1e-5));blocked=False
     for j in obstacles:
      poly=clip(list(local[j]),p[1]+1e-5,True)
      if len(poly)<3:continue
      poly=clip(poly,p[1]+1.5,False)
      if len(poly)>=3 and distance(poly,p)<.1-1e-6:blocked=True;break
     if blocked:collision_count+=1
     else:free.append(p.tolist())
  item={'scene':sc,'node':row['node'],'camera_position':row['camera_position'],'sampled_supported_positions':tested,'collision_count':collision_count,'collision_free_count':len(free),'closest_free_candidates':sorted(free,key=lambda p:math.hypot(p[0]-camera[0],p[2]-camera[2]))[:32],'scene_sha256':sha};records.append(item);print(sc,row['node'],tested,len(free),flush=True);atomic_json(ROOT/'outputs/landmark-connectivity/remaining-body-clearance.partial.json',{'records':records})
atomic_json(ROOT/'outputs/landmark-connectivity/remaining-body-clearance.json',{'status':'DIAGNOSTIC_COMPLETE_NOT_ACCEPTED','records':records,'settings':{'radius':.1,'height':1.5,'horizontal_grid':.025,'horizontal_bound':.5,'downward_bound':2,'foot_support_offset':.02,'max_support_slope_deg':45},'limits':'Conservative cylinder-triangle check at sampled supported positions; no free sample is not a continuous-space impossibility proof, especially on slopes/steps. Free candidates still require navmesh connectivity, source-semantic review and actual movement validation. No scene or raw annotation changes.','script_sha256':digest(__file__)})
