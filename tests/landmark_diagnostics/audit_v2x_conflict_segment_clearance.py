"""Measure actual native-source contact heights on the66 V2X conflicting route segments."""
import os,sys,json,gzip,hashlib,struct,math,datetime,collections
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import digest,atomic_json
from swept_cylinder_reference import triangle_linear_sweep_distance
from cylinder_contact_height import contact_height_range
import numpy as np,psutil
usage=psutil.cpu_percent(interval=1,percpu=True);cpus=[i for i in sorted(os.sched_getaffinity(0))[:64] if i not in [1,7,15,16]];os.sched_setaffinity(0,[min(cpus,key=lambda i:usage[i])]);B=R/'outputs/landmark-connectivity';O=B/'v2x-conflict-segment-source-v1';O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});core_path=B/'V2X-grounded-fine05-supported-v1/component-conflict-cores.json';cores=json.loads(core_path.read_text());assert cores['tasks']==66;parent_path=B/'full-native-v11/manifest.json';m=json.loads(parent_path.read_text());assert digest(parent_path)==cores['parent_manifest_sha256'];tasks={t['task_key']:t for t in m['tasks']};catalog=json.loads((B/'native-source-catalog-v1/catalog.json').read_text());native=next(r for r in catalog['scenes'] if r['scene']=='V2XKFyX4ASd');assert digest(native['native_geometry_path'])==native['native_geometry_sha256'];raw=Path(native['native_geometry_path']).read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);verts=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+12*nv).reshape(nt,3);tri=verts[ix].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);cache={};regions={};rows=[]
def contacts(point):
 key=tuple(point)
 if key in cache:return cache[key]
 p=np.array(point);cell=tuple(np.floor(p/.5).astype(int))
 if cell not in regions:
  low=np.array(cell)*.5;high=low+.5;regions[cell]=np.flatnonzero((lo[:,0]<high[0]+.1)&(hi[:,0]>low[0]-.1)&(lo[:,2]<high[2]+.1)&(hi[:,2]>low[2]-.1)&(lo[:,1]<high[1]+1.5)&(hi[:,1]>low[1]+1e-5))
 result=[]
 for j in regions[cell]:
  if lo[j,0]>=p[0]+.1 or hi[j,0]<=p[0]-.1 or lo[j,2]>=p[2]+.1 or hi[j,2]<=p[2]-.1 or lo[j,1]>=p[1]+1.5 or hi[j,1]<=p[1]+1e-5:continue
  distance=triangle_linear_sweep_distance(tri[j],p,p)
  if distance>=.1-1e-6:continue
  height=contact_height_range(tri[j],p);assert height is not None;normal=np.cross(tri[j,1]-tri[j,0],tri[j,2]-tri[j,0]);norm=float(np.linalg.norm(normal));result.append({'triangle':int(j),'distance':float(distance),'minimum_height_m':height['minimum_height'],'maximum_height_m':height['maximum_height'],'maximum_point':height['maximum_point'],'triangle_area_m2':norm/2,'absolute_normal_y':float(abs(normal[1])/norm) if norm else None})
 cache[key]=result;return result
for core in cores['records']:
 key=core['task_key'];task=tasks[key];h=hashlib.sha256(key.encode()).hexdigest();rp=B/'full-native-v11'/f'shard-{int(h,16)%m["worker_count"]:02}'/(h[:24]+'.result.json');r=json.loads(rp.read_text());assert r['status']=='PASS' and r['source_record_sha256']==task['source_record_sha256'];tp=B/'full-native-v11'/r['trace_path'];assert digest(tp)==r['trace_sha256'];trace=json.load(gzip.open(tp,'rt'));assert trace['task_key']==key and trace['targets']==task['targets'];bounds={0:0,**{b['reference_index']:b['action_index'] for b in trace['reached_reference_boundaries']}};i,j=min(core['core_reference_indices']),max(core['core_reference_indices']);start,end=bounds[i],bounds[j];events=[]
 for index in range(start,end+1):
  hits=contacts(trace['positions'][index])
  if hits:events.append({'position_index':index,'position':trace['positions'][index],'contacts':hits,'maximum_height_m':max(h['maximum_height_m'] for h in hits)})
 row={'task_key':key,'source_record_sha256':task['source_record_sha256'],'core_reference_indices':core['core_reference_indices'],'action_start':start,'action_end':end,'actual_positions_checked':end-start+1,'positions_with_contact':len(events),'positions_contact_above_0point2m':sum(e['maximum_height_m']>.2 for e in events),'positions_contact_above_0point3m':sum(e['maximum_height_m']>.3 for e in events),'positions_contact_above_1m':sum(e['maximum_height_m']>1 for e in events),'maximum_actual_contact_height_m':max((e['maximum_height_m'] for e in events),default=None),'trace_sha256':r['trace_sha256'],'events':events};atomic_json(O/(key.replace(':','-')+'.json'),row);rows.append({k:v for k,v in row.items() if k!='events'});atomic_json(O/'state.json',{'status':'RUNNING','completed':len(rows),'expected':66})
assert len(rows)==66;report={'status':'COMPLETE_CONFLICT_SEGMENT_ACTUAL_SOURCE_CONTACT_DIAGNOSTIC','tasks':66,'tasks_with_contact':sum(r['positions_with_contact']>0 for r in rows),'tasks_with_contact_above_0point2m':sum(r['positions_contact_above_0point2m']>0 for r in rows),'tasks_with_contact_above_0point3m':sum(r['positions_contact_above_0point3m']>0 for r in rows),'tasks_with_contact_above_1m':sum(r['positions_contact_above_1m']>0 for r in rows),'unique_actual_positions_checked':len(cache),'records':rows,'core_receipt_sha256':digest(core_path),'native_geometry_sha256':native['native_geometry_sha256'],'script_sha256':digest(__file__),'limits':'Actual contact heights inside the original cylinder, not triangle vertex upper bounds.0.2/0.3/1m are diagnostic categories, never acceptance exemptions. Original full source failures retained; this is not proof no alternate route exists, nor permission to relax gates.'};atomic_json(O/'validation.json',report);atomic_json(O/'state.json',{'status':'COMPLETE','tasks_with_contact':report['tasks_with_contact'],'above_0point3m':report['tasks_with_contact_above_0point3m']});print({k:v for k,v in report.items() if k.startswith('tasks')})
