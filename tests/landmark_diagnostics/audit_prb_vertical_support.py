"""Check source support witnesses for fixed-XZ clearance diagnoses, not navigation."""
import os,sys,json,struct,math,collections
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from cylinder_contact_height import contact_height_range
import numpy as np
B=R/'outputs/landmark-connectivity';source=B/'prb-initial-vertical-clearance-v3/validation.json';report=json.loads(source.read_text());gp=B/'full-source-native-pRbA3pwrgk9-v1/validation.json';g=json.loads(gp.read_text());assert digest(gp)==report['native_geometry_receipt_sha256'] and digest(g['native_geometry_path'])==g['native_geometry_sha256'];raw=Path(g['native_geometry_path']).read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);v=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=v[ix].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);cache={};rows=[]
for row in report['records']:
 q=np.array(row['candidate']);key=tuple(q)
 if key not in cache:
  top=[r for r in row['forbidden_intervals'] if abs(r['high']+1e-8-q[1])<1e-9];assert top;witnesses=[]
  for r in top:
   j=r['triangle'];t=tri[j];normal=np.cross(t[1]-t[0],t[2]-t[0]);cosine=abs(normal[1])/np.linalg.norm(normal);ref=[q[0],float(t[:,1].min()-1),q[2]];height=float(t[:,1].max()-ref[1]+1);h=contact_height_range(t,ref,height=height,foot_epsilon=0);assert h is not None;p=h['maximum_point'];witnesses.append({'triangle':j,'point':p,'horizontal_distance_m':math.hypot(p[0]-q[0],p[2]-q[2]),'height_above_foot_m':p[1]-q[1],'absolute_normal_y':float(cosine),'within_45_degree_support_slope':bool(cosine>=math.cos(math.pi/4))})
  center=[];inds=np.flatnonzero((lo[:,0]<=q[0])&(hi[:,0]>=q[0])&(lo[:,2]<=q[2])&(hi[:,2]>=q[2])&(lo[:,1]<=q[1]+1e-5))
  for j in inds:
   t=tri[j];A=np.stack([(t[1]-t[0])[[0,2]],(t[2]-t[0])[[0,2]]],axis=1)
   if abs(np.linalg.det(A))<1e-14:continue
   u,w=np.linalg.solve(A,q[[0,2]]-t[0,[0,2]])
   if min(u,w)<-1e-10 or u+w>1+1e-10:continue
   y=t[0,1]+u*(t[1,1]-t[0,1])+w*(t[2,1]-t[0,1])
   if y<=q[1]+1e-5:center.append((float(q[1]-y),int(j)))
  nearest=min(center) if center else None;cache[key]={'candidate':q.tolist(),'support_witnesses':witnesses,'has_slope_compatible_footprint_witness':any(r['within_45_degree_support_slope'] for r in witnesses),'center_support_gap_m':nearest[0] if nearest else None,'center_support_triangle':nearest[1] if nearest else None}
 rows.append({'task_key':row['task_key'],**cache[key]})
output=source.parent/'support-witness-audit.json';assert not output.exists();atomic_json(output,{'status':'COMPLETE_SOURCE_SUPPORT_WITNESS_DIAGNOSTIC_NOT_NAVIGATION','tasks':len(rows),'unique_candidates':len(cache),'slope_compatible_tasks':sum(r['has_slope_compatible_footprint_witness'] for r in rows),'max_center_support_gap_m':max(r['center_support_gap_m'] for r in rows if r['center_support_gap_m'] is not None),'records':rows,'source_sha256':digest(source),'native_geometry_sha256':g['native_geometry_sha256'],'script_sha256':digest(__file__),'limits':'Footprint point support and center ray are diagnostics, not stability/physical dynamics or native mesh membership. No mesh/target changes, and no fullscene/motion acceptance.'});print('support',len(rows),sum(r['has_slope_compatible_footprint_witness'] for r in rows))
