import os,sys,json,math
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'.cache/geometry-tools'));sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[10:11]);os.nice(10)
import numpy as np,trimesh
source=Path('tests/landmark_diagnostics/audit_remaining_body_clearance.py').read_text();exec(source[source.index('def clip('):source.index('records=[]')])
b=ROOT/'outputs/landmark-connectivity';report=json.loads((b/'V2-regression-boundaries.json').read_text());gp=ROOT/'data/scene_datasets/mp3d/V2XKFyX4ASd/V2XKFyX4ASd.glb';mesh=trimesh.load(str(gp),force='scene',process=False).to_geometry();mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float));tri=np.asarray(mesh.triangles);lo=tri.min(axis=1);hi=tri.max(axis=1);positions={}
for row in report['records']:
 for crossing in row['component_crossings']:
  for side in crossing.values():
   for kind in ['old_path_position','new_projection']:
    v=side[kind]
    if v is not None:positions.setdefault(tuple(v),set()).add(kind)
rows=[]
for xyz,kinds in positions.items():
 p=np.array(xyz);near=np.flatnonzero((lo[:,0]<p[0]+.1)&(hi[:,0]>p[0]-.1)&(lo[:,2]<p[2]+.1)&(hi[:,2]>p[2]-.1)&(lo[:,1]<p[1]+1.5)&(hi[:,1]>p[1]+1e-5));hits=[]
 for j in near:
  poly=clip(list(tri[j]),p[1]+1e-5,True)
  if len(poly)<3:continue
  poly=clip(poly,p[1]+1.5,False)
  if len(poly)>=3 and distance(poly,p)<.1-1e-6:hits.append({'triangle':int(j),'horizontal_distance':distance(poly,p),'min_height_from_foot':float(min(v[1] for v in poly)-p[1]),'max_height_from_foot':float(max(v[1] for v in poly)-p[1])})
 rows.append({'position':list(xyz),'kinds':sorted(kinds),'intersecting_triangles':hits});print(sorted(kinds),len(hits),min((h['min_height_from_foot'] for h in hits),default=None),max((h['max_height_from_foot'] for h in hits),default=None),flush=True)
atomic_json(b/'V2-boundary-geometry.json',{'status':'DIAGNOSTIC_ONLY','scene_sha256':digest(gp),'radius':.1,'height':1.5,'records':rows,'script_sha256':digest(__file__),'limits':'Source cylinder/triangle intersections at localized points, not path repair. Low risers must be distinguished from head-clearance failures. No scene modifications.'})
