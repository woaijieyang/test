"""Source-geometry evidence at all localized component gaps; diagnostic only."""
import os,sys,json,math,collections,atexit
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'.cache/geometry-tools'));sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[28:29]);os.nice(15)
import numpy as np,trimesh
helper=ROOT/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';code=helper.read_text();exec(code[code.index('def clip('):code.index('records=[]')])
b=ROOT/'outputs/landmark-connectivity';source=b/'remaining3342-all-gaps-v1/classification.json';d=json.loads(source.read_text());out=b/'remaining3342-gap-geometry-v1';out.mkdir(exist_ok=False);results=[];atomic_json(out/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});atomic_json(out/'state.json',{'status':'RUNNING','completed_scenes':0});groups=collections.defaultdict(list)
for r in d['pairs']:groups[r['scene']].append(r)
def end_state():
 if not (out/'summary.json').exists():atomic_json(out/'state.json',{'status':'FAILED','completed_scenes':len(results),'reason':'See retained log'})
atexit.register(end_state)
for sc,pairs in groups.items():
 gp=ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb';mesh=trimesh.load(str(gp),force='scene',process=False).to_geometry();mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float));tri=np.asarray(mesh.triangles);lo=tri.min(axis=1);hi=tri.max(axis=1);normal=mesh.face_normals[:,1];rows=[]
 for edge in pairs:
  a=np.array(edge['boundary_a']);c=np.array(edge['boundary_b']);samples=[];n=max(1,math.ceil(math.dist(a,c)/.05))
  for i in range(n+1):
   p=a+(c-a)*i/n;near=np.flatnonzero((lo[:,0]<p[0]+.1)&(hi[:,0]>p[0]-.1)&(lo[:,2]<p[2]+.1)&(hi[:,2]>p[2]-.1)&(lo[:,1]<p[1]+1.5)&(hi[:,1]>p[1]-.5));hits=[];supports=[]
   for j in near:
    t=tri[j];poly=clip(list(t),p[1]+1e-5,True)
    if len(poly)>=3:
     poly=clip(poly,p[1]+1.5,False)
     if len(poly)>=3 and distance(poly,p)<.1-1e-6:hits.append({'triangle':int(j),'min_height':float(min(v[1] for v in poly)-p[1]),'max_height':float(max(v[1] for v in poly)-p[1])})
    if abs(normal[j])<math.cos(math.pi/4):continue
    u=t[1,[0,2]]-t[0,[0,2]];v=t[2,[0,2]]-t[0,[0,2]];w=p[[0,2]]-t[0,[0,2]];den=u[0]*v[1]-u[1]*v[0]
    if abs(den)<1e-10:continue
    alpha=(w[0]*v[1]-v[0]*w[1])/den;beta=(u[0]*w[1]-w[0]*u[1])/den
    if alpha>=0 and beta>=0 and alpha+beta<=1:
     y=t[0,1]+alpha*(t[1,1]-t[0,1])+beta*(t[2,1]-t[0,1]);supports.append(float(y-p[1]))
   samples.append({'position':p.tolist(),'fraction':i/n,'body_intersections':hits,'nearest_potential_support_vertical_offset':min(supports,key=abs) if supports else None})
  rows.append({'component_pair':edge['component_pair'],'nodes':edge['nodes'],'vertex_gap':edge['vertex_gap'],'samples':samples,'samples_with_high_contact':sum(any(h['max_height']>.3 for h in p['body_intersections']) for p in samples),'samples_without_support_within_0point3m':sum(p['nearest_potential_support_vertical_offset'] is None or abs(p['nearest_potential_support_vertical_offset'])>.3 for p in samples)})
 result={'scene':sc,'source_sha256':digest(gp),'pairs':rows};atomic_json(out/(sc+'.json'),result);results.append({'scene':sc,'pairs':len(rows),'high_contact_pairs':sum(r['samples_with_high_contact']>0 for r in rows),'unsupported_centerline_pairs':sum(r['samples_without_support_within_0point3m']>0 for r in rows)});atomic_json(out/'state.json',{'status':'RUNNING','completed_scenes':len(results),'last_scene':sc});print(results[-1],flush=True)
atomic_json(out/'summary.json',{'status':'DIAGNOSTIC_COMPLETE','scenes':results,'source_sha256':digest(source),'script_sha256':digest(__file__),'helper_sha256':digest(helper),'limits':'Nearest-boundary centerline samples classify investigation evidence only; contacts or missing support here do not prove no alternate route exists. The 0.3m classification band is not a changed acceptance threshold. No geometry or annotations modified; held114 and full33954 denominator preserved.'});atomic_json(out/'state.json',{'status':'COMPLETE','completed_scenes':len(results)})
