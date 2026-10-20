"""One sequential native geometry export per missing scene; reuse verified existing exports."""
import os,sys,json,struct,time,subprocess,datetime,fcntl,collections
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
import numpy as np
B=R/'outputs/landmark-connectivity';O=B/'native-source-catalog-v1';O.mkdir(exist_ok=False);(O/'scenes').mkdir();(O/'logs').mkdir();lock=(O/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
parent_path=B/'full-native-v11/manifest.json';parent=json.loads(parent_path.read_text());scenes=sorted({t['scene'] for t in parent['tasks']});assert len(scenes)==71 and len(parent['tasks'])==33954;screen_path=B/'full-source-geometry-v1/manifest.json';screen=json.loads(screen_path.read_text());assert screen['parent_manifest_sha256']==digest(parent_path);worker=R/'tests/landmark_diagnostics/export_native_source_catalog_scene.py';worker_sha=digest(worker);binding_receipt=B/'native-stage-trace-xc-v1/state.json';binding=json.loads(binding_receipt.read_text());assert digest(binding['binding'])==binding['binding_sha256'];originals={p:digest(p) for p in binding['originals_unchanged']};assert originals==binding['originals_unchanged'];expected={};rows=[]
for scene in scenes:
 p=B/'full-source-geometry-v1/scenes'/scene/'validation.json';d=json.loads(p.read_text());assert d['scene']==scene;expected[scene]={'scene_sha256':d['scene_sha256'],'screen_receipt_path':str(p),'screen_receipt_sha256':digest(p),'tasks':sum(t['scene']==scene for t in parent['tasks'])}
existing={sc:{'native_geometry_path':d['path'],'native_geometry_sha256':d['sha256'],'scene_sha256':d['scene_sha256'],'receipt_path':d['receipt'],'receipt_sha256':d['receipt_sha256']} for sc,d in screen['native_geometry'].items()}
for name in ['full-source-native-confirmation-17DRP-v1','full-source-native-pRbA3pwrgk9-v1']:
 p=B/name/'validation.json';d=json.loads(p.read_text());existing[d['scene']]={**d,'receipt_path':str(p),'receipt_sha256':digest(p)}
atomic_json(O/'manifest.json',{'status':'FROZEN_GEOMETRY_PROVENANCE_ONLY','scenes':expected,'global_tasks':33954,'reused_scenes':sorted(existing),'parent_manifest_sha256':digest(parent_path),'source_screen_manifest_sha256':digest(screen_path),'worker_sha256':worker_sha,'binding_receipt_sha256':digest(binding_receipt),'binding_sha256':binding['binding_sha256'],'originals':originals,'controller_sha256':digest(__file__),'resource_policy':'One exporter at a time on an actually idle GPU0..6; GPU7 formal run excluded. Two CPU threads for exporter, one for catalog checks, no external process intervention. Wait for idleGPU/free16GiB rather than oversubscribe.'})
def note(status,**extra):atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'completed_scenes':len(rows),'expected_scenes':71,'reused':sum(r['reused'] for r in rows),**extra})
def check(scene,d,reused):
 assert digest(d['receipt_path'])==d['receipt_sha256'] and d['scene_sha256']==expected[scene]['scene_sha256'];p=Path(d['native_geometry_path']).resolve();assert p.is_relative_to(B.resolve()) and digest(p)==d['native_geometry_sha256'];raw=p.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);assert nv>0 and nt>0 and len(raw)==8+12*nv+12*nt;vertices=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8);indices=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12);assert np.isfinite(vertices).all() and indices.min()>=0 and indices.max()<nv
 return {'scene':scene,'tasks':expected[scene]['tasks'],'scene_sha256':d['scene_sha256'],'native_geometry_path':str(p),'native_geometry_sha256':d['native_geometry_sha256'],'native_vertices':nv,'native_triangles':nt,'bytes':len(raw),'receipt_path':d['receipt_path'],'receipt_sha256':d['receipt_sha256'],'reused':reused}
def idle_gpu():
 data=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True);active=set(subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid','--format=csv,noheader'],text=True).splitlines());found={}
 for line in data.splitlines():
  i,u,m,util=[x.strip() for x in line.split(',')]
  if int(i)!=7 and int(m)<1024 and int(util)<10 and u not in active:found[int(i)]=True
 return next((i for i in [5,6,4,3,2,1,0] if i in found),None)
try:
 note('VALIDATING_EXISTING_NATIVE_EXPORTS')
 for scene,d in sorted(existing.items()):rows.append(check(scene,d,True))
 atomic_json(O/'catalog.partial.json',rows)
 for scene in scenes:
  if scene in existing:continue
  while True:
   disk=os.statvfs(O);gpu=idle_gpu()
   if gpu is not None and disk.f_bavail*disk.f_frsize>=16*2**30:break
   note('WAITING_FOR_IDLE_GPU_AND_DISK',next_scene=scene);time.sleep(30)
  assert digest(worker)==worker_sha and digest(binding['binding'])==binding['binding_sha256'];note('EXPORTING_NATIVE_SCENE',scene=scene,gpu=gpu)
  with (O/'logs'/(scene+'.log')).open('xb') as log:
   proc=subprocess.Popen([sys.executable,'-B',str(worker),'--scene',scene,'--gpu',str(gpu)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'});atomic_json(O/'current-worker.json',{'pid':proc.pid,'start_ticks':Path('/proc',str(proc.pid),'stat').read_text().rsplit(')',1)[1].split()[19],'scene':scene,'gpu':gpu});code=proc.wait()
  assert code==0,('Exporter failed',scene,code)
  p=O/'scenes'/scene/'validation.json';d=json.loads(p.read_text());assert d['scene']==scene and d['parent_manifest_sha256']==digest(parent_path) and d['binding_sha256']==binding['binding_sha256'] and d['script_sha256']==worker_sha;d.update(receipt_path=str(p),receipt_sha256=digest(p));rows.append(check(scene,d,False));atomic_json(O/'catalog.partial.json',rows);note('SCENE_EXPORT_VALIDATED',last_scene=scene)
 assert {r['scene'] for r in rows}==set(scenes) and len(rows)==71 and sum(r['tasks'] for r in rows)==33954;assert {p:digest(p) for p in originals}==originals;assert digest(parent_path)==screen['parent_manifest_sha256'];atomic_json(O/'catalog.json',{'scenes':rows});atomic_json(O/'validation.json',{'status':'COMPLETE_NATIVE_GEOMETRY_CATALOG_NOT_NAVIGATION_ACCEPTANCE','scenes':71,'global_tasks':33954,'reused_scenes':sum(r['reused'] for r in rows),'new_exports':sum(not r['reused'] for r in rows),'geometry_bytes':sum(r['bytes'] for r in rows),'catalog_sha256':digest(O/'catalog.json'),'manifest_sha256':digest(O/'manifest.json'),'original_build_inputs_unchanged':True,'limits':'Native loader input provenance and finite indexed triangle structure only. No source-motion PASS, navmesh adoption, model score or publication approval.'});note('COMPLETE_NATIVE_GEOMETRY_CATALOG_NOT_NAVIGATION_ACCEPTANCE')
except Exception as e:note('FAILED',error=repr(e));raise
