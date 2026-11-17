"""Publication-only Landmark gate. Does not run navigation or mutate evidence."""
import hashlib,json,math
from pathlib import Path

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def validate_report(v):
 assert v['status']=='PASS','Landmark validation not PASS'
 assert v['coverage_complete'] is True,'Landmark coverage incomplete'
 c=v['counts'];assert c.get('PASS',0)==33954,'All 33954 original tasks must pass'
 assert c.get('STATIC_BLOCKED_PRESERVED',0)==0 and c.get('FAIL',0)==0,'Unresolved Landmark tasks'
 assert not v['audit_issues'] and not v['failure_kinds'],'Landmark audit or motion failures'
 e=v['max_independent_replay_error'];assert isinstance(e,(float,int)) and math.isfinite(e) and 0<=e<=1e-5,'Invalid replay error'
 assert c.get('actual_actions',0)>0,'Missing actual native motion'
 expected={'train':26464,'val_seen':2939,'val_unseen':4551}
 assert set(v['split_counts'])==set(expected),'Unexpected split set'
 for name,total in expected.items():
  split=v['split_counts'][name];assert split.get('PASS',0)==total and split.get('FAIL',0)==split.get('STATIC_BLOCKED_PRESERVED',0)==0,'Split coverage/failure mismatch'


def validate_geometry_report(g, tasks, manifest_sha256, profile_sha256, native_validation_sha256, native_actions):
 """Require exact source-geometry evidence for the same complete native task set."""
 assert g.get('status')=='PASS' and g.get('coverage_complete') is True,'Source geometry acceptance incomplete'
 assert g.get('verification_mode')=='exact_continuous_linear','Sampled or hypothetical-step geometry is not accepted by this gate'
 assert g.get('manifest_sha256')==manifest_sha256 and g.get('profile_sha256')==profile_sha256,'Source geometry identity drift'
 assert g.get('native_validation_sha256')==native_validation_sha256,'Source geometry/native audit binding drift'
 body=g.get('body',{});assert body.get('height')==1.5 and abs(body.get('radius',0)-.1)<=1e-8,'Source geometry body mismatch'
 assert g.get('foot_epsilon_m')==1e-5 and g.get('radial_epsilon_m')==1e-6,'Source geometry tolerance drift'
 assert g.get('audit_issues')==[] and g.get('unresolved')==[],'Missing or unresolved source geometry review'
 expected={t['task_key']:t for t in tasks};rows=g.get('records',[]);assert len(rows)==len(expected)==len(tasks) and len({r['task_key'] for r in rows})==len(rows) and {r['task_key'] for r in rows}==set(expected),'Source geometry task coverage mismatch'
 def sha(value):return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)
 actions=0
 for row in rows:
  t=expected[row['task_key']];assert row.get('status')=='PASS','Source geometry failed task hidden'
  assert row.get('scene')==t['scene'] and row.get('source_record_sha256')==t['source_record_sha256'],'Source task identity mismatch'
  assert row.get('geometry_kind')=='NATIVE_LOADER_EXPORTED_TRIANGLES','Source parser geometry lacks native confirmation'
  assert sha(row.get('native_trace_sha256')) and sha(row.get('geometry_sha256')),'Missing source/trace identity'
  for field in ['actual_position_contacts','continuous_linear_contacts','hypothetical_step_segments']:
   assert type(row.get(field)) is int and row[field]==0,'Source contact or unapproved curve remains'
  n=row.get('actual_actions');assert type(n) is int and n>=0,'Invalid source action count';actions+=n
 assert actions==native_actions and actions>0,'Source/native action coverage mismatch'

def require_acceptance(root):
 root=Path(root).resolve();base=root/'outputs/landmark-connectivity';a=json.loads((base/'acceptance.json').read_text());assert a['status']=='PASS','User-requested Landmark repair not accepted'
 def owned(value):
  p=Path(value);p=(p if p.is_absolute() else root/p).resolve();assert root in p.parents,'Evidence escapes case1';return p
 run=owned(a['full_native_run']);assert base.resolve() in run.parents,'Unexpected Landmark run location'
 for receipt in a['receipts']:assert digest(owned(receipt['path']))==receipt['sha256'],'Landmark receipt drift'
 vp=run/'validation.json';assert any(owned(r['path'])==vp and r['sha256']==digest(vp) for r in a['receipts']),'Latest validation not receipted'
 v=json.loads(vp.read_text());validate_report(v)
 mpath=run/'manifest.json';m=json.loads(mpath.read_text());binding=json.loads((run/'validation-code-binding.json').read_text());assert digest(mpath)==v['manifest_sha256']==binding['manifest_sha256'],'Manifest binding drift'
 assert digest(owned(binding['actual_validator_path']))==v['validator_sha256']==binding['actual_validator_sha256'],'Validator code drift'
 assert len(m['tasks'])==len({t['task_key'] for t in m['tasks']})==33954,'Missing or duplicate task identity'
 assert all(t['status']=='READY_FOR_NATIVE_MOTION' for t in m['tasks']),'Static failures hidden in manifest'
 assert digest(owned(m['profile_path']))==m['profile_sha256'],'Profile drift'
 assert a.get('geometry_review_required') is False,'Source geometry review is not cleared'
 receipt=a.get('source_geometry_acceptance');assert isinstance(receipt,dict) and 'path' in receipt and 'sha256' in receipt,'Missing full source geometry acceptance'
 geometry_path=owned(receipt['path']);assert digest(geometry_path)==receipt['sha256'],'Source geometry receipt drift'
 assert any(owned(r['path'])==geometry_path and r['sha256']==receipt['sha256'] for r in a['receipts']),'Source geometry acceptance not receipted'
 g=json.loads(geometry_path.read_text());validator_path=owned(g['validator_path']);assert digest(validator_path)==g['validator_sha256'],'Source geometry validator drift'
 validate_geometry_report(g,m['tasks'],v['manifest_sha256'],m['profile_sha256'],digest(vp),v['counts']['actual_actions'])
 return {'status':'PASS','run':str(run),'episodes':33954,'validation_sha256':digest(vp)}
