"""Full frozen trace source-cylinder screen. No task is retried or accepted by this audit."""
import os,sys,json,math,hashlib,gzip,struct,argparse,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
p=argparse.ArgumentParser();p.add_argument('--scene',required=True);p.add_argument('--cpu',type=int,required=True);args=p.parse_args();os.sched_setaffinity(0,[args.cpu])
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics'),str(R/'.cache/geometry-tools')]
from workspace import atomic_json,digest
from projected_distance_reference import projected_distance
import numpy as np,trimesh
B=R/'outputs/landmark-connectivity';O=B/'full-source-geometry-v1';manifest=json.loads((O/'manifest.json').read_text());assert digest(__file__)==manifest['worker_sha256'];assert digest(R/'tests/landmark_diagnostics/projected_distance_reference.py')==manifest['distance_sha256'];run=B/'full-native-v11';assert digest(run/'manifest.json')==manifest['parent_manifest_sha256'];m=json.loads((run/'manifest.json').read_text());assert digest(m['profile_path'])==m['profile_sha256'];profile=json.loads(Path(m['profile_path']).read_text());scene=args.scene;tasks=[t for t in m['tasks'] if t['scene']==scene];assert tasks
D=O/'scenes'/scene;D.mkdir(exist_ok=False);atomic_json(D/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':args.cpu})
try:
 gp=R/f'data/scene_datasets/mp3d/{scene}/{scene}.glb';scene_sha=digest(gp);native=manifest['native_geometry'].get(scene)
 if native:
  assert scene_sha==native['scene_sha256']
  gpath=Path(native['path']);assert digest(gpath)==native['sha256'];raw=gpath.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);assert len(raw)==8+nv*12+nt*12;verts=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=verts[ix].astype(float);geometry_kind='NATIVE_LOADER_EXPORTED_TRIANGLES'
 else:
  mesh=trimesh.load(str(gp),force='scene',process=False).to_geometry();mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float));tri=np.asarray(mesh.triangles);geometry_kind='GLB_SOURCE_EXACT_AXIS_TRANSFORM_NATIVE_CONFIRMATION_PENDING'
 assert np.isfinite(tri).all();lo=tri.min(axis=1);hi=tri.max(axis=1);regions={};cache={};pose_queries=0
 def clip(poly,y,above):
  out=[]
  for a,b in zip(poly,poly[1:]+poly[:1]):
   ia=a[1]>=y if above else a[1]<=y;ib=b[1]>=y if above else b[1]<=y
   if ia:out.append(a)
   if ia!=ib:out.append(a+(y-a[1])/(b[1]-a[1])*(b-a))
  return out
 def contact(p):
  global pose_queries
  key=tuple(float(x) for x in p)
  if key in cache:return cache[key]
  if len(cache)>=500000:cache.clear()
  pose_queries+=1;p=np.array(p);cell=tuple(math.floor(float(v)/.5) for v in p)
  if cell not in regions:
   low=np.array(cell)*.5;high=low+.5;regions[cell]=np.flatnonzero((lo[:,0]<high[0]+.1)&(hi[:,0]>low[0]-.1)&(lo[:,2]<high[2]+.1)&(hi[:,2]>low[2]-.1)&(lo[:,1]<high[1]+1.5)&(hi[:,1]>low[1]))
  hit=None
  for j in regions[cell]:
   if lo[j,0]>=p[0]+.1 or hi[j,0]<=p[0]-.1 or lo[j,2]>=p[2]+.1 or hi[j,2]<=p[2]-.1 or lo[j,1]>=p[1]+1.5 or hi[j,1]<=p[1]+1e-5:continue
   poly=clip(list(tri[j]),p[1]+1e-5,True)
   if len(poly)<3:continue
   poly=clip(poly,p[1]+1.5,False)
   if len(poly)>=3:
    d=projected_distance(poly,p)
    if d<.1-1e-6:hit={'triangle':int(j),'distance':d,'max_height':float(max(v[1] for v in poly)-p[1])};break
  cache[key]=hit;return hit
 rows=[];asset=profile['assets'][f'mp3d/{scene}/{scene}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256']
 for task in tasks:
  key=task['task_key'];h=hashlib.sha256(key.encode()).hexdigest();rp=run/f'shard-{int(h,16)%m["worker_count"]:02}'/(h[:24]+'.result.json');result=json.loads(rp.read_text());assert result['task_key']==key and result['source_record_sha256']==task['source_record_sha256'];row={'task_key':key,'source_record_sha256':task['source_record_sha256'],'native_status':result['status'],'result_path':str(rp),'result_sha256':digest(rp),'actions':0,'actual_position_contacts':0,'interior_samples':0,'interior_contacts':0,'contact_examples':[]}
  if task['status']=='STATIC_BLOCKED_PRESERVED':assert result['status']=='STATIC_BLOCKED_PRESERVED';row['status']='STATIC_BLOCKED_PRESERVED'
  else:
   assert result['status']=='PASS' and result['manifest_sha256']==manifest['parent_manifest_sha256'];tp=run/result['trace_path'];assert tp.resolve().is_relative_to(run.resolve()) and digest(tp)==result['trace_sha256'];trace=json.load(gzip.open(tp,'rt'));assert trace['task_key']==key and trace['manifest_sha256']==manifest['parent_manifest_sha256'] and trace['mesh_sha256']==asset['navmesh_sha256'] and trace['targets']==task['targets'];pos=np.asarray(trace['positions']);assert len(pos)==len(trace['actions'])+1 and np.isfinite(pos).all();row['trace_sha256']=result['trace_sha256'];row['trace_path']=str(tp);row['actions']=len(trace['actions']);row['positions_checked']=len(pos)
   for i,q in enumerate(pos):
    hit=contact(q)
    if hit:
     row['actual_position_contacts']+=1
     if len(row['contact_examples'])<24:row['contact_examples'].append({'kind':'ACTUAL_POSITION','position_index':i,'position':q.tolist(),**hit})
   for i,(a,b) in enumerate(zip(pos,pos[1:])):
    steps=max(1,math.ceil(float(np.linalg.norm(b-a))/.05))
    for j in range(1,steps):
     q=a+(b-a)*j/steps;hit=contact(q);row['interior_samples']+=1
     if hit:
      row['interior_contacts']+=1
      if len(row['contact_examples'])<24:row['contact_examples'].append({'kind':'LINEAR_INTERIOR','action_index':i+1,'fraction':j/steps,'position':q.tolist(),**hit})
   row['status']='CONTACT_REQUIRES_REVIEW' if row['actual_position_contacts'] or row['interior_contacts'] else 'NO_CONTACT_AT_CHECKED_SAMPLES';row['examples_truncated']=row['actual_position_contacts']+row['interior_contacts']>len(row['contact_examples'])
  rows.append(row)
  if len(rows)%10==0:atomic_json(D/'state.json',{'status':'RUNNING','completed':len(rows),'expected':len(tasks),'geometry_kind':geometry_kind,'computed_pose_queries':pose_queries})
 assert digest(gp)==scene_sha
 atomic_json(D/'validation.json',{'status':'COMPLETE_SCENE_SCREEN_NOT_ACCEPTANCE','scene':scene,'geometry_kind':geometry_kind,'scene_sha256':scene_sha,'native_geometry':native,'expected_tasks':len(tasks),'rows':rows,'computed_pose_queries':pose_queries,'manifest_sha256':digest(O/'manifest.json'),'worker_sha256':digest(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'All original native PASS traces and static rows retained. Actual pose and <=0.05m straight-interior samples classified separately. No-contact samples do not prove continuous sweep, and GLB-parser cases require native geometry confirmation. No task rerun, accepted-count change or publishing.'});atomic_json(D/'state.json',{'status':'COMPLETE','completed':len(rows),'contact_tasks':sum(r['status']=='CONTACT_REQUIRES_REVIEW' for r in rows),'sample_clear_tasks':sum(r['status']=='NO_CONTACT_AT_CHECKED_SAMPLES' for r in rows),'static_preserved':sum(r['status']=='STATIC_BLOCKED_PRESERVED' for r in rows)})
except Exception as e:atomic_json(D/'state.json',{'status':'FAILED','error':repr(e)});raise
