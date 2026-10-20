"""Reclassify recorded native-confirmed contacts by height actually inside the cylinder."""
import os,sys,json,datetime,collections,struct
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from cylinder_contact_height import contact_height_range
import numpy as np,psutil
u=psutil.cpu_percent(interval=1,percpu=True);free=[i for i in sorted(os.sched_getaffinity(0))[:64] if i not in [6,10,11,12,13,15,18,20,22,24,27,30]];os.sched_setaffinity(0,[min(free,key=lambda i:u[i])])
B=R/'outputs/landmark-connectivity';O=B/'native-contact-height-classification-v1';O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});source=B/'full-source-native-pRbA3pwrgk9-v1/actual-position-confirmation.json';v=json.loads(source.read_text());rows=[];issues=[];bins=collections.Counter();taskbins=collections.defaultdict(set);overestimates=[]
def checked_range(tri,p):
 result=contact_height_range(tri,p)
 if result is None:raise ValueError('Confirmed collision has no height intersection')
 tri=np.array(tri,float);p=np.array(p)
 for key in ['minimum_point','maximum_point']:
  q=np.array(result[key]);uv,*_=np.linalg.lstsq(np.column_stack((tri[1]-tri[0],tri[2]-tri[0])),q-tri[0],rcond=None);err=np.linalg.norm(tri[0]+uv[0]*(tri[1]-tri[0])+uv[1]*(tri[2]-tri[0])-q);assert err<1e-7 and min(uv)>=-1e-7 and sum(uv)<=1+1e-7 and np.linalg.norm((q-p)[[0,2]])<=.1-1e-6+1e-8
 return result
for n,record in enumerate(v['rows']):
 exact=[];errors=[]
 for h in record['native_hits']:
  try:exact.append({'native_triangle':h['native_triangle'],**checked_range(h['vertices'],record['position'])})
  except Exception as e:errors.append({'native_triangle':h['native_triangle'],'error':repr(e)})
 if errors:category='HEIGHT_CLASSIFICATION_INCONCLUSIVE';issues.append({'position':record['position'],'errors':errors});high=None;old=None
 else:
  high=max(x['maximum_height'] for x in exact);old=max(x['clipped_triangle_maximum_height'] for x in exact);category='LOW_LE_002M' if high<=.02 else 'STEP_BAND_002_TO_03M' if high<=.3 else 'UPPER_GT_03M';overestimates.append(old-high)
 keys=sorted({o['task_key'] for o in record['occurrences']});bins[category]+=1
 for k in keys:taskbins[k].add(category)
 rows.append({'position':record['position'],'task_keys':keys,'category':category,'maximum_height_inside_cylinder':high,'clipped_triangle_height_upper_bound':old,'contacts':exact,'errors':errors})
 if n%250==0:atomic_json(O/'state.json',{'status':'RUNNING','positions':n+1,'total':len(v['rows']),'classification_issues':len(issues)})
# Revisit the separate anchor used for the5.409mm candidate, without modifying its evidence or asset.
gap_path=B/'pRb-ground-height-gap-v1/validation.json';gap=json.loads(gap_path.read_text());geo=json.loads((B/'full-source-native-pRbA3pwrgk9-v1/validation.json').read_text());raw=Path(geo['native_geometry_path']).read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);vertices=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);anchor=[]
for h in gap['original_contacts']:anchor.append({'native_triangle':h['triangle'],**checked_range(vertices[ix[h['triangle']]],gap['original_snap'])})
anchor_summary={'actual_maximum_contact_height':max(x['maximum_height'] for x in anchor),'prior_triangle_upper_bound':gap['maximum_original_contact_height'],'candidate_lift_m':gap['lift_m'],'existing_candidate_geometry_still_unmodified':True,'contacts':anchor}
atomic_json(O/'validation.json',{'status':'COMPLETE_HEIGHT_CLASSIFICATION_WITH_REVIEW_ITEMS' if issues else 'COMPLETE_NATIVE_HEIGHT_CLASSIFICATION','recorded_positions':len(rows),'unique_tasks':len(taskbins),'position_categories':dict(bins),'task_category_memberships':{k:sorted(x) for k,x in taskbins.items()},'triangle_height_overestimate_max_m':max(overestimates,default=0),'positions_with_height_upper_bound_overestimate_gt_1mm':sum(x>.001 for x in overestimates),'issues':issues,'rows':rows,'ground_plane_anchor_recheck':anchor_summary,'source_confirmation_sha256':digest(source),'ground_gap_receipt_sha256':digest(gap_path),'height_helper_sha256':digest(R/'tests/landmark_diagnostics/cylinder_contact_height.py'),'script_sha256':digest(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Severity only: all4957 recorded native collision existence flags remain unchanged. Closed-radius contact-height supremum, not a new collision tolerance. Bounds, task status, actual traces and current runs unchanged. Recorded examples do not represent every point of every trajectory.'});atomic_json(O/'state.json',{'status':'COMPLETE','position_categories':dict(bins),'issues':len(issues)});print(dict(bins),'issues',len(issues),'anchor', {k:v for k,v in anchor_summary.items() if k!='contacts'})
