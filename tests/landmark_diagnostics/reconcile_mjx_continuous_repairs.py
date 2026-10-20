"""Reconcile all594 mJX tasks without overwriting any historical attempt or count."""
import json,hashlib,datetime
from pathlib import Path
B=Path('outputs/landmark-connectivity')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
base=B/'mjx-composite-continuous-v1';repair=B/'mjx-continuous-contact-repair-v1';ind=B/'mjx-continuous-contact-repair-v1-independent'
a=read(base/'validation.json');am=read(base/'manifest.json');b=read(ind/'validation.json');m=read(repair/'guarded/manifest.json');rv=read(repair/'guarded/validation.json');parent=read(B/'full-native-v11/manifest.json')
assert a['full_scene_coverage'] and a['scope_tasks']==594 and a['source_guard_manifest_sha256']==sha(base/'manifest.json')
assert b['scope_tasks']==70 and b['scene_tasks']==594 and not b['full_scene_coverage'] and b['source_guard_mode']=='exact_continuous_linear_sweep'
assert b['source_guard_manifest_sha256']==sha(repair/'guarded/manifest.json')==rv['manifest_sha256'] and b['source_validation_sha256']==sha(repair/'guarded/validation.json')
assert m['parent_manifest_sha256']==am['parent_manifest_sha256']==sha(B/'full-native-v11/manifest.json') and m['profile_sha256']==am['profile_sha256']==parent['profile_sha256']
original={t['task_key']:t for t in parent['tasks'] if t['scene']=='mJXqzFtmKg4'};old={r['task_key']:r for r in a['records']};new={r['task_key']:r for r in b['records']};results={r['task_key']:r for r in rv['results']};assert len(original)==len(old)==594 and set(original)==set(old)
selected={k for k,r in old.items() if r.get('source_guard_status')=='PASS_DIAGNOSTIC' and r['status']!='LINEAR_CONTINUOUS_SOURCE_CLEAR_DIAGNOSTIC'};assert selected==set(new)==set(results) and len(selected)==70
rows=[]
for key,t in original.items():
 r=new[key] if key in new else old[key];report=ind/(key.replace(':','-')+'.json') if key in new else base/(key.replace(':','-')+'.json');assert report.exists();detail=read(report);assert detail['task_key']==key and detail['status']==r['status']
 if key in new:
  result=results[key];rp=Path(result['result_path']);assert sha(rp)==result['sha256']==r['source_result_sha256'];raw=read(rp);assert raw['source_record_sha256']==t['source_record_sha256'] and raw['targets']==t['targets'] and raw['guard_manifest_sha256']==sha(repair/'guarded/manifest.json')
 if r['status']=='LINEAR_CONTINUOUS_SOURCE_CLEAR_DIAGNOSTIC':assert r['replayed'] and r['replay_error']<=1e-5 and r['actual_contact_count']==r['unresolved_transition_count']==r['hypothetical_step_count']==0
 rows.append({'task_key':key,'source_record_sha256':t['source_record_sha256'],'status':r['status'],'evidence_path':str(report),'evidence_sha256':sha(report),'new_execution':key in new,'previous_status':old[key]['status']})
from collections import Counter
counts=dict(Counter(r['status'] for r in rows));recovered=set(read(B/'full-native-v11/static-transition-audit.json')['recovered']);new45=dict(Counter(r['status'] for r in rows if r['task_key'] in recovered));assert sum(new45.values())==45 and sum(counts.values())==594
out=B/'mJX-exact-continuous-proof-index-v1.json';assert not out.exists()
payload={'status':'COMPOSITE_EXACT_CONTINUOUS_PARTIAL_PROOF_NOT_GLOBAL_ACCEPTANCE','scene':'mJXqzFtmKg4','expected':594,'global_denominator':33954,'counts':counts,'new45_counts':new45,'unresolved':[r['task_key'] for r in rows if r['status']!='LINEAR_CONTINUOUS_SOURCE_CLEAR_DIAGNOSTIC'],'records':rows,'parent_manifest_sha256':sha(B/'full-native-v11/manifest.json'),'profile_sha256':parent['profile_sha256'],'base_audit_sha256':sha(base/'validation.json'),'repair_audit_sha256':sha(ind/'validation.json'),'script_sha256':sha(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'All594 identities retained. Only exact continuous clear and independently replayed traces are proof. Original11 failures and every repair failure retained. No model score or global acceptance and no step-protocol substitution.'}
out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'counts':counts,'new45_counts':new45,'unresolved':len(payload['unresolved'])}))
