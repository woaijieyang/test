"""Complete paired VFua source-guard diagnostic, retaining static blockers in both denominators."""
import os,sys,json,subprocess,hashlib,datetime,concurrent.futures,threading,fcntl,time
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(10)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
import psutil
B=R/'outputs/landmark-connectivity';O=B/'17drp-source-guard-v2';O.mkdir(exist_ok=False);lock=(O/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
scene='17DRP5sb8fy';gp=R/f'data/scene_datasets/mp3d/{scene}/{scene}.glb';scene_sha=digest(gp)
worker=R/'tests/landmark_diagnostics/source_guard_native_geometry_worker.py';helper=R/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';oracle=R/'tests/landmark_diagnostics/robust_oracle.py';geometry=R/'tests/landmark_diagnostics/projected_distance_reference.py';sources={str(p):digest(p) for p in [worker,helper,oracle,geometry]};atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
results={};jobs=[];contexts={}
def note(status,**kw):
 atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'cohorts':{k:{'records':len(v),'passed':sum(r['status']=='PASS_DIAGNOSTIC' for r in v),'failed':sum(r['status']=='FAILED_DIAGNOSTIC' for r in v),'static_blocked':sum(r['status']=='STATIC_BLOCKED_PRESERVED' for r in v),'expected':261} for k,v in results.items()},**kw})
try:
 note('FREEZING_PAIRED_INPUTS')
 for label,parent_name in [('guarded','full-native-v11')]:
  run=O/label;run.mkdir();(run/'inputs').mkdir();(run/'episodes').mkdir();(run/'logs').mkdir();parent_path=B/parent_name/'manifest.json';parent=json.loads(parent_path.read_text());tasks=[t for t in parent['tasks'] if t['scene']==scene];assert len(tasks)==261;profile=json.loads(Path(parent['profile_path']).read_text());asset=profile['assets'][f'mp3d/{scene}/{scene}.glb'];assert digest(parent['profile_path'])==parent['profile_sha256'] and digest(asset['navmesh_path'])==asset['navmesh_sha256'];plans={};results[label]=[]
  for t in tasks:
   tid=hashlib.sha256(t['task_key'].encode()).hexdigest();atomic_json(run/'inputs'/(tid[:24]+'.json'),t)
   if t['status']!='READY_FOR_NATIVE_MOTION':
    p=run/'episodes'/(tid[:24]+'.json');row={'task_key':t['task_key'],'source_record_sha256':t['source_record_sha256'],'status':'STATIC_BLOCKED_PRESERVED','parent_task':t};atomic_json(p,row);results[label].append({'task_key':t['task_key'],'status':row['status'],'result_path':str(p),'sha256':digest(p)});continue
   rp=B/parent_name/f'shard-{int(tid,16)%8:02}'/(tid[:24]+'.result.json');old=json.loads(rp.read_text());tp=B/parent_name/old['trace_path'];assert old['status']=='PASS' and old['manifest_sha256']==digest(parent_path) and old['source_record_sha256']==t['source_record_sha256'] and digest(tp)==old['trace_sha256'];plans[t['task_key']]={'result_path':str(rp),'result_sha256':digest(rp),'trace_path':str(tp),'trace_sha256':digest(tp)};jobs.append((label,t))
  manifest={'status':'FROZEN_COMPLETE_SCENE_SOURCE_GUARD','native_geometry':{'receipt_path':str(B/'full-source-native-confirmation-17DRP-v1/validation.json'),'receipt_sha256':digest(B/'full-source-native-confirmation-17DRP-v1/validation.json')},'parent_manifest_sha256':digest(parent_path),'profile_path':parent['profile_path'],'profile_sha256':parent['profile_sha256'],'scene_sha256':scene_sha,'worker_sha256':sources[str(worker)],'helper_sha256':sources[str(helper)],'oracle_sha256':sources[str(oracle)],'geometry_reference_sha256':sources[str(geometry)],'native_plan_inputs':plans,'expected_tasks':[{'task_key':t['task_key'],'source_record_sha256':t['source_record_sha256'],'prior_status':t['status']} for t in tasks],'expected':261,'body':parent['body'],'actions':parent['actions'],'motion_gate':parent['motion_gate'],'max_search_nodes':5000,'scope':'Source-clear feasibility diagnosis only, complete paired scene denominators; raw native plans are proposals and each action is revalidated/reexecuted, not copied result acceptance'};atomic_json(run/'manifest.json',manifest);contexts[label]={'run':run,'manifest':manifest,'parent_path':parent_path}
 assert len(jobs)==237
 while True:
  usage=psutil.cpu_percent(interval=1,percpu=True);cpus=[i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i]<25 and i not in [6,7,20,25]]
  if len(cpus)>=4 and psutil.virtual_memory().available>=16*2**30:cpus=sorted(cpus,key=lambda i:usage[i])[:4];break
  note('WAITING_FOR_IDLE_CPU_AND_MEMORY');time.sleep(120)
 atomic_json(O/'manifest.json',{'scene':scene,'cohorts':{label:{'manifest_sha256':digest(c['run']/'manifest.json'),'parent_manifest_sha256':c['manifest']['parent_manifest_sha256'],'expected':261} for label,c in contexts.items()},'sources':sources,'cpu_ids':cpus,'workers':4,'ready_jobs':len(jobs),'total_records':261,'global_denominator_remains':33954,'script_sha256':digest(__file__)})
 stop=threading.Event();alloc=threading.Lock();free=list(cpus)
 def execute(job):
  label,t=job
  if stop.is_set():return None
  with alloc:cpu=free.pop()
  c=contexts[label];run=c['run'];tid=hashlib.sha256(t['task_key'].encode()).hexdigest()[:24];out=run/'episodes'/(tid+'.json')
  try:
   assert all(digest(p)==h for p,h in sources.items())
   with (run/'logs'/(tid+'.log')).open('xb') as log:
    proc=subprocess.Popen([sys.executable,'-B',str(worker),'--manifest',str(run/'manifest.json'),'--task-file',str(run/'inputs'/(tid+'.json')),'--output',str(out),'--cpu',str(cpu)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','PYTHONHASHSEED':'0'});st=Path('/proc')/str(proc.pid)/'stat';atomic_json(run/'logs'/(tid+'.process.json'),{'pid':proc.pid,'start_ticks':st.read_text().rsplit(')',1)[1].split()[19],'task_key':t['task_key'],'cpu':cpu});code=proc.wait()
   assert code==0 and out.exists(),('worker failure',code)
   d=json.loads(out.read_text());assert d['task_key']==t['task_key'] and d['source_record_sha256']==t['source_record_sha256'] and d['targets']==t['targets'];assert d['guard_manifest_sha256']==digest(run/'manifest.json') and d['script_sha256']==sources[str(worker)] and d['scene_sha256']==scene_sha and d['geometry_reference_sha256']==sources[str(geometry)];assert len(d['positions'])==len(d['actions'])+1
   if d['status']=='PASS_DIAGNOSTIC':assert d['error'] is None and d['max_replay_error']<=1e-5 and len(d['boundaries'])==len(t['targets'])-1
   return label,{'task_key':t['task_key'],'status':d['status'],'actions':len(d['actions']),'error':d['error'],'result_path':str(out),'sha256':digest(out)}
  except Exception as e:stop.set();return label,{'task_key':t['task_key'],'status':'INFRASTRUCTURE_FAILURE','error':repr(e)}
  finally:
   with alloc:free.append(cpu)
 # One actual execution validates the new entry point before all remaining jobs.
 pilot=next(j for j in jobs if j[0]=='guarded' and j[1]['task_key']=='train:54269');first=execute(pilot);assert first and first[1]['status']!='INFRASTRUCTURE_FAILURE',first;results[first[0]].append(first[1]);note('RUNNING_PAIRED_SCENE',cpu_ids=cpus)
 # Interleave old/candidate records by task identity for paired evidence.
 ordered=sorted([j for j in jobs if j!=pilot],key=lambda j:(j[1]['task_key'],j[0]))
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  futures=[pool.submit(execute,j) for j in ordered]
  for future in concurrent.futures.as_completed(futures):
   value=future.result()
   if value is None:continue
   label,row=value;results[label].append(row);atomic_json(contexts[label]['run']/'results-index.json',results[label]);note('RUNNING_PAIRED_SCENE' if not stop.is_set() else 'INFRASTRUCTURE_FAILURE',cpu_ids=cpus)
 assert not stop.is_set()
 for label,c in contexts.items():
  assert len(results[label])==261 and len({r['task_key'] for r in results[label]})==261;assert digest(c['parent_path'])==c['manifest']['parent_manifest_sha256'];atomic_json(c['run']/'validation.json',{'status':'COMPLETE_SOURCE_GUARD_DIAGNOSTIC_NOT_ACCEPTED','expected':261,'coverage_complete':True,'counts':{s:sum(r['status']==s for r in results[label]) for s in ['PASS_DIAGNOSTIC','FAILED_DIAGNOSTIC','STATIC_BLOCKED_PRESERVED']},'manifest_sha256':digest(c['run']/'manifest.json'),'results':results[label]})
 atomic_json(O/'validation.json',{'status':'COMPLETE_SCENE_SOURCE_GUARD_NOT_GLOBAL_ACCEPTANCE','expected_unique_tasks':261,'global_denominator':33954,'cohort_validation_sha256':digest(contexts['guarded']['run']/'validation.json'),'limits':'All261 scene tasks retained. Source-guarded native actual execution and in-worker replay; independent complete audit and all global gates still required.'});note('COMPLETE_SCENE_SOURCE_GUARD_NOT_GLOBAL_ACCEPTANCE')
except Exception as e:note('FAILED',error=repr(e));raise
