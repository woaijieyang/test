"""Native input confirmation of actual-position source alerts from the first complete scene."""
import os,sys,json,struct,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(15);os.environ['CUDA_VISIBLE_DEVICES']=''
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from projected_distance_reference import projected_distance
from swept_cylinder_reference import triangle_linear_sweep_distance
import numpy as np,psutil
u=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:u[i])])
B=R/'outputs/landmark-connectivity';D=B/'full-source-native-confirmation-17DRP-v1';receipt=json.loads((D/'validation.json').read_text());p=B/'full-source-geometry-v1/scenes/17DRP5sb8fy/validation.json';x=json.loads(p.read_text());assert x['scene_sha256']==receipt['scene_sha256'];gp=Path(receipt['native_geometry_path']);assert digest(gp)==receipt['native_geometry_sha256'];raw=gp.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);v=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=v[ix].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);points={}
for row in x['rows']:
 for c in row['contact_examples']:
  if c['kind']=='ACTUAL_POSITION':points.setdefault(tuple(c['position']),[]).append({'task_key':row['task_key'],'position_index':c['position_index'],'parser_witness':c})
rows=[]
for key,occ in points.items():
 q=np.array(key);ids=np.flatnonzero((lo[:,0]<q[0]+.1)&(hi[:,0]>q[0]-.1)&(lo[:,2]<q[2]+.1)&(hi[:,2]>q[2]-.1)&(lo[:,1]<q[1]+1.5)&(hi[:,1]>q[1]+1e-5));hits=[]
 for j in ids:
  distance=triangle_linear_sweep_distance(tri[j],q,q)
  if distance<.1-1e-6:hits.append({'native_triangle':int(j),'distance':distance,'radial_penetration':.1-distance,'vertices':tri[j].tolist()})
 rows.append({'position':list(key),'occurrences':occ,'native_hits':hits,'confirmed':bool(hits)})
confirmed={o['task_key'] for row in rows if row['confirmed'] for o in row['occurrences']};allkeys={o['task_key'] for row in rows for o in row['occurrences']};atomic_json(D/'actual-position-confirmation.json',{'status':'COMPLETE_NATIVE_SOURCE_ALERT_CONFIRMATION_NOT_ACCEPTANCE','unique_actual_positions_checked':len(rows),'positions_confirmed':sum(r['confirmed'] for r in rows),'task_keys_with_recorded_actual_alerts':sorted(allkeys),'task_keys_with_native_confirmed_actual_alerts':sorted(confirmed),'rows':rows,'screen_sha256':digest(p),'native_geometry_receipt_sha256':digest(D/'validation.json'),'script_sha256':digest(__file__),'sweep_helper_sha256':digest(R/'tests/landmark_diagnostics/swept_cylinder_reference.py'),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Confirms recorded actual-position examples only, not all source samples or whole tasks. No reconstruction claim for unknown original navmesh parameters. Same native scene geometry, body1.5/0.1 and radial threshold0.099999; no policy, mesh or criteria changed.'});print('unique',len(rows),'confirmed',sum(r['confirmed'] for r in rows),'tasks',len(allkeys),len(confirmed),'max_penetration',max((h['radial_penetration'] for r in rows for h in r['native_hits']),default=0))
