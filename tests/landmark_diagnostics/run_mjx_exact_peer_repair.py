"""Repair exact continuous contacts identified by the full mJX composite audit; retain all negative evidence."""
import os,sys,json,subprocess,hashlib,datetime,concurrent.futures,threading,fcntl,time
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(10)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
import psutil
B=R/'outputs/landmark-connectivity';O=B/'mjx-exact-peer-repair-v1';O.mkdir(exist_ok=False);lock=(O/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
scene='mJXqzFtmKg4';gp=R/f'data/scene_datasets/mp3d/{scene}/{scene}.glb';scene_sha=digest(gp)
worker=R/'tests/landmark_diagnostics/source_guard_continuous_peer_worker.py';helper=R/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';oracle=R/'tests/landmark_diagnostics/robust_oracle.py';geometry=R/'tests/landmark_diagnostics/projected_distance_reference.py';sweep=R/'tests/landmark_diagnostics/swept_cylinder_reference.py';sources={str(p):digest(p) for p in [worker,helper,oracle,geometry,sweep]};audit_path=B/'mjx-exact-peer-proposals-v1.json';proposal=json.loads(audit_path.read_text());assert proposal['status']=='THREE_NEW_EXACT_PROOF_SEEDS_ONE_DUPLICATE_REJECTED';seed_manifest=audit_path;selected={r['task_key'] for r in proposal['rows']};expected=len(selected);assert expected==3;seed_index={r['task_key']:{**r,'sha256':r['result_sha256']} for r in proposal['rows']};seed_binding={'source_manifests':{r['task_key']:{'path':r['manifest_path'],'sha256':r['manifest_sha256']} for r in proposal['rows']}};
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
results={};jobs=[];contexts={}
def note(status,**kw):
 atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'cohorts':{k:{'records':len(v),'passed':sum(r['status']=='PASS_DIAGNOSTIC' for r in v),'failed':sum(r['status']=='FAILED_DIAGNOSTIC' for r in v),'static_blocked':sum(r['status']=='STATIC_BLOCKED_PRESERVED' for r in v),'expected':expected} for k,v in results.items()},**kw})
try:
 note('FREEZING_PAIRED_INPUTS')
 for label,parent_name in [('guarded','full-native-v11')]:
  run=O/label;run.mkdir();(run/'inputs').mkdir();(run/'episodes').mkdir();(run/'logs').mkdir();parent_path=B/parent_name/'manifest.json';parent_bytes=parent_path.read_bytes();parent_sha=hashlib.sha256(parent_bytes).hexdigest();parent=json.loads(parent_bytes);tasks=[t for t in parent['tasks'] if t['scene']==scene and t['task_key'] in selected];assert len(tasks)==expected;profile=json.loads(Path(parent['profile_path']).read_text());asset=profile['assets'][f'mp3d/{scene}/{scene}.glb'];assert digest(parent['profile_path'])==parent['profile_sha256'] and digest(asset['navmesh_path'])==asset['navmesh_sha256'];plans={};results[label]=[]
  for t in tasks:
   tid=hashlib.sha256(t['task_key'].encode()).hexdigest();atomic_json(run/'inputs'/(tid[:24]+'.json'),t)
   if t['status']!='READY_FOR_NATIVE_MOTION':
    p=run/'episodes'/(tid[:24]+'.json');row={'task_key':t['task_key'],'source_record_sha256':t['source_record_sha256'],'status':'STATIC_BLOCKED_PRESERVED','parent_task':t};atomic_json(p,row);results[label].append({'task_key':t['task_key'],'status':row['status'],'result_path':str(p),'sha256':digest(p)});continue
   seed_row=seed_index[t['task_key']];rp=Path(seed_row['result_path']);assert digest(rp)==seed_row['sha256'];old=json.loads(rp.read_text());assert old['status']=='PASS_DIAGNOSTIC' and old['guard_manifest_sha256']==seed_binding['source_manifests'][t['task_key']]['sha256'] and digest(seed_binding['source_manifests'][t['task_key']]['path'])==old['guard_manifest_sha256'] and old['source_record_sha256']==seed_row['peer_source_record_sha256'] and old['task_key']==seed_row['peer_task_key'] and old['targets']==t['targets'];plans[t['task_key']]={'result_path':str(rp),'result_sha256':digest(rp),'trace_path':str(rp),'trace_sha256':digest(rp),'kind':'independently_exact_proven_peer_same_targets','peer_task_key':seed_row['peer_task_key'],'peer_source_record_sha256':seed_row['peer_source_record_sha256'],'proof_path':seed_row['proof_path'],'proof_sha256':seed_row['proof_sha256'],'manifest_path':seed_binding['source_manifests'][t['task_key']]['path'],'manifest_sha256':old['guard_manifest_sha256']};jobs.append((label,t))
  manifest={'scope_mode':'targeted_probe','full_scene_tasks':594,'contact_audit_path':str(audit_path),'contact_audit_sha256':digest(audit_path),'source_guard_mode':'exact_continuous_linear_sweep','sweep_helper_sha256':sources[str(sweep)],'seed_guard_manifest_path':str(seed_manifest),'seed_guard_manifest_sha256':digest(seed_manifest),'status':'FROZEN_COMPLETE_SCENE_SOURCE_GUARD','native_geometry':{'receipt_path':str(B/'step-envelope-native-geometry-v1/validation.json'),'receipt_sha256':digest(B/'step-envelope-native-geometry-v1/validation.json')},'parent_manifest_sha256':parent_sha,'profile_path':parent['profile_path'],'profile_sha256':parent['profile_sha256'],'scene_sha256':scene_sha,'worker_sha256':sources[str(worker)],'helper_sha256':sources[str(helper)],'oracle_sha256':sources[str(oracle)],'geometry_reference_sha256':sources[str(geometry)],'native_plan_inputs':plans,'expected_tasks':[{'task_key':t['task_key'],'source_record_sha256':t['source_record_sha256'],'prior_status':t['status']} for t in tasks],'expected':expected,'body':parent['body'],'actions':parent['actions'],'motion_gate':parent['motion_gate'],'max_search_nodes':5000,'scope':'Source-clear feasibility diagnosis only, targeted contact repair with full scene denominator retained; raw native plans are proposals and each action is revalidated/reexecuted, not copied result acceptance'};atomic_json(run/'manifest.json',manifest);contexts[label]={'run':run,'manifest':manifest,'parent_path':parent_path}
 assert len(jobs)==expected
 while True:
  usage=psutil.cpu_percent(interval=1,percpu=True);cpus=[i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i]<25 and i not in [6,10,11,12,13,15,18,20,22,24,27,30]]
  if len(cpus)>=3 and psutil.virtual_memory().available>=16*2**30:cpus=sorted(cpus,key=lambda i:usage[i])[:3];break
  note('WAITING_FOR_IDLE_CPU_AND_MEMORY');time.sleep(30)
 atomic_json(O/'manifest.json',{'scene':scene,'cohorts':{label:{'manifest_sha256':digest(c['run']/'manifest.json'),'parent_manifest_sha256':c['manifest']['parent_manifest_sha256'],'expected':expected} for label,c in contexts.items()},'sources':sources,'cpu_ids':cpus,'workers':3,'ready_jobs':len(jobs),'total_records':expected,'global_denominator_remains':33954,'script_sha256':digest(__file__)})
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
 pilot=sorted(jobs,key=lambda j:j[1]['task_key'])[0];first=execute(pilot);assert first and first[1]['status']!='INFRASTRUCTURE_FAILURE',first;results[first[0]].append(first[1]);note('RUNNING_PAIRED_SCENE',cpu_ids=cpus)
 # Interleave old/candidate records by task identity for paired evidence.
 ordered=sorted([j for j in jobs if j!=pilot],key=lambda j:(j[1]['task_key'],j[0]))
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
  futures=[pool.submit(execute,j) for j in ordered]
  for future in concurrent.futures.as_completed(futures):
   value=future.result()
   if value is None:continue
   label,row=value;results[label].append(row);atomic_json(contexts[label]['run']/'results-index.json',results[label]);note('RUNNING_PAIRED_SCENE' if not stop.is_set() else 'INFRASTRUCTURE_FAILURE',cpu_ids=cpus)
 assert not stop.is_set()
 for label,c in contexts.items():
  assert len(results[label])==expected and len({r['task_key'] for r in results[label]})==expected;assert digest(c['parent_path'])==c['manifest']['parent_manifest_sha256'];atomic_json(c['run']/'validation.json',{'status':'COMPLETE_SOURCE_GUARD_DIAGNOSTIC_NOT_ACCEPTED','expected':expected,'coverage_complete':True,'counts':{s:sum(r['status']==s for r in results[label]) for s in ['PASS_DIAGNOSTIC','FAILED_DIAGNOSTIC','STATIC_BLOCKED_PRESERVED']},'manifest_sha256':digest(c['run']/'manifest.json'),'results':results[label]})
 atomic_json(O/'validation.json',{'status':'COMPLETE_SCENE_SOURCE_GUARD_NOT_GLOBAL_ACCEPTANCE','expected_unique_tasks':expected,'global_denominator':33954,'cohort_validation_sha256':digest(contexts['guarded']['run']/'validation.json'),'limits':'Only the explicitly selected new peer-plan tasks are reexecuted; all594 scene tasks and33954 global tasks remain in the denominator. Other old proofs and failures are retained unchanged. Source-guarded native actual execution and in-worker replay; independent complete audit and all global gates still required.'});note('COMPLETE_SCENE_SOURCE_GUARD_NOT_GLOBAL_ACCEPTANCE')
except Exception as e:note('FAILED',error=repr(e));raise
