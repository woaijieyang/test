"""Four-idle-CPU full native-source exact audit, gated on complete native provenance."""
import os,sys,json,time,datetime,subprocess,collections,shutil,fcntl
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
import psutil
B=R/'outputs/landmark-connectivity';O=B/'full-native-source-exact-v1';O.mkdir(exist_ok=False);(O/'scenes').mkdir();lock=(O/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});catalog_run=B/'native-source-catalog-v1';source=json.loads((catalog_run/'independent-process.json').read_text())
def note(status,**kw):atomic_json(O/'controller-state.json',{'status':status,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw})
try:
 note('WAITING_FOR_FULL_NATIVE_CATALOG_INDEPENDENT_AUDIT')
 while not (catalog_run/'independent-validation.json').exists():
  p=Path('/proc',str(source['pid']),'stat');s=p.read_text().rsplit(')',1)[1].split() if p.exists() else [];assert s and s[19]==str(source['start_ticks']) and s[0] not in ['Z','X'],'Catalog independent auditor terminal without full report';time.sleep(60)
 c=json.loads((catalog_run/'independent-validation.json').read_text());assert c['status']=='PASS_ALL71_NATIVE_PROVENANCE_AND_BINARY_STRUCTURE_NOT_NAVIGATION' and c['scenes']==71 and c['global_tasks']==33954 and c['catalog_sha256']==digest(catalog_run/'catalog.json');catalog=json.loads((catalog_run/'catalog.json').read_text());native={r['scene']:r for r in catalog['scenes']};assert len(native)==71
 parent=B/'full-native-v11/manifest.json';m=json.loads(parent.read_text());pv=B/'full-native-v11/validation.json';validated=json.loads(pv.read_text());assert validated['coverage_complete'] and not validated['audit_issues'] and validated['manifest_sha256']==digest(parent);assert len(m['tasks'])==len({t['task_key'] for t in m['tasks']})==33954;scenes=sorted({t['scene'] for t in m['tasks']});assert set(scenes)==set(native)
 while True:
  u=psutil.cpu_percent(interval=1,percpu=True);eligible=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<20 and i not in [1,7,15,16]];cpus=sorted(eligible,key=lambda i:u[i])[:4]
  if len(cpus)==4 and psutil.virtual_memory().available>24*2**30 and shutil.disk_usage(R).free>10*2**30:break
  note('WAITING_FOR_FOUR_IDLE_CPUS_AND_MEMORY');time.sleep(30)
 worker=R/'tests/landmark_diagnostics/audit_native_exact_scene_traces.py';old={}
 for scene in scenes:
  p=B/'full-source-geometry-v1/scenes'/scene/'validation.json';old[scene]={'path':str(p),'sha256':digest(p)}
 manifest={'status':'FROZEN_FULL_NATIVE_EXACT_GEOMETRY_AUDIT','global_tasks':33954,'scenes':scenes,'parent_manifest_sha256':digest(parent),'parent_validation_sha256':digest(pv),'profile_sha256':m['profile_sha256'],'worker_sha256':digest(worker),'controller_sha256':digest(__file__),'sweep_sha256':digest(R/'tests/landmark_diagnostics/swept_cylinder_reference.py'),'distance_sha256':digest(R/'tests/landmark_diagnostics/projected_distance_reference.py'),'native_geometry':native,'catalog_independent_sha256':digest(catalog_run/'independent-validation.json'),'old_screen_receipts':old,'cpus':cpus,'settings':{'height':1.5,'radius':.1,'foot_epsilon':1e-5,'radial_threshold':.1-1e-6,'continuous_interpretation':'exact_continuous_linear','deduplication':'exact coordinate tuples, no rounding'},'limits':'Immutable originalv11 traces, not new navigation or replay. Full native source plus exact continuous interpretation; original sampled screen retained, and repaired alternate proofs remain separate. Static failures not removed, no final acceptance or score.'};atomic_json(O/'manifest.json',manifest)
 queue=list(scenes);active={};completed=[];failures=[]
 while queue or active:
  for cpu in cpus:
   if cpu in active or not queue or failures:continue
   scene=queue.pop(0);log=(O/(scene+'.log')).open('x');proc=subprocess.Popen([sys.executable,'-B',str(worker),'--scene',scene,'--cpu',str(cpu)],stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL);ticks=Path('/proc',str(proc.pid),'stat').read_text().rsplit(')',1)[1].split()[19];active[cpu]=(scene,proc,log,ticks)
  for cpu,(scene,proc,log,ticks) in list(active.items()):
   code=proc.poll()
   if code is None:continue
   log.close();del active[cpu]
   if code:failures.append({'scene':scene,'exit_code':code})
   else:
    p=O/'scenes'/scene/'validation.json';assert p.exists();completed.append({'scene':scene,'path':str(p),'sha256':digest(p)})
  note('WAITING_ACTIVE_AFTER_FAILURE' if failures and active else 'FAILED' if failures else 'RUNNING',completed_scenes=len(completed),expected_scenes=71,active=[{'scene':sc,'pid':pr.pid,'start_ticks':ticks,'cpu':cpu} for cpu,(sc,pr,log,ticks) in active.items()],failures=failures,queued=len(queue))
  if failures and not active:break
  if active:time.sleep(30)
 assert not failures,failures;rows=[]
 for receipt in completed:
  d=json.loads(Path(receipt['path']).read_text());assert d['manifest_sha256']==digest(O/'manifest.json') and len(d['rows'])==d['expected_tasks'];rows.extend({**r,'scene':d['scene']} for r in d['rows'])
 assert len(rows)==len({r['task_key'] for r in rows})==33954 and {r['task_key'] for r in rows}=={t['task_key'] for t in m['tasks']};counts=dict(collections.Counter(r['status'] for r in rows));assert counts['STATIC_BLOCKED_PRESERVED']==3411;cross=dict(collections.Counter(r['old_sampled_status']+' -> '+r['status'] for r in rows));atomic_json(O/'validation.json',{'status':'COMPLETE_FULL_NATIVE_EXACT_GEOMETRY_AUDIT_NOT_ACCEPTANCE','coverage_complete':True,'global_tasks':33954,'scenes':71,'counts':counts,'old_sampled_to_new_exact':cross,'actions':sum(r['actions'] for r in rows),'scene_receipts':completed,'manifest_sha256':digest(O/'manifest.json'),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':manifest['limits']});note('COMPLETE_FULL_NATIVE_EXACT_GEOMETRY_AUDIT_NOT_ACCEPTANCE',completed_scenes=71,counts=counts)
except Exception as e:note('FAILED',error=repr(e));raise
