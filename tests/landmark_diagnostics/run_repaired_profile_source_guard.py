"""Complete paired VFua source-guard diagnostic, retaining static blockers in both denominators."""
import os,sys,json,subprocess,hashlib,datetime,concurrent.futures,threading,fcntl,time,argparse,re
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--scene',required=True);parser.add_argument('--proposal',required=True);parser.add_argument('--run',required=True);args=parser.parse_args();assert re.fullmatch('[A-Za-z0-9-]+',args.proposal) and re.fullmatch('[A-Za-z0-9]{11}',args.scene) and re.fullmatch('full-source-guard-[A-Za-z0-9-]+',args.run);
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(10)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
import psutil
B=R/'outputs/landmark-connectivity';O=B/args.run;O.mkdir(exist_ok=False);lock=(O/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
scene=args.scene;expected=sum(t['scene']==scene for t in json.loads((B/'full-native-v11/manifest.json').read_text())['tasks']);assert expected>0;gp=R/f'data/scene_datasets/mp3d/{scene}/{scene}.glb';scene_sha=digest(gp)
worker=R/'tests/landmark_diagnostics/source_guard_repaired_profile_worker.py';helper=R/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';oracle=R/'tests/landmark_diagnostics/robust_oracle.py';geometry=R/'tests/landmark_diagnostics/projected_distance_reference.py';sources={str(p):digest(p) for p in [worker,helper,oracle,geometry]};atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
results={};jobs=[];contexts={}
def note(status,**kw):
 atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'cohorts':{k:{'records':len(v),'passed':sum(r['status']=='PASS_DIAGNOSTIC' for r in v),'failed':sum(r['status']=='FAILED_DIAGNOSTIC' for r in v),'source_candidate_blocked':sum(r['status']=='SOURCE_CANDIDATE_BLOCKED_PRESERVED' for r in v),'expected':expected} for k,v in results.items()},**kw})
try:
 proposal=B/args.proposal;candidate_path=proposal/'candidate_tasks.json';static_audit_path=proposal/'independent-static.json';proof=json.loads(static_audit_path.read_text());assert proof['status']=='PASS_PROPOSAL_IDENTITY_BOUNDS_BODY_AND_CONNECTIVITY_NOT_MOTION' and proof['candidate_tasks_sha256']==digest(candidate_path);proposed={t['task_key']:t for t in json.loads(candidate_path.read_text())['tasks']};proposal_rows={t['task_key']:t for t in json.loads((proposal/'validation.json').read_text())['rows']};assert len(proposed)==expected
 note('FREEZING_DERIVED_TARGET_INPUTS')
 for label,parent_name in [('guarded','full-native-v11')]:
  run=O/label;run.mkdir();(run/'inputs').mkdir();(run/'source_inputs').mkdir();(run/'episodes').mkdir();(run/'logs').mkdir();parent_path=B/parent_name/'manifest.json';parent_bytes=parent_path.read_bytes();parent_sha=hashlib.sha256(parent_bytes).hexdigest();parent=json.loads(parent_bytes);original_tasks={t['task_key']:t for t in parent['tasks'] if t['scene']==scene};tasks=[proposed[t['task_key']] for t in parent['tasks'] if t['scene']==scene];assert len(tasks)==expected;source_profile=json.loads(Path(parent['profile_path']).read_text());source_mesh_sha=source_profile['assets'][f'mp3d/{scene}/{scene}.glb']['navmesh_sha256'];proposal_report=json.loads((proposal/'validation.json').read_text());active_profile_path=Path(proposal_report['profile_path']);assert active_profile_path.resolve().is_relative_to(R/'data/derived/navmeshes') and digest(active_profile_path)==proof['profile_sha256'];profile=json.loads(active_profile_path.read_text());asset=profile['assets'][f'mp3d/{scene}/{scene}.glb'];assert digest(parent['profile_path'])==parent['profile_sha256'] and digest(asset['navmesh_path'])==asset['navmesh_sha256'];plans={};results[label]=[]
  for t in tasks:
   tid=hashlib.sha256(t['task_key'].encode()).hexdigest();atomic_json(run/'inputs'/(tid[:24]+'.json'),t);source_task_path=run/'source_inputs'/(tid[:24]+'.json');atomic_json(source_task_path,original_tasks[t['task_key']])
   if proposal_rows[t['task_key']]['status']=='NO_SOURCE_CLEAR_COMMON_COMPONENT':
    p=run/'episodes'/(tid[:24]+'.json');row={'task_key':t['task_key'],'source_record_sha256':t['source_record_sha256'],'status':'SOURCE_CANDIDATE_BLOCKED_PRESERVED','parent_task':t,'candidate_failure':proposal_rows[t['task_key']],'original_native_status':original_tasks[t['task_key']]['status']};atomic_json(p,row);results[label].append({'task_key':t['task_key'],'status':row['status'],'result_path':str(p),'sha256':digest(p)});continue
   rp=B/parent_name/f'shard-{int(tid,16)%8:02}'/(tid[:24]+'.result.json');old=json.loads(rp.read_text());tp=B/parent_name/old['trace_path'];assert old['status']=='PASS' and old['manifest_sha256']==parent_sha and old['source_record_sha256']==t['source_record_sha256'] and digest(tp)==old['trace_sha256'];plans[t['task_key']]={'result_path':str(rp),'result_sha256':digest(rp),'trace_path':str(tp),'trace_sha256':digest(tp),'source_mesh_sha256':source_mesh_sha,'source_task_path':str(source_task_path),'source_task_sha256':digest(source_task_path)};jobs.append((label,t))
  manifest={'status':'FROZEN_DERIVED_TARGET_SOURCE_GUARD','candidate_tasks_path':str(candidate_path),'candidate_tasks_sha256':digest(candidate_path),'candidate_static_audit_path':str(static_audit_path),'candidate_static_audit_sha256':digest(static_audit_path),'proposal_rows_path':str(proposal/'validation.json'),'proposal_rows_sha256':digest(proposal/'validation.json'),'native_geometry':{'receipt_path':str(B/f'full-source-native-{scene}-v1/validation.json'),'receipt_sha256':digest(B/f'full-source-native-{scene}-v1/validation.json')},'parent_manifest_sha256':parent_sha,'source_profile_path':parent['profile_path'],'source_profile_sha256':parent['profile_sha256'],'profile_path':str(active_profile_path),'profile_sha256':digest(active_profile_path),'scene_sha256':scene_sha,'worker_sha256':sources[str(worker)],'helper_sha256':sources[str(helper)],'oracle_sha256':sources[str(oracle)],'geometry_reference_sha256':sources[str(geometry)],'native_plan_inputs':plans,'expected_tasks':[{'task_key':t['task_key'],'source_record_sha256':t['source_record_sha256'],'prior_status':original_tasks[t['task_key']]['status'],'candidate_status':proposal_rows[t['task_key']]['status']} for t in tasks],'expected':expected,'body':parent['body'],'actions':parent['actions'],'motion_gate':parent['motion_gate'],'max_search_nodes':5000,'scope':'Source-clear feasibility diagnosis only, complete single-scene denominator; raw native plans are proposals and each action is revalidated/reexecuted, not copied result acceptance'};atomic_json(run/'manifest.json',manifest);contexts[label]={'run':run,'manifest':manifest,'parent_path':parent_path}
 assert len(jobs)==sum(t['candidate_status']=='SOURCE_CLEAR_TARGETS_COMMON_COMPONENT_PENDING_MOTION' for t in contexts['guarded']['manifest']['expected_tasks'])
 while True:
  usage=psutil.cpu_percent(interval=1,percpu=True);cpus=[i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i]<25 and i not in [6,12,18,20,22,24,27,30]]
  if len(cpus)>=4 and psutil.virtual_memory().available>=16*2**30:cpus=sorted(cpus,key=lambda i:usage[i])[:4];break
  note('WAITING_FOR_IDLE_CPU_AND_MEMORY');time.sleep(120)
 atomic_json(O/'manifest.json',{'scene':scene,'cohorts':{label:{'manifest_sha256':digest(c['run']/'manifest.json'),'parent_manifest_sha256':c['manifest']['parent_manifest_sha256'],'expected':expected} for label,c in contexts.items()},'sources':sources,'cpu_ids':cpus,'workers':4,'ready_jobs':len(jobs),'total_records':expected,'global_denominator_remains':33954,'script_sha256':digest(__file__)})
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
 confirmed=json.loads((B/f'full-source-native-{scene}-v1/actual-position-confirmation.json').read_text())['task_keys_with_native_confirmed_actual_alerts'];assert confirmed;pilot=next(j for j in jobs if j[0]=='guarded' and j[1]['task_key'] in set(confirmed));first=execute(pilot);assert first and first[1]['status']!='INFRASTRUCTURE_FAILURE',first;results[first[0]].append(first[1]);note('RUNNING_SOURCE_GUARD_SCENE',cpu_ids=cpus)
 # Interleave old/candidate records by task identity for paired evidence.
 ordered=sorted([j for j in jobs if j!=pilot],key=lambda j:(j[1]['task_key'],j[0]))
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  futures=[pool.submit(execute,j) for j in ordered]
  for future in concurrent.futures.as_completed(futures):
   value=future.result()
   if value is None:continue
   label,row=value;results[label].append(row);atomic_json(contexts[label]['run']/'results-index.json',results[label]);note('RUNNING_SOURCE_GUARD_SCENE' if not stop.is_set() else 'INFRASTRUCTURE_FAILURE',cpu_ids=cpus)
 assert not stop.is_set()
 for label,c in contexts.items():
  assert len(results[label])==expected and len({r['task_key'] for r in results[label]})==expected;assert digest(c['parent_path'])==c['manifest']['parent_manifest_sha256'];atomic_json(c['run']/'validation.json',{'status':'COMPLETE_SOURCE_GUARD_DIAGNOSTIC_NOT_ACCEPTED','expected':expected,'coverage_complete':True,'counts':{s:sum(r['status']==s for r in results[label]) for s in ['PASS_DIAGNOSTIC','FAILED_DIAGNOSTIC','SOURCE_CANDIDATE_BLOCKED_PRESERVED']},'manifest_sha256':digest(c['run']/'manifest.json'),'results':results[label]})
 atomic_json(O/'validation.json',{'status':'COMPLETE_SCENE_SOURCE_GUARD_NOT_GLOBAL_ACCEPTANCE','expected_unique_tasks':expected,'global_denominator':33954,'cohort_validation_sha256':digest(contexts['guarded']['run']/'validation.json'),'limits':'All scene tasks retained, including unresolved derived-target cases. Source-guarded native actual execution and in-worker replay; independent complete audit and all global gates still required.'});note('COMPLETE_SCENE_SOURCE_GUARD_NOT_GLOBAL_ACCEPTANCE')
except Exception as e:note('FAILED',error=repr(e));raise
