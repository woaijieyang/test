"""One-shot complete v1/v3 comparison, retaining every failed task and source identity."""
import collections,datetime,json,os,sys,time
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import digest,atomic_json
B=R/'outputs/connectivity';O=B/'endpoint115-v3-paired-audit-v1';O.mkdir(exist_ok=False);os.nice(15)
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
def note(status,**kw):atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**kw})
def alive(receipt):
 p=Path('/proc')/str(receipt['pid'])/'stat'
 if not p.exists():return False
 f=p.read_text().rsplit(')',1)[1].split();return f[0]!='Z' and f[19]==receipt['start_ticks']
try:
 note('WAITING_FOR_EXISTING_V2_FULL3062')
 while not (B/'endpoint115-full-motion-v3/validation.json').exists():
  p=B/'endpoint115-full-motion-v3/process.json'
  if not p.exists():p=B/'endpoint115-v3-launch-binding-v1/process.json'
  assert alive(json.loads(p.read_text())),'Existing controller unavailable without full receipt';time.sleep(300)
 runs={};tasks={}
 for label in ['v1','v3']:
  base=B/('endpoint115-full-motion-'+label);v=json.loads((base/'validation.json').read_text());m=json.loads((base/'manifest.json').read_text());assert digest(base/'manifest.json')==v['manifest_sha256'] and v['coverage_complete'] and v['expected']==3062;assert len(v['results'])==len({r['task_key'] for r in v['results']})==3062 and {r['task_key'] for r in v['results']}==set(m['task_keys']);runs[label]={'validation':v,'manifest':m,'base':base};tasks[label]={r['task_key']:r for r in v['results']}
 assert set(tasks['v1'])==set(tasks['v3'])
 for field in ['derivative_manifest_sha256','profile_path','profile_sha256','protocol']:
  assert runs['v1']['manifest'][field]==runs['v3']['manifest'][field],('Run protocol mismatch',field)
 reports=[];counts=collections.Counter();categories=collections.Counter();by_dataset=collections.defaultdict(collections.Counter);action_count=0;maximum=0.
 for key in sorted(tasks['v1']):
  actual={}
  for label in ['v1','v3']:
   row=tasks[label][key];assert digest(row['result_path'])==row['result_sha256'] and digest(row['audit_path'])==row['audit_sha256'];d=json.loads(Path(row['result_path']).read_text());a=json.loads(Path(row['audit_path']).read_text());assert d['task_key']==a['task_key']==key and a['result_sha256']==row['result_sha256'];assert a['status']==row['status'] and a['independent_replay'] and a['max_replay_error']<=1e-5;assert a['manifest_sha256']==d['guard_manifest_sha256'];assert len(d['actions'])==a['actions'] and len(d['positions'])==len(d['actions'])+1
   if a['status']=='PASS_STRICT_MOTION_REPLAY':assert not a['source_alerts'] and d['error'] is None
   else:assert a['status']=='FAILURE_PRESERVED' and d['error']
   actual[label]=(d,a)
  old,old_a=actual['v1'];new,new_a=actual['v3']
  for field in ['source_record_sha256','targets','rotation','mesh_sha256','scene_sha256','native_geometry_sha256','source_guard_mode']:
   assert old[field]==new[field],(key,field)
  op=old_a['status']=='PASS_STRICT_MOTION_REPLAY';np=new_a['status']=='PASS_STRICT_MOTION_REPLAY';transition='retained_pass' if op and np else 'recovered' if np else 'regressed' if op else 'still_failed';counts[transition]+=1;category='PASS' if np else new['error'];categories[category]+=1;by_dataset[key.split('|')[0]][transition]+=1;action_count+=new_a['actions'];maximum=max(maximum,new_a['max_replay_error']);reports.append({'task_key':key,'transition':transition,'old_error':old['error'],'new_error':new['error'],'v1_result_sha256':tasks['v1'][key]['result_sha256'],'v3_result_sha256':tasks['v3'][key]['result_sha256'],'v3_audit_sha256':tasks['v3'][key]['audit_sha256']})
 passed=counts['retained_pass']+counts['recovered'];result={'status':'COMPLETE_PAIRED3062_ALL_STRICT_PASS_PENDING_OTHER_GATES' if passed==3062 else 'COMPLETE_PAIRED3062_FAILURES_PRESERVED_NOT_ACCEPTED','scope':3062,'strict_v3_pass':passed,'strict_v3_fail':3062-passed,'transition_counts':dict(counts),'v3_failure_categories':dict(categories),'dataset_transitions':{k:dict(v) for k,v in by_dataset.items()},'v3_actions_independently_replayed':action_count,'max_v3_replay_error':maximum,'records':reports,'receipt_bindings':{label:digest(r['base']/'validation.json') for label,r in runs.items()},'script_sha256':digest(__file__),'formal_launch_allowed':False,'limits':'No mixing run successes, no task exclusions, no model re-evaluation selection. This is offline reachability evidence; environment, simulator protocol, model full evaluation and all publication gates remain separate.'}
 atomic_json(O/'validation.json',result);note(result['status'],strict_v3_pass=passed,strict_v3_fail=3062-passed,transition_counts=dict(counts))
except Exception as error:note('FAILED_PAIRED_AUDIT_PRESERVED',error=repr(error));raise
