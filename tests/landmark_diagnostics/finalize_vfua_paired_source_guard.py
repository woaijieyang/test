"""Wait once for the complete paired source run, then perform full independent replay audits."""
import os,sys,json,time,subprocess,datetime,fcntl
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(10)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
import psutil
B=R/'outputs/landmark-connectivity';run=B/'vfua-paired-source-guard-v1';lock=(run/'independent-controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);source_process=json.loads((run/'process.json').read_text());worker=R/'tests/landmark_diagnostics/audit_vfua_paired_records.py';geometry=R/'tests/landmark_diagnostics/projected_distance_reference.py';helper=R/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';sources={str(p):digest(p) for p in [worker,geometry,helper]};pilot=json.loads((run/'independent-pilot/shard-00.json').read_text());assert pilot['status']=='INDEPENDENT_RECORDS_AUDITED' and len(pilot['rows'])==6 and pilot['script_sha256']==sources[str(worker)]
atomic_json(run/'independent-controller-process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'source_controller':source_process,'sources':sources})
def note(status,**kw):atomic_json(run/'independent-controller-state.json',{'status':status,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw})
try:
 note('WAITING_FOR_COMPLETE_PAIRED_SCENE')
 while not (run/'validation.json').exists():
  s=Path('/proc')/str(source_process['pid'])/'stat';x=s.read_text().rsplit(')',1)[1].split() if s.exists() else []
  if not x or x[19]!=str(source_process['start_ticks']) or x[0] in 'ZX':
   note('BLOCKED_INCOMPLETE_SOURCE_RUN',source_state=json.loads((run/'state.json').read_text()));sys.exit(0)
  state=json.loads((run/'state.json').read_text())
  if state['status'] in ['FAILED','INFRASTRUCTURE_FAILURE']:note('BLOCKED_SOURCE_INFRASTRUCTURE_FAILURE',source_state=state);sys.exit(0)
  time.sleep(120)
 source=json.loads((run/'validation.json').read_text());assert source['status']=='COMPLETE_PAIRED_SCENE_NOT_GLOBAL_ACCEPTANCE' and source['total_paired_records']==1270
 for label in ['old','candidate']:assert digest(run/label/'validation.json')==source['cohorts'][label]
 assert all(digest(p)==h for p,h in sources.items())
 while True:
  usage=psutil.cpu_percent(interval=1,percpu=True);cpus=[i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i]<25]
  if len(cpus)>=4 and psutil.virtual_memory().available>=16*2**30:cpus=sorted(cpus,key=lambda i:usage[i])[:4];break
  note('WAITING_FOR_IDLE_AUDIT_CPUS');time.sleep(120)
 out=run/'independent';out.mkdir(exist_ok=False);atomic_json(out/'manifest.json',{'source_validation_sha256':digest(run/'validation.json'),'sources':sources,'geometry_export_sha256':digest(B/'vfua-native-geometry-v1/validation.json'),'cpu_ids':cpus,'shards':4,'scope':'All1270 paired records,829 native attempts and441 static blockers; all failed records retained'})
 processes=[]
 for shard,cpu in enumerate(cpus):
  log=(out/f'worker-{shard:02}.log').open('xb');p=subprocess.Popen(['bash','scripts/with_runtime.sh','runtime/awarevln/bin/python',str(worker),'--shard',str(shard),'--shards','4','--cpu',str(cpu)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT);st=Path('/proc')/str(p.pid)/'stat';atomic_json(out/f'worker-{shard:02}-process.json',{'pid':p.pid,'start_ticks':st.read_text().rsplit(')',1)[1].split()[19],'cpu':cpu});processes.append((p,log))
 note('FULL_INDEPENDENT_NATIVE_AND_GEOMETRY_AUDIT',workers=[p.pid for p,_ in processes])
 for p,log in processes:code=p.wait();log.close();assert code==0,('audit worker failed',code)
 rows=[];receipts=[]
 for shard in range(4):
  path=out/f'shard-{shard:02}.json';d=json.loads(path.read_text());assert not d['pilot'] and d['shard']==shard and d['shards']==4 and d['script_sha256']==sources[str(worker)];assert d['reference_geometry_sha256']==sources[str(geometry)];assert d['cohort_receipts']==source['cohorts'];rows+=d['rows'];receipts.append({'path':str(path),'sha256':digest(path)})
 expected={(label,t['task_key']) for label in ['old','candidate'] for t in json.loads((run/label/'manifest.json').read_text())['expected_tasks']};assert len(expected)==1270 and len(rows)==1270 and {(r['cohort'],r['task_key']) for r in rows}==expected
 issues=[r for r in rows if r['audit_issues']];counts={}
 for label in ['old','candidate']:
  data=[r for r in rows if r['cohort']==label];counts[label]={'total':len(data),'producer_pass':sum(r['producer_status']=='PASS_DIAGNOSTIC' for r in data),'independently_verified_source_pass':sum(r['producer_status']=='PASS_DIAGNOSTIC' and not r['audit_issues'] for r in data),'failed_preserved':sum(r['producer_status']=='FAILED_DIAGNOSTIC' for r in data),'static_preserved':sum(r['producer_status']=='STATIC_BLOCKED_PRESERVED' for r in data),'audit_issue_rows':sum(bool(r['audit_issues']) for r in data)}
 final={'status':'COMPLETE_WITH_AUDIT_ISSUES_NOT_ACCEPTED' if issues else 'COMPLETE_INDEPENDENT_AUDIT_NOT_GLOBAL_ACCEPTANCE','coverage_complete':True,'unique_scene_tasks':635,'total_paired_records':1270,'global_denominator':33954,'cohorts':counts,'audit_issues':issues,'receipts':receipts,'manifest_sha256':digest(out/'manifest.json'),'source_validation_sha256':digest(run/'validation.json'),'limits':'No result registration or profile adoption. Partial source-feasibility proofs do not clear global static blockers or other publication gates.'};atomic_json(out/'validation.json',final);note(final['status'],cohorts=counts)
except Exception as e:note('FAILED',error=repr(e));raise
