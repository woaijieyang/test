import os,sys,json,math
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'.cache/geometry-tools'));sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[28:29]);os.nice(15)
import numpy as np,trimesh
code=(ROOT/'tests/landmark_diagnostics/audit_remaining_body_clearance.py').read_text();exec(code[code.index('def clip('):code.index('records=[]')])
b=ROOT/'outputs/landmark-connectivity';r=next(x for x in json.loads((b/'none-seed-recheck-v1.json').read_text())['records'] if x['node']=='b6bfed9c855f4d67a0ece0a83fc4ef67' and x['mesh_name']=='fine025_climb03');p=np.array(r['bounded_candidates'][0]['position']);gp=ROOT/'data/scene_datasets/mp3d/mJXqzFtmKg4/mJXqzFtmKg4.glb';mesh=trimesh.load(str(gp),force='scene',process=False).to_geometry();mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float));tri=np.asarray(mesh.triangles);lo=tri.min(axis=1);hi=tri.max(axis=1);ids=np.flatnonzero((lo[:,0]<p[0]+.1)&(hi[:,0]>p[0]-.1)&(lo[:,2]<p[2]+.1)&(hi[:,2]>p[2]-.1)&(lo[:,1]<p[1]+3)&(hi[:,1]>p[1]+.3));over=[]
for j in ids:
 poly=clip(list(tri[j]),p[1]+.3,True)
 if len(poly)<3:continue
 poly=clip(poly,p[1]+3,False)
 if len(poly)>=3 and distance(poly,p)<.1:over.append({'triangle':int(j),'min_height':float(min(v[1] for v in poly)-p[1]),'max_height':float(max(v[1] for v in poly)-p[1]),'horizontal_distance':distance(poly,p)})
heights=[]
for ch in [.025,.05,.075,.1,.125,.2]:
 n=int(np.ceil(np.float32(1.5)/np.float32(ch)));heights.append({'cell_height':ch,'height_voxels':n,'old_min_accepted_quantized_gap':(n+1)*ch,'upstream626_min_accepted_quantized_gap':n*ch})
out={'status':'DIAGNOSTIC_COMPLETE','candidate':p.tolist(),'source_sha256':digest(gp),'min_obstacle_height_above_lower_0point3_band':min((x['min_height'] for x in over),default=None),'overhead_candidates':over,'quantized_gap_bounds':heights,'script_sha256':digest(__file__),'limits':'Triangle/cylinder footprint diagnostic and exact filter boundary calculation; overhead boundary estimate can be conservative and does not replace whole-route/motion checks.'};atomic_json(b/'mJX-new45-clearance.json',out);print(out['candidate'],out['min_obstacle_height_above_lower_0point3_band']);print(heights)
