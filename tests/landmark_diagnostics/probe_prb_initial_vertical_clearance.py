"""Analytic fixed-XZ upward clearance diagnosis; no navmesh or target mutation."""
import os,sys,json,math,datetime,struct,collections
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import digest,atomic_json
from cylinder_contact_height import contact_height_range
from projected_distance_reference import projected_distance
from swept_cylinder_reference import triangle_linear_sweep_distance
import numpy as np,psutil
u=psutil.cpu_percent(interval=1,percpu=True);pool=[i for i in sorted(os.sched_getaffinity(0))[:64] if i not in [6,7,20,25]];cpu=min(pool,key=lambda i:u[i]);os.sched_setaffinity(0,[cpu])
B=R/'outputs/landmark-connectivity';O=B/'prb-initial-vertical-clearance-v1';O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':cpu})
def candidate_height(y,intervals,limit=.5):
 value=y
 for low,high in sorted(intervals):
  if high<value:continue
  if low>value:break
  value=high+1e-8
 return value if value-y<=limit else None
assert candidate_height(0,[(-1,.01),(.5,1)])==.01000001
assert candidate_height(0,[(-1,.01),(.005,.02)])==.02000001
assert candidate_height(0,[(-1,1)]) is None
assert candidate_height(0,[(.1,.2)])==0
source=B/'full-source-guard-pRbA3pwrgk9-v1/guarded/validation.json';validation=json.loads(source.read_text());selected=[r for r in validation['results'] if r.get('error')=="AssertionError('source_body_initial_collision')"];assert len(selected)==96
geometry=B/'full-source-native-pRbA3pwrgk9-v1/validation.json';g=json.loads(geometry.read_text());assert g['scene']=='pRbA3pwrgk9' and digest(g['native_geometry_path'])==g['native_geometry_sha256'];raw=Path(g['native_geometry_path']).read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);v=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=v[ix].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);ybase=float(lo[:,1].min()-1);yheight=float(hi[:,1].max()-ybase+1)
cache={};rows=[]
for row in selected:
 rp=Path(row['result_path']);assert digest(rp)==row['sha256'];d=json.loads(rp.read_text());p=np.array(d['positions'][0],float);key=tuple(p)
 if key not in cache:
  spatial=np.flatnonzero((lo[:,0]<p[0]+.1)&(hi[:,0]>p[0]-.1)&(lo[:,2]<p[2]+.1)&(hi[:,2]>p[2]-.1));intervals=[];initial=[];witnesses=[]
  for j in spatial:
   if triangle_linear_sweep_distance(tri[j],p,p)<.1-1e-6:initial.append(int(j))
   if projected_distance(list(tri[j]),p)>=.1-1e-6:continue
   q=contact_height_range(tri[j],[p[0],ybase,p[2]],height=yheight,foot_epsilon=0)
   assert q is not None,('missing analytic witness',int(j))
   low=q['minimum_point'][1]-1.5;high=q['maximum_point'][1]-1e-5;intervals.append((low,high));witnesses.append({'triangle':int(j),'low':low,'high':high})
  assert initial
  y=candidate_height(p[1],intervals);candidate=None if y is None else [float(p[0]),float(y),float(p[2])];contacts=[] if candidate is None else [int(j) for j in spatial if triangle_linear_sweep_distance(tri[j],candidate,candidate)<.1-1e-6]
  assert not contacts,('independent zero-sweep contradiction',contacts)
  cache[key]={'original_position':p.tolist(),'candidate':candidate,'upward_shift_m':None if y is None else y-p[1],'initial_contact_triangles':initial,'forbidden_intervals':witnesses,'candidate_zero_sweep_contacts':contacts,'status':'SOURCE_CLEAR_FIXED_XZ_HEIGHT_EXISTS' if candidate else 'NO_FIXED_XZ_CLEARANCE_WITHIN_HALF_METRE'}
 rows.append({'task_key':row['task_key'],'source_record_sha256':d['source_record_sha256'],'source_result_sha256':row['sha256'],**cache[key]});atomic_json(O/'state.json',{'status':'RUNNING','records':len(rows),'unique_positions':len(cache)})
counts=dict(collections.Counter(r['status'] for r in rows));shifts=[r['upward_shift_m'] for r in rows if r['candidate'] is not None];atomic_json(O/'validation.json',{'status':'COMPLETE_ANALYTIC_CLEARANCE_DIAGNOSTIC_NOT_NAVIGATION_ACCEPTANCE','expected':96,'unique_positions':len(cache),'counts':counts,'shift_min_m':min(shifts) if shifts else None,'shift_max_m':max(shifts) if shifts else None,'within_2cm':sum(x<=.02 for x in shifts),'records':rows,'source_validation_sha256':digest(source),'native_geometry_receipt_sha256':digest(geometry),'script_sha256':digest(__file__),'helpers':{str(R/'tests/landmark_diagnostics'/n):digest(R/'tests/landmark_diagnostics'/n) for n in ['cylinder_contact_height.py','projected_distance_reference.py','swept_cylinder_reference.py']},'limits':'Fixed-XZ upward clearance <=0.5m is a diagnostic domain only, not authorization to move targets. Candidate is not on existing navmesh by construction; source-anchor bounds, support/semantic validity, topology, full trajectories and real movement still required. Original failures, targets, geometry and profiles unchanged.'});atomic_json(O/'state.json',{'status':'COMPLETE','counts':counts});print(counts)
