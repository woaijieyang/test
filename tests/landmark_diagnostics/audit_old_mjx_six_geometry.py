"""Independent source-cylinder check on newly recovered VFua native trajectories."""
import os,sys,json,gzip,hashlib,math
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'.cache/geometry-tools'));sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[27:28]);os.nice(15)
import numpy as np,trimesh
helper=ROOT/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';source=helper.read_text();exec(source[source.index('def clip('):source.index('records=[]')])
b=ROOT/'outputs/landmark-connectivity';run=b/'full-native-v8';keys=['train:39659','train:75836','train:100549','train:100550','train:36008','train:36009'];assert len(keys)==6;records=[];points={};trace_receipts=[]
for key in keys:
 code=hashlib.sha256(key.encode()).hexdigest();shard=int(code,16)%8;rp=run/f'shard-{shard:02}'/(code[:24]+'.result.json');r=json.loads(rp.read_text());assert r['status']=='PASS',key;tp=run/r['trace_path'];assert digest(tp)==r['trace_sha256'];t=json.load(gzip.open(tp,'rt'));assert t['task_key']==key and t['mesh_sha256'];trace_receipts.append({'path':str(tp),'sha256':digest(tp)});positions=t['positions']
 for i,(a,c) in enumerate(zip(positions,positions[1:])):
  steps=max(1,math.ceil(math.dist(a,c)/.05))
  for j in range(steps+1):
   p=[a[k]+(c[k]-a[k])*j/steps for k in range(3)];pk=tuple(round(x,5) for x in p);points.setdefault(pk,{'position':p,'occurrences':[]})['occurrences'].append({'task_key':key,'action_index':i,'fraction':j/steps})
sc='mJXqzFtmKg4';gp=ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.glb';mesh=trimesh.load(str(gp),force='scene',process=False).to_geometry();mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float));tri=np.asarray(mesh.triangles);lo=tri.min(axis=1);hi=tri.max(axis=1);collisions=[]
for n,item in enumerate(points.values()):
 p=np.array(item['position']);near=np.flatnonzero((lo[:,0]<p[0]+.1)&(hi[:,0]>p[0]-.1)&(lo[:,2]<p[2]+.1)&(hi[:,2]>p[2]-.1)&(lo[:,1]<p[1]+1.5)&(hi[:,1]>p[1]+1e-5));hits=[]
 for j in near:
  poly=clip(list(tri[j]),p[1]+1e-5,True)
  if len(poly)<3:continue
  poly=clip(poly,p[1]+1.5,False)
  if len(poly)>=3 and distance(poly,p)<.1-1e-6:hits.append({'triangle':int(j),'distance':distance(poly,p),'min_height':float(min(v[1] for v in poly)-p[1]),'max_height':float(max(v[1] for v in poly)-p[1])})
 if hits:collisions.append({**item,'hits':hits})
 if n%1000==0:print(n,'/',len(points),'contact_samples',len(collisions),flush=True)
atomic_json(b/'mJX-region-control-v1/old-six-source-body-audit.json',{'status':'NO_INTERSECTION_SAMPLED' if not collisions else 'CONTACTS_REQUIRE_REVIEW','scene':sc,'tasks':len(keys),'unique_sweep_samples':len(points),'contact_samples':len(collisions),'contacts':collisions,'scene_sha256':digest(gp),'trace_receipts':trace_receipts,'script_sha256':digest(__file__),'helper_sha256':digest(helper),'limits':'Cylinder source-triangle intersection at <=0.05m linear interpolation spacing; conservative diagnostics, not a replacement for native trajectory replay. Interpolated stairs can contact low risers and require evidence review, not automatic acceptance.'})
print('complete',len(points),len(collisions),flush=True)
