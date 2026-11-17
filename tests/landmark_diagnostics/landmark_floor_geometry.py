import json,sys,os,time,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'.cache/geometry-tools'))
import trimesh,numpy as np
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2])
source=json.loads(Path('outputs/landmark-connectivity/candidate-nodes.json').read_text());groups=collections.defaultdict(list)
for row in source['nodes']:
 if row['method']=='camera_minus_1point5_candidate' or row['needs_geometric_review']:groups[row['scene']].append(row)
root=Path('outputs/landmark-connectivity/geometry');root.mkdir(exist_ok=True)
for sc,rows in sorted(groups.items()):
 output=root/(sc+'.json')
 if output.exists():continue
 t=time.time();mesh=trimesh.load('data/scene_datasets/mp3d/'+sc+'/'+sc+'.glb',force='scene',process=False).to_geometry();mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],dtype=float))
 tri=np.asarray(mesh.triangles);xz=tri[:,:,[0,2]];v0=xz[:,1]-xz[:,0];v1=xz[:,2]-xz[:,0];den=v0[:,0]*v1[:,1]-v1[:,0]*v0[:,1];valid=abs(den)>1e-10;out=[]
 for row in rows:
  camera=np.array(row['camera_position']);v2=camera[[0,2]]-xz[:,0];u=np.zeros(len(tri));v=np.zeros(len(tri));u[valid]=(v2[valid,0]*v1[valid,1]-v1[valid,0]*v2[valid,1])/den[valid];v[valid]=(v0[valid,0]*v2[valid,1]-v2[valid,0]*v0[valid,1])/den[valid]
  inside=valid&(u>=0)&(v>=0)&(u+v<=1);y=tri[:,0,1]+u*(tri[:,1,1]-tri[:,0,1])+v*(tri[:,2,1]-tri[:,0,1]);ids=np.flatnonzero(inside)
  hits=[{'height':float(y[i]),'camera_drop':float(camera[1]-y[i]),'normal_y':float(mesh.face_normals[i][1]),'triangle':int(i)} for i in ids]
  out.append({'node':row['node'],'camera_position':row['camera_position'],'seed':row['seed'],'hits':sorted(hits,key=lambda h:h['height'])})
 output.write_text(json.dumps({'scene':sc,'transform':'x,z,-y','nodes':out},indent=2));print(sc,len(rows),round(time.time()-t,2),flush=True)
