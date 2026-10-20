"""Exact straight swept-cylinder audit of frozen v11 traces against native source geometry.
No task is rerun; this preserves the baseline traces, all static records and all failures.
"""
import os,sys,json,math,hashlib,gzip,struct,argparse,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
P=argparse.ArgumentParser();P.add_argument('--scene',required=True);P.add_argument('--cpu',type=int,required=True);args=P.parse_args();os.sched_setaffinity(0,[args.cpu])
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
import numpy as np
B=R/'outputs/landmark-connectivity';O=B/'full-native-source-exact-v1';manifest=json.loads((O/'manifest.json').read_text());assert digest(__file__)==manifest['worker_sha256'];assert digest(R/'tests/landmark_diagnostics/swept_cylinder_reference.py')==manifest['sweep_sha256'] and digest(R/'tests/landmark_diagnostics/projected_distance_reference.py')==manifest['distance_sha256'];run=B/'full-native-v11';assert digest(run/'manifest.json')==manifest['parent_manifest_sha256'];parent=json.loads((run/'manifest.json').read_text());tasks=[t for t in parent['tasks'] if t['scene']==args.scene];assert tasks;assert digest(parent['profile_path'])==parent['profile_sha256'];profile=json.loads(Path(parent['profile_path']).read_text());asset=profile['assets'][f'mp3d/{args.scene}/{args.scene}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256']
D=O/'scenes'/args.scene;D.mkdir(exist_ok=False);atomic_json(D/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':args.cpu})
try:
 native=manifest['native_geometry'][args.scene];gp=R/f'data/scene_datasets/mp3d/{args.scene}/{args.scene}.glb';assert digest(gp)==native['scene_sha256'];assert digest(native['native_geometry_path'])==native['native_geometry_sha256'];raw=Path(native['native_geometry_path']).read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);assert len(raw)==8+12*nv+12*nt;vertices=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+12*nv).reshape(nt,3);tri=vertices[ix].astype(float);assert np.isfinite(tri).all();lo=tri.min(axis=1);hi=tri.max(axis=1);regions={};cache={};queries=0;clears=0
 oldpath=B/'full-source-geometry-v1/scenes'/args.scene/'validation.json';assert digest(oldpath)==manifest['old_screen_receipts'][args.scene]['sha256'];old=json.loads(oldpath.read_text());oldrows={r['task_key']:r for r in old['rows']};assert set(oldrows)=={t['task_key'] for t in tasks}
 def contact(a,b):
  global queries,clears
  key=(tuple(float(x) for x in a),tuple(float(x) for x in b))
  if key in cache:return cache[key]
  if len(cache)>=500000:cache.clear();clears+=1
  queries+=1;lower=np.minimum(a,b);upper=np.maximum(a,b);c0=tuple(np.floor(lower/.5).astype(int));c1=tuple(np.floor(upper/.5).astype(int));rk=(c0,c1)
  if rk not in regions:
   l=np.array(c0)*.5;h=(np.array(c1)+1)*.5;regions[rk]=np.flatnonzero((lo[:,0]<h[0]+.1)&(hi[:,0]>l[0]-.1)&(lo[:,2]<h[2]+.1)&(hi[:,2]>l[2]-.1)&(lo[:,1]<h[1]+1.5)&(hi[:,1]>l[1]+1e-5))
  hit=None
  for j in regions[rk]:
   if lo[j,0]>=upper[0]+.1 or hi[j,0]<=lower[0]-.1 or lo[j,2]>=upper[2]+.1 or hi[j,2]<=lower[2]-.1 or lo[j,1]>=upper[1]+1.5 or hi[j,1]<=lower[1]+1e-5:continue
   distance=triangle_linear_sweep_distance(tri[j],a,b)
   if distance<.1-1e-6:hit={'native_triangle':int(j),'distance':float(distance)};break
  cache[key]=hit;return hit
 rows=[]
 for task in tasks:
  key=task['task_key'];h=hashlib.sha256(key.encode()).hexdigest();rp=run/f'shard-{int(h,16)%parent["worker_count"]:02}'/(h[:24]+'.result.json');result=json.loads(rp.read_text());assert result['task_key']==key and result['source_record_sha256']==task['source_record_sha256'];row={'task_key':key,'source_record_sha256':task['source_record_sha256'],'native_status':result['status'],'result_path':str(rp),'result_sha256':digest(rp),'actions':0,'actual_position_contacts':0,'continuous_segment_contacts':0,'contact_examples':[],'old_sampled_status':oldrows[key]['status'],'old_geometry_kind':old['geometry_kind']}
  if task['status']=='STATIC_BLOCKED_PRESERVED':assert result['status']=='STATIC_BLOCKED_PRESERVED';row['status']='STATIC_BLOCKED_PRESERVED'
  else:
   assert result['status']=='PASS' and result['manifest_sha256']==manifest['parent_manifest_sha256'];tp=(run/result['trace_path']).resolve();assert tp.is_relative_to(run.resolve()) and digest(tp)==result['trace_sha256'];trace=json.load(gzip.open(tp,'rt'));assert trace['task_key']==key and trace['manifest_sha256']==manifest['parent_manifest_sha256'] and trace['mesh_sha256']==asset['navmesh_sha256'] and trace['targets']==task['targets'];pos=np.asarray(trace['positions']);assert len(pos)==len(trace['actions'])+1 and np.isfinite(pos).all();row.update(trace_path=str(tp),trace_sha256=result['trace_sha256'],actions=len(trace['actions']),positions_checked=len(pos));hits=[]
   for i,p in enumerate(pos):
    hit=contact(p,p);hits.append(hit)
    if hit:
     row['actual_position_contacts']+=1
     if len(row['contact_examples'])<24:row['contact_examples'].append({'kind':'ACTUAL_POSITION','position_index':i,'position':p.tolist(),**hit})
   for i,(a,b) in enumerate(zip(pos,pos[1:])):
    hit=hits[i] or hits[i+1];kind='ENDPOINT_CONTACT_WITNESS'
    if hit is None:hit=contact(a,b);kind='EXACT_CONTINUOUS_INTERIOR'
    if hit:
     row['continuous_segment_contacts']+=1
     if len(row['contact_examples'])<24:row['contact_examples'].append({'kind':kind,'action_index':i+1,'start':a.tolist(),'end':b.tolist(),**hit})
   row['status']='ACTUAL_POSITION_SOURCE_CONTACT' if row['actual_position_contacts'] else 'CONTINUOUS_INTERIOR_SOURCE_CONTACT' if row['continuous_segment_contacts'] else 'EXACT_LINEAR_SOURCE_CLEAR';row['examples_truncated']=row['actual_position_contacts']+row['continuous_segment_contacts']>len(row['contact_examples'])
  rows.append(row)
  if len(rows)%10==0:atomic_json(D/'state.json',{'status':'RUNNING','completed':len(rows),'expected':len(tasks),'queries':queries})
 assert digest(gp)==native['scene_sha256'];atomic_json(D/'validation.json',{'status':'COMPLETE_NATIVE_EXACT_TRACE_GEOMETRY_AUDIT_NOT_ACCEPTANCE','scene':args.scene,'scene_sha256':native['scene_sha256'],'native_geometry_sha256':native['native_geometry_sha256'],'expected_tasks':len(tasks),'rows':rows,'exact_geometry_queries':queries,'cache_clears':clears,'manifest_sha256':digest(O/'manifest.json'),'worker_sha256':digest(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Exact straight swept-cylinder interpretation of immutable originalv11 native traces, not newly executed navigation or observed engine internal curves. Existing alternate repaired traces/proofs are separate and not overwritten. All static failures retained; no publication or source_geometry_acceptance.'});atomic_json(D/'state.json',{'status':'COMPLETE','completed':len(rows)})
except Exception as e:atomic_json(D/'state.json',{'status':'FAILED','error':repr(e)});raise
