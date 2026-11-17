"""Wait once for v36, then compare all786 against the492 validated v35 witnesses."""
import collections,datetime,json,os,sys,time
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
B=R/'outputs/landmark-connectivity';O=B/'D7-detail01-proof-comparison-v1';O.mkdir(exist_ok=False)
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
def note(status,**kw):atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**kw})
try:
    parent=B/'d7-tiled-detail01-v1';identity=json.loads((parent/'motion-continuation-process.json').read_text());audit_path=B/'D7-tiled-detail01-source-independent-v1/validation.json';note('WAITING_FOR_EXISTING_FULL_INDEPENDENT_AUDIT',continuation=identity)
    while not audit_path.exists():
        state=json.loads((parent/'motion-continuation-state.json').read_text());assert state['status']!='FAILED_CONTINUATION_PRESERVED',state
        proc=Path(f"/proc/{identity['pid']}/stat");assert proc.exists(),'continuation_exited_without_audit'
        fields=proc.read_text().rsplit(')',1)[1].split();assert fields[0]!='Z' and fields[19]==str(identity['start_ticks'])
        time.sleep(30)
    note('VERIFYING_FULL_COVERAGE_AND_PROOF_IDENTITIES')
    old_index_path=B/'D7-phasehalf-strict-proof-index-v2.json';old_index=json.loads(old_index_path.read_text());assert old_index['strict_proven']==492
    old_audits={}
    for name in ['D7-tiled-phasehalf-source-independent-v1','D7-phasehalf-strict-seed-84497-independent-v1']:
        p=B/name/'validation.json';old_audits[digest(p)]=json.loads(p.read_text())
    old_manifests={};old_sources={};old_records={}
    for proof in old_index['proofs']:
        folder=B/proof['run_id']/'guarded'
        if proof['run_id'] not in old_manifests:
            old_manifests[proof['run_id']]=json.loads((folder/'manifest.json').read_text())
            old_sources[proof['run_id']]={r['task_key']:r for r in json.loads((folder/'validation.json').read_text())['results']}
        m=old_manifests[proof['run_id']];assert digest(folder/'manifest.json')==proof['manifest_sha256'];assert m['profile_sha256']==old_index['profile_sha256']
        audited=next(r for r in old_audits[proof['independent_audit_sha256']]['records'] if r['task_key']==proof['task_key'])
        assert audited['status']=='LINEAR_CONTINUOUS_SOURCE_CLEAR_DIAGNOSTIC' and not audited['exact_guard_contradiction'] and audited['replay_error']<=1e-5
        source=old_sources[proof['run_id']][proof['task_key']];assert digest(source['result_path'])==source['sha256']==proof['source_result_sha256']==audited['source_result_sha256']
        old_records[proof['task_key']]={'proof':proof,'source':source,'result':json.loads(Path(source['result_path']).read_text()),'manifest':m}
    assert len(old_records)==492
    run=B/'full-source-guard-D7-tiled-detail01-v1/guarded';m=json.loads((run/'manifest.json').read_text());audit=json.loads(audit_path.read_text());producer=json.loads((run/'validation.json').read_text());rows={r['task_key']:r for r in audit['records']};sources={r['task_key']:r for r in producer['results']};expected={r['task_key'] for r in m['expected_tasks']}
    assert audit['full_scene_coverage'] and audit['scope_tasks']==audit['scene_tasks']==len(rows)==len(sources)==len(expected)==786
    assert set(rows)==set(sources)==expected and set(old_records)<=expected
    assert audit['source_guard_manifest_sha256']==digest(run/'manifest.json') and audit['source_validation_sha256']==digest(run/'validation.json')
    assert audit['source_guard_mode']==m['source_guard_mode']=='exact_continuous_linear_sweep'
    assert digest(m['profile_path'])==m['profile_sha256']
    for old in old_manifests.values():
        for key in ['body','actions','motion_gate','max_search_nodes','native_geometry','scene_sha256','source_guard_mode','sweep_helper_sha256','geometry_reference_sha256']:
            assert old[key]==m[key],('physical_contract_changed',key)
    new_results={};passed=set();failure_counts=collections.Counter()
    for key,row in rows.items():
        source=sources[key];assert digest(source['result_path'])==source['sha256']==row['source_result_sha256'];result=json.loads(Path(source['result_path']).read_text());assert result['task_key']==key;new_results[key]=result
        if row['status']=='SOURCE_CANDIDATE_BLOCKED_PRESERVED':
            assert not row['replayed'] and result['status']==row['status'];continue
        assert row['replayed'] and not row['exact_guard_contradiction'] and row['replay_error']<=1e-5
        assert result['guard_manifest_sha256']==digest(run/'manifest.json') and result['script_sha256']==m['worker_sha256']
        assert row['actions_replayed']==len(result['actions']) and row['hypothetical_step_count']==0
        if row['status']=='LINEAR_CONTINUOUS_SOURCE_CLEAR_DIAGNOSTIC':
            assert result['status']=='PASS_DIAGNOSTIC' and result['error'] is None and len(result['boundaries'])==len(result['targets'])-1
            assert row['actual_contact_count']==row['unresolved_transition_count']==0 and not row['native_gate_alerts'];passed.add(key)
        else:failure_counts[str(result.get('error'))]+=1
    old_passed=set(old_records);regressed=[]
    for key in sorted(old_passed-passed):
        old=old_records[key];new=new_results[key]
        regressed.append({'task_key':key,'new_status':rows[key]['status'],'new_error':new.get('error'),'same_targets':old['result']['targets']==new.get('targets'),'same_rotation':old['result']['rotation']==new.get('rotation'),'old_proof':old['proof'],'new_result_path':sources[key]['result_path'],'new_result_sha256':sources[key]['sha256']})
    new90=set(json.loads((B/'d7-tiled-phasehalf-v1/relative-to-mixed-v32.json').read_text())['recovered_from_prior']);assert len(new90)==90
    counts=dict(collections.Counter(r['status'] for r in rows.values()))
    output={'status':'COMPLETE_FULL786_COMPARISON_NOT_ADOPTED','scope_tasks':786,'global_denominator':33954,'prior_v35_proven':492,'candidate_strict_proven':len(passed),'old_proofs_retained':len(old_passed&passed),'recovered':sorted(passed-old_passed),'regressed':regressed,'new90_proven':sorted(new90&passed),'new90_unproven':sorted(new90-passed),'candidate_counts':counts,'failure_classes':dict(failure_counts),'candidate_profile_path':m['profile_path'],'candidate_profile_sha256':m['profile_sha256'],'candidate_proofs':[{'task_key':key,'source_result_sha256':rows[key]['source_result_sha256'],'actions':rows[key]['actions_replayed'],'replay_error':rows[key]['replay_error']} for key in sorted(passed)],'prior_index_sha256':digest(old_index_path),'candidate_independent_sha256':digest(audit_path),'candidate_manifest_sha256':digest(run/'manifest.json'),'script_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat(),'limits':'All786/33954 retained. Compares complete valid witnesses without merging profiles or rewriting failed attempts. Finite search failure is not physical impossibility. No formalmodel metric or adoption/publication claim.'}
    atomic_json(O/'validation.json',output);note('COMPLETE_FULL786_COMPARISON_NOT_ADOPTED',candidate_strict=len(passed),retained=len(old_passed&passed),recovered=len(passed-old_passed),regressed=len(old_passed-passed),new90_proven=len(new90&passed))
except Exception as error:note('FAILED_COMPARISON_PRESERVED',error=repr(error));raise

