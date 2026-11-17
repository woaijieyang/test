"""Full affected-scene source-geometry guarded native audit, independent child processes."""
import os,sys,json,pathlib,subprocess,hashlib,datetime,concurrent.futures,threading,fcntl
R=pathlib.Path('/data/zy/vln/case1');os.chdir(R);sys.path.insert(0,str(R/'scripts'));from workspace import atomic_json,digest
B=R/'outputs/landmark-connectivity';RUN=B/'recast626-source-guard-scene-v1';RUN.mkdir(exist_ok=False);lease=(RUN/'controller.lock').open('a');fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
parent_path=B/'full-native-v11/manifest.json';parent=json.loads(parent_path.read_text());tasks=[t for t in parent['tasks'] if t['scene']=='mJXqzFtmKg4'];assert len(tasks)==594 and all(t['status']=='READY_FOR_NATIVE_MOTION' for t in tasks);recovered=set(json.loads((B/'full-native-v11/static-transition-audit.json').read_text())['recovered']);assert len(recovered)==45
import psutil
usage=psutil.cpu_percent(interval=1,percpu=True);cpus=sorted(sorted(os.sched_getaffinity(0))[:64],key=lambda c:usage[c])[:4];worker=R/'tests/landmark_diagnostics/recast626_source_guard_worker.py';helper=R/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';oracle=R/'tests/landmark_diagnostics/robust_oracle.py'
manifest={'status':'FROZEN_DIAGNOSTIC','parent_manifest_sha256':digest(parent_path),'profile_path':parent['profile_path'],'profile_sha256':parent['profile_sha256'],'worker_sha256':digest(worker),'helper_sha256':digest(helper),'oracle_sha256':digest(oracle),'expected_tasks':[{'task_key':t['task_key'],'source_record_sha256':t['source_record_sha256'],'newly_recovered':t['task_key'] in recovered} for t in tasks],'cpu_ids':cpus,'body':parent['body'],'actions':parent['actions'],'motion_gate':parent['motion_gate'],'max_search_nodes':5000,'scope':'All594 affected-scene tasks, source-body guard plus fresh actual native motion and replay; no model metrics or publication approval'};atomic_json(RUN/'manifest.json',manifest);(RUN/'inputs').mkdir();(RUN/'episodes').mkdir();(RUN/'logs').mkdir();atomic_json(RUN/'process.json',{'pid':os.getpid(),'start_ticks':pathlib.Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
for t in tasks:
 tid=hashlib.sha256(t['task_key'].encode()).hexdigest()[:24];atomic_json(RUN/'inputs'/(tid+'.json'),t)
results=[];stop=threading.Event();lock=threading.Lock();free=list(cpus)
def note(status,**kw):atomic_json(RUN/'state.json',{'status':status,'time':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),**kw})
def execute(t):
 if stop.is_set():return None
 with lock:cpu=free.pop()
 tid=hashlib.sha256(t['task_key'].encode()).hexdigest()[:24];out=RUN/'episodes'/(tid+'.json');command=['bash','scripts/with_runtime.sh',str(R/'runtime/awarevln/bin/python'),str(worker),'--manifest',str(RUN/'manifest.json'),'--task-file',str(RUN/'inputs'/(tid+'.json')),'--output',str(out),'--cpu',str(cpu)]
 try:
  with (RUN/'logs'/(tid+'.log')).open('xb') as log:
   p=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','PYTHONHASHSEED':'0'});st=pathlib.Path('/proc')/str(p.pid)/'stat';atomic_json(RUN/'logs'/(tid+'.process.json'),{'pid':p.pid,'start_ticks':st.read_text().rsplit(')',1)[1].split()[19],'task_key':t['task_key'],'cpu':cpu});code=p.wait()
  if code!=0 or not out.exists():stop.set();return {'task_key':t['task_key'],'status':'INFRASTRUCTURE_FAILURE','exit_code':code}
  d=json.loads(out.read_text());assert d['task_key']==t['task_key'] and d['source_record_sha256']==t['source_record_sha256'];assert d['guard_manifest_sha256']==digest(RUN/'manifest.json') and d['script_sha256']==manifest['worker_sha256'];assert d['targets']==t['targets'];assert len(d['positions'])==len(d['actions'])+1
  if d['status']=='PASS_DIAGNOSTIC':assert d['error'] is None and d['max_replay_error']<=1e-5 and len(d['boundaries'])==len(t['targets'])-1
  return {'task_key':t['task_key'],'status':d['status'],'newly_recovered':t['task_key'] in recovered,'actions':len(d['actions']),'error':d['error'],'result_path':str(out),'sha256':digest(out)}
 except Exception as e:stop.set();return {'task_key':t['task_key'],'status':'INFRASTRUCTURE_FAILURE','error':repr(e)}
 finally:
  with lock:free.append(cpu)
try:
 note('PREFLIGHT',expected=594,cpu_ids=cpus)
 pilot=next(t for t in tasks if t['task_key']=='train:38384');first=execute(pilot);assert first and first['status']=='PASS_DIAGNOSTIC',first;results.append(first);note('RUNNING',completed=1,passed=1,failed=0,expected=594,cpu_ids=cpus)
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  futures=[pool.submit(execute,t) for t in tasks if t['task_key']!=pilot['task_key']]
  for future in concurrent.futures.as_completed(futures):
   row=future.result()
   if row is None:continue
   results.append(row);atomic_json(RUN/'results-index.json',results);note('RUNNING' if not stop.is_set() else 'INFRASTRUCTURE_FAILURE',completed=len(results),passed=sum(x['status']=='PASS_DIAGNOSTIC' for x in results),failed=sum(x['status']!='PASS_DIAGNOSTIC' for x in results),expected=594,cpu_ids=cpus)
 assert digest(parent_path)==manifest['parent_manifest_sha256'];coverage=len(results)==594 and len({r['task_key'] for r in results})==594;passed=sum(r['status']=='PASS_DIAGNOSTIC' for r in results);report={'status':'PASS_AFFECTED_SCENE_DIAGNOSTIC' if coverage and passed==594 else 'COMPLETE_NOT_ACCEPTED' if coverage else 'INCOMPLETE_INFRASTRUCTURE_FAILURE','coverage_complete':coverage,'expected':594,'completed':len(results),'passed':passed,'failed':len(results)-passed,'newly_recovered_passed':sum(r.get('newly_recovered',False) and r['status']=='PASS_DIAGNOSTIC' for r in results),'manifest_sha256':digest(RUN/'manifest.json'),'results':results,'limits':'This is additional affected-scene feasibility evidence only; remaining dataset failures and all publication gates remain.'};atomic_json(RUN/'validation.json',report);note(report['status'],completed=len(results),passed=passed,expected=594)
except Exception as e:note('FAILED',reason=repr(e),completed=len(results));raise
