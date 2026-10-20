"""Four-CPU finite offline audit controller; never touches native/model workers or resumes failures."""
import os,sys,json,time,datetime,subprocess,collections,shutil
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'));from workspace import atomic_json,digest
import psutil
B=R/'outputs/landmark-connectivity';O=B/'full-source-geometry-v1';O.mkdir(exist_ok=False);(O/'scenes').mkdir();worker=R/'tests/landmark_diagnostics/audit_full_landmark_source_geometry.py';parent=B/'full-native-v11/manifest.json';m=json.loads(parent.read_text());validated=json.loads((B/'full-native-v11/validation.json').read_text());assert validated['coverage_complete'] and not validated['audit_issues'] and validated['manifest_sha256']==digest(parent);assert len(m['tasks'])==33954 and len({t['task_key'] for t in m['tasks']})==33954
u=psutil.cpu_percent(interval=2,percpu=True);eligible=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<20];cpus=sorted(eligible,key=lambda i:u[i])[:4];assert cpus,'No idle CPU';assert psutil.virtual_memory().available>12*1024**3 and shutil.disk_usage(R).free>10*1024**3;os.sched_setaffinity(0,[cpus[0]])
native={}
for scene,rel,key in [('XcA2TqTSSAj','native-stage-trace-xc-v3','native_triangle_dump_sha256'),('mJXqzFtmKg4','step-envelope-native-geometry-v1','native_geometry_sha256'),('VFuaQ6m2Qom','vfua-native-geometry-v1','native_geometry_sha256')]:
 receipt=B/rel/'validation.json';v=json.loads(receipt.read_text());gp=B/rel/'native-1.bin';assert digest(gp)==v[key];native[scene]={'path':str(gp),'sha256':digest(gp),'scene_sha256':v['scene_sha256'],'receipt':str(receipt),'receipt_sha256':digest(receipt)}
scenes=sorted({t['scene'] for t in m['tasks']});manifest={'status':'FROZEN_OFFLINE_SOURCE_SCREEN','global_tasks':33954,'native_parent_counts':validated['counts'],'scenes':scenes,'parent_manifest_sha256':digest(parent),'parent_validation_sha256':digest(B/'full-native-v11/validation.json'),'profile_sha256':m['profile_sha256'],'worker_sha256':digest(worker),'controller_sha256':digest(__file__),'distance_sha256':digest(R/'tests/landmark_diagnostics/projected_distance_reference.py'),'native_geometry':native,'cpus':cpus,'cpu_utilization_before':{str(i):u[i] for i in cpus},'gpu_requested':False,'settings':{'height':1.5,'radius':.1,'foot_epsilon':1e-5,'radial_threshold':.1-1e-6,'interpolation_max_spacing':.05,'deduplication':'exact float tuple; no rounding'},'limits':'Diagnostic coverage screen, not formal model evaluation or acceptance.68 scenes use GLB-source parser unless a native export is recorded; native geometry confirmation remains mandatory before adopting repairs. No completed task rerun, raw annotation change, or geometry modification.'};atomic_json(O/'manifest.json',manifest);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
queue=list(scenes);active={};completed=[];failures=[]
while queue or active:
 for cpu in cpus:
  if cpu in active or not queue or failures:continue
  scene=queue.pop(0);log=(O/(scene+'.log')).open('x');p=subprocess.Popen([sys.executable,'-B',str(worker),'--scene',scene,'--cpu',str(cpu)],cwd=R,stdout=log,stderr=subprocess.STDOUT);active[cpu]=(scene,p,log)
 for cpu,(scene,p,log) in list(active.items()):
  code=p.poll()
  if code is None:continue
  log.close();del active[cpu]
  if code:failures.append({'scene':scene,'exit_code':code})
  else:
   q=O/'scenes'/scene/'validation.json';assert q.exists();completed.append({'scene':scene,'path':str(q),'sha256':digest(q)})
 state={'status':'WAITING_ACTIVE_AFTER_FAILURE' if failures and active else 'FAILED' if failures else 'RUNNING','completed_scenes':len(completed),'expected_scenes':len(scenes),'active':[{'scene':scene,'pid':p.pid,'cpu':cpu} for cpu,(scene,p,log) in active.items()],'failures':failures,'queued':len(queue)};atomic_json(O/'controller-state.json',state)
 if failures and not active:break
 if active:time.sleep(30)
if failures:raise RuntimeError(str(failures))
allrows=[];kinds=collections.Counter()
for receipt in completed:
 x=json.loads(Path(receipt['path']).read_text());assert x['manifest_sha256']==digest(O/'manifest.json');assert len(x['rows'])==x['expected_tasks'];allrows.extend({**r,'scene':x['scene'],'geometry_kind':x['geometry_kind']} for r in x['rows']);kinds[x['geometry_kind']]+=len(x['rows'])
assert len(allrows)==33954 and {r['task_key'] for r in allrows}=={t['task_key'] for t in m['tasks']};counts=collections.Counter(r['status'] for r in allrows);assert counts['STATIC_BLOCKED_PRESERVED']==3411;actual=sum(r['actual_position_contacts']>0 for r in allrows);interior_only=sum(r['actual_position_contacts']==0 and r['interior_contacts']>0 for r in allrows)
atomic_json(O/'validation.json',{'status':'COMPLETE_SOURCE_SCREEN_NOT_ACCEPTANCE','coverage_complete':True,'global_tasks':33954,'scenes':len(completed),'counts':dict(counts),'tasks_with_actual_pose_contacts':actual,'tasks_with_only_interior_contacts':interior_only,'geometry_kind_task_counts':dict(kinds),'scene_receipts':completed,'manifest_sha256':digest(O/'manifest.json'),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':manifest['limits']});atomic_json(O/'controller-state.json',{'status':'COMPLETE_SOURCE_SCREEN_NOT_ACCEPTANCE','completed_scenes':len(completed),'counts':dict(counts)});print((O/'validation.json').read_text())
