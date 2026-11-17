"""Bind full pRb evidence and compare every identity against both strict baselines."""
import sys,json,datetime
from pathlib import Path
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import digest,atomic_json
from scene_evidence_comparison import compare,CLEAR
B=R/'outputs/landmark-connectivity';parent_path=B/'full-native-v11/manifest.json';parent=json.loads(parent_path.read_text());expected={t['task_key']:t for t in parent['tasks'] if t['scene']=='pRbA3pwrgk9'};assert len(expected)==660
original_path=B/'full-source-guard-pRbA3pwrgk9-v1-continuous-v1/validation.json';original=json.loads(original_path.read_text());index_path=B/'prb-v17-continuous-proof-index-v1.json';index=json.loads(index_path.read_text());assert original['scene_tasks']==index['scene_denominator']==660
assert len(original['records'])==len(index['records'])==660 and {r['task_key'] for r in original['records']}=={r['task_key'] for r in index['records']}==set(expected)
old_pass={r['task_key'] for r in original['records'] if r['status']==CLEAR};v17_pass={r['task_key'] for r in index['records'] if r['status']==CLEAR};assert len(old_pass)==60 and len(v17_pass)==85 and old_pass<=v17_pass
proofs={}
for r in index['records']:
 p=Path(r['proof']).resolve();assert p.is_relative_to(B.resolve())
 if str(p) not in proofs:
  d=json.loads(p.read_text());assert digest(p) in [index['base_audit_sha256'],index['regression_audit_sha256']];proofs[str(p)]={q['task_key']:q for q in d['records']}
 q=proofs[str(p)][r['task_key']];assert q['status']==r['status'] and q['source_result_sha256']==r['source_result_sha256']
run=B/'full-source-guard-pRb-detail-exact-v1';audit_path=B/'full-source-guard-pRb-detail-exact-v1-independent/validation.json';audit=json.loads(audit_path.read_text());mp=run/'guarded/manifest.json';m=json.loads(mp.read_text());vp=run/'guarded/validation.json';v=json.loads(vp.read_text());assert audit['scene_tasks']==audit['scope_tasks']==m['expected']==660 and audit['full_scene_coverage'];assert audit['source_guard_mode']==m['source_guard_mode']=='exact_continuous_linear_sweep';assert audit['source_guard_manifest_sha256']==v['manifest_sha256']==digest(mp) and audit['source_validation_sha256']==digest(vp) and audit['script_sha256']==digest(R/'tests/landmark_diagnostics/audit_guarded_continuous_routes_v3.py');assert m['parent_manifest_sha256']==digest(parent_path)
for k in ['body','actions','motion_gate']:assert m[k]==parent[k]
raw_rows={r['task_key']:r for r in v['results']};assert len(v['results'])==len(raw_rows)==660 and set(raw_rows)==set(expected)
for r in audit['records']:
 raw=raw_rows[r['task_key']];p=Path(raw['result_path']).resolve();assert p.is_relative_to(run.resolve()) and digest(p)==raw['sha256']==r['source_result_sha256'];d=json.loads(p.read_text());assert d['source_record_sha256']==expected[r['task_key']]['source_record_sha256'] and d['guard_manifest_sha256']==digest(mp)
 if r['status']==CLEAR:assert r['replayed'] and r['replay_error']<=1e-5 and r['actual_contact_count']==r['unresolved_transition_count']==r['hypothetical_step_count']==0
result=compare(expected,{'original_strict60':old_pass,'experimental_v17_strict85':v17_pass},audit['records']);result.update(status='COMPLETE_FULL_SCENE_IDENTITY_COMPARISON_NOT_GLOBAL_ACCEPTANCE',candidate_profile_sha256=m['profile_sha256'],original_audit_sha256=digest(original_path),v17_index_sha256=digest(index_path),candidate_audit_sha256=digest(audit_path),parent_manifest_sha256=digest(parent_path),script_sha256=digest(__file__),comparison_helper_sha256=digest(R/'tests/landmark_diagnostics/scene_evidence_comparison.py'),time=datetime.datetime.now(datetime.timezone.utc).isoformat(),protocol_note='Different diagnostic navmesh/derived target protocols compared for retained source-record feasibility only. No model score or SR gain claim; all660 tasks retained. More passes do not excuse lost prior proofs.')
out=B/'prb-detail-nonregression-v1.json';assert not out.exists();atomic_json(out,result);print({k:result[k] for k in ['denominator','candidate_strict_passed','all_baselines_preserved','all_tasks_strict']})
