import os,sys,json,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'.cache/geometry-tools'));sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[28:29]);os.nice(15)
import numpy as np,trimesh
b=ROOT/'outputs/landmark-connectivity';base=b/'remaining3342-gap-geometry-v1';clear=json.loads((base/'classification.json').read_text())['clear_centerline_candidates'];rows=[]
for sc in sorted({x['scene'] for x in clear}):
 gp=ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb';mesh=trimesh.load(str(gp),force='scene',process=False).to_geometry();mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float));tri=np.asarray(mesh.triangles);normal=mesh.face_normals[:,1];lo=tri.min(axis=1);hi=tri.max(axis=1);detail=json.loads((base/(sc+'.json')).read_text())
 for candidate in [x for x in clear if x['scene']==sc]:
  edge=next(e for e in detail['pairs'] if e['nodes']==candidate['nodes']);points=[]
  for sample in edge['samples']:
   p=np.asarray(sample['position']);ids=np.flatnonzero((lo[:,0]<=p[0]+.11)&(hi[:,0]>=p[0]-.11)&(lo[:,2]<=p[2]+.11)&(hi[:,2]>=p[2]-.11)&(lo[:,1]<=p[1]+.5)&(hi[:,1]>=p[1]-.5)&(np.abs(normal)>=math.cos(math.pi/4)));local=tri[ids];ring=[]
   for k in range(24):
    xz=p[[0,2]]+.1*np.array([math.cos(k*math.pi/12),math.sin(k*math.pi/12)]);heights=[]
    for t in local:
     a=t[1,[0,2]]-t[0,[0,2]];c=t[2,[0,2]]-t[0,[0,2]];w=xz-t[0,[0,2]];den=a[0]*c[1]-a[1]*c[0]
     if abs(den)<1e-10:continue
     u=(w[0]*c[1]-c[0]*w[1])/den;v=(a[0]*w[1]-w[0]*a[1])/den
     if u>=0 and v>=0 and u+v<=1:heights.append(float(t[0,1]+u*(t[1,1]-t[0,1])+v*(t[2,1]-t[0,1])-p[1]))
    ring.append(min(heights,key=abs) if heights else None)
   points.append({'position':p.tolist(),'rim_surface_offsets':ring,'missing_rim_samples':sum(x is None for x in ring),'max_absolute_offset':max((abs(x) for x in ring if x is not None),default=None)})
  rows.append({'scene':sc,'nodes':candidate['nodes'],'points':points,'missing_rim_total':sum(p['missing_rim_samples'] for p in points),'max_absolute_offset':max((p['max_absolute_offset'] for p in points if p['max_absolute_offset'] is not None),default=None),'scene_sha256':digest(gp)});print(sc,candidate['nodes'],rows[-1]['missing_rim_total'],rows[-1]['max_absolute_offset'],flush=True)
atomic_json(base/'clear-gap-footprint.json',{'status':'DIAGNOSTIC_COMPLETE','records':rows,'script_sha256':digest(__file__),'limits':'24 perimeter samples at radius0.1 help localize ledge/support discontinuity; finite sampling is not a full contact-dynamics or no-alternative-route proof. No acceptance threshold changed.'})
