"""Localize why a formerly usable mJX camera seed disappears on fine meshes."""
import os,sys,json,math
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'.cache/geometry-tools'));sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[28:29]);os.nice(15)
import numpy as np,trimesh,habitat_sim
support_code=(ROOT/'tests/landmark_diagnostics/audit_unmapped_support_geometry.py').read_text();exec(support_code[support_code.index('def clip_y('):support_code.index('records=[]')]);body_code=(ROOT/'tests/landmark_diagnostics/audit_remaining_body_clearance.py').read_text();exec(body_code[body_code.index('def clip('):body_code.index('records=[]')])
b=ROOT/'outputs/landmark-connectivity';sc='mJXqzFtmKg4';node='596c721baa6545aba7d244e239d48972';m=json.loads((b/'full-native-v8/manifest.json').read_text());t=next(t for t in m['tasks'] if t['task_key']=='train:39659');old=np.asarray(t['targets'][0]);identity=next(x for x in json.loads((b/'published-identity-nodes.json').read_text())['nodes'] if x['scene']==sc and x['node']==node);camera=np.asarray(identity['camera_position']);gp=ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb';mesh=trimesh.load(str(gp),force='scene',process=False).to_geometry();mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float));tri=np.asarray(mesh.triangles);lo=tri.min(axis=1);hi=tri.max(axis=1);normal=mesh.face_normals[:,1]
ids=np.flatnonzero((lo[:,0]<=camera[0]+.5)&(hi[:,0]>=camera[0]-.5)&(lo[:,2]<=camera[2]+.5)&(hi[:,2]>=camera[2]-.5)&(lo[:,1]<=camera[1])&(hi[:,1]>=camera[1]-2)&(np.abs(normal)>=math.cos(math.pi/4)));supports=[]
for j in ids:
 poly=clip_y(list(tri[j]),camera[1]-2,True)
 if len(poly)<3:continue
 poly=clip_y(poly,camera[1],False)
 if len(poly)<3:continue
 dist=horizontal_distance(poly,camera)
 if dist<.5:supports.append({'triangle':int(j),'horizontal_distance':dist,'min_y':float(min(p[1] for p in poly)),'max_y':float(max(p[1] for p in poly))})
body=[];ids=np.flatnonzero((lo[:,0]<old[0]+.1)&(hi[:,0]>old[0]-.1)&(lo[:,2]<old[2]+.1)&(hi[:,2]>old[2]-.1)&(lo[:,1]<old[1]+1.5)&(hi[:,1]>old[1]+1e-5))
for j in ids:
 poly=clip(list(tri[j]),old[1]+1e-5,True)
 if len(poly)<3:continue
 poly=clip(poly,old[1]+1.5,False)
 if len(poly)>=3 and distance(poly,old)<.1-1e-6:body.append({'triangle':int(j),'horizontal_distance':distance(poly,old),'min_height':float(min(p[1] for p in poly)-old[1]),'max_height':float(max(p[1] for p in poly)-old[1])})
profile=json.loads(Path(m['profile_path']).read_text());assets=[{'variant':'old_profile',**profile['assets'][f'mp3d/{sc}/{sc}.glb']}]+[{'variant':v['variant'],'navmesh_path':v['mesh_path'],'navmesh_sha256':v['mesh_sha256']} for v in json.loads((b/'static-scene-search-v1'/(sc+'.json')).read_text())['variants']];meshes=[]
for a in assets:
 pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(a['navmesh_path']);q=list(pf.snap_point(old));meshes.append({'variant':a['variant'],'mesh_sha256':digest(a['navmesh_path']),'old_position_navigable':pf.is_navigable(old),'nearest':q,'distance_from_old':math.dist(old,q),'horizontal_from_source_camera':math.hypot(q[0]-camera[0],q[2]-camera[2]),'drop_from_camera':camera[1]-q[1]})
affected=[x['task_key'] for x in m['tasks'] if x['scene']==sc and node in x['original_viewpoint_path']];out={'status':'DIAGNOSTIC_COMPLETE','scene':sc,'node':node,'task_keys':affected,'source_camera':camera.tolist(),'old_derived_position':old.tolist(),'source_sha256':digest(gp),'bounded_potential_support_triangles':supports,'old_position_body_intersections':body,'meshes':meshes,'script_sha256':digest(__file__),'limits':'Local source-geometry and mesh comparison only; collision-free support and a whole route still required. Existing native PASS is not silently reclassified or dropped.'};atomic_json(b/'mJX-six-regression-geometry.json',out);print('support_triangles',len(supports),'old_body_intersections',len(body));print('body',body[:3]);print('meshes',meshes)
