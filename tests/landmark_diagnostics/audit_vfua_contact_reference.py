"""Recheck VFua recorded contact claims with exact projected geometry; preserve the original audit."""
import os,sys,json,math,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(15);os.environ['CUDA_VISIBLE_DEVICES']=''
sys.path[:0]=[str(Path.cwd()/'scripts'),str(Path.cwd()/'tests/landmark_diagnostics'),str(Path.cwd()/'.cache/geometry-tools')]
from workspace import ROOT,atomic_json,digest
from projected_distance_reference import projected_distance
import numpy as np,trimesh,psutil
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])])
B=ROOT/'outputs/landmark-connectivity';audit=B/'full-native-v10/source-body-audit.json';d=json.loads(audit.read_text());gp=ROOT/f"data/scene_datasets/mp3d/{d['scene']}/{d['scene']}.glb";assert digest(gp)==d['scene_sha256'];mesh=trimesh.load(str(gp),force='scene',process=False).to_geometry();mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float));tri=np.asarray(mesh.triangles)
helper=ROOT/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';assert digest(helper)==d['helper_sha256'];s=helper.read_text();exec(s[s.index('def clip('):s.index('records=[]')]);checked=0;false=[];cleared_samples=[];high=[]
for item in d['contacts']:
 p=np.array(item['position']);remaining=[]
 for hit in item['hits']:
  poly=clip(list(tri[hit['triangle']]),p[1]+1e-5,True);assert len(poly)>=3;poly=clip(poly,p[1]+1.5,False);assert len(poly)>=3;prior=distance(poly,p);assert abs(prior-hit['distance'])<1e-8;exact=projected_distance(poly,p);checked+=1
  row={**hit,'exact_distance':exact,'vertices':tri[hit['triangle']].tolist()}
  if exact>=.1-1e-6:false.append({'position':p.tolist(),'occurrences':item['occurrences'],'hit':row})
  else:remaining.append(row)
 if not remaining:cleared_samples.append({'position':p.tolist(),'occurrences':item['occurrences']})
 high_hits=[h for h in remaining if h['max_height']>.3]
 if high_hits:high.append({'position':p.tolist(),'occurrences':item['occurrences'],'hits':high_hits})
atomic_json(B/'vfua-contact-distance-reference-v1.json',{'status':'RECORDED_CONTACT_REFERENCE_AUDIT','time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'original_contact_samples':len(d['contacts']),'individual_hits_checked':checked,'false_individual_hits':false,'cleared_contact_samples':cleared_samples,'remaining_high_contact_samples':high,'original_audit_sha256':digest(audit),'scene_sha256':digest(gp),'reference_sha256':digest(ROOT/'tests/landmark_diagnostics/projected_distance_reference.py'),'script_sha256':digest(__file__),'limits':'Rechecks recorded claims only; no task/profile change or new acceptance, and does not prove physical impossibility from retained contacts.'});print(checked,len(false),len(cleared_samples),len(high))
