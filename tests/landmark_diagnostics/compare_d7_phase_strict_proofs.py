"""One-shot, complete-scene proof comparison after the existing independent audit."""
import collections,datetime,json,os,sys,time
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
B=R/'outputs/landmark-connectivity';O=B/'D7-tiled-phasehalf-proof-comparison-v1';O.mkdir(exist_ok=False)
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
def note(status,**kw):atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**kw})
try:
    continuation=B/'d7-tiled-phasehalf-v1';identity=json.loads((continuation/'continuation-process.json').read_text())
    audit_path=B/'D7-tiled-phasehalf-source-independent-v1/validation.json'
    note('WAITING_FOR_EXISTING_INDEPENDENT_AUDIT',continuation=identity)
    while not audit_path.exists():
        state=json.loads((continuation/'continuation-state.json').read_text())
        assert state['status'] not in ['FAILED_CONTINUATION_PRESERVED','CANDIDATE_REJECTED_OR_NO_RECOVERY_NO_MOTION_LAUNCHED'],state
        p=Path(f"/proc/{identity['pid']}/stat");assert p.exists(),'continuation_exited_without_independent_receipt'
        fields=p.read_text().rsplit(')',1)[1].split();assert fields[0]!='Z' and fields[19]==str(identity['start_ticks'])
        time.sleep(30)
    note('VERIFYING_ALL786_IDENTITIES_AND_STRICT_GATES')
    old_index_path=B/'D7-tiled-mixed-strict-proof-index-v1.json';old_index=json.loads(old_index_path.read_text())
    old_audit_path=B/'D7-tiled-mixed-source-independent-v1/validation.json';assert digest(old_audit_path)==old_index['independent_audit_sha256']
    old_audit=json.loads(old_audit_path.read_text());new_audit=json.loads(audit_path.read_text())
    parent_path=B/'full-native-v11/manifest.json';parent=json.loads(parent_path.read_text());expected={r['task_key']:r for r in parent['tasks'] if r['scene']=='D7N2EKCX4Sj'};assert len(expected)==786
    all_rows={};all_manifests={};all_results={}
    for label,run,audit in [('old','full-source-guard-D7-tiled-mixed-v1',old_audit),('new','full-source-guard-D7-tiled-phasehalf-v1',new_audit)]:
        folder=B/run/'guarded';manifest=json.loads((folder/'manifest.json').read_text());producer=json.loads((folder/'validation.json').read_text())
        assert manifest['parent_manifest_sha256']==digest(parent_path)
        assert digest(folder/'manifest.json')==audit['source_guard_manifest_sha256'] and digest(folder/'validation.json')==audit['source_validation_sha256']
        assert audit['full_scene_coverage'] and audit['scene_tasks']==audit['scope_tasks']==786
        assert audit['source_guard_mode']=='exact_continuous_linear_sweep'
        rows={r['task_key']:r for r in audit['records']};results={r['task_key']:r for r in producer['results']}
        assert len(audit['records'])==len(producer['results'])==786 and set(rows)==set(results)==set(expected)
        assert digest(manifest['profile_path'])==manifest['profile_sha256']
        assert {r['task_key'] for r in manifest['expected_tasks']}==set(expected)
        for key,row in rows.items():
            source=results[key];assert digest(source['result_path'])==source['sha256']==row['source_result_sha256']
            result=json.loads(Path(source['result_path']).read_text());assert result['task_key']==key and result['source_record_sha256']==expected[key]['source_record_sha256']
            if row['status']=='SOURCE_CANDIDATE_BLOCKED_PRESERVED':
                assert not row['replayed'] and result['status']=='SOURCE_CANDIDATE_BLOCKED_PRESERVED'
                continue
            assert row['replayed'] and not row['exact_guard_contradiction']
            assert result['guard_manifest_sha256']==digest(folder/'manifest.json') and result['script_sha256']==manifest['worker_sha256']
            assert row['actions_replayed']==len(result['actions']) and row['replay_error']<=1e-5
            assert row['hypothetical_step_count']==0
            if row['status']=='LINEAR_CONTINUOUS_SOURCE_CLEAR_DIAGNOSTIC':
                assert result['status']=='PASS_DIAGNOSTIC' and result['error'] is None
                assert not row['native_gate_alerts'] and row['actual_contact_count']==row['unresolved_transition_count']==0
                assert len(result['boundaries'])==len(result['targets'])-1
        all_rows[label]=rows;all_manifests[label]=manifest;all_results[label]=results
    for key in ['body','actions','motion_gate','max_search_nodes','native_geometry','scene_sha256','worker_sha256','oracle_sha256','sweep_helper_sha256','geometry_reference_sha256']:
        assert all_manifests['old'][key]==all_manifests['new'][key],('unexpected_gate_or_code_change',key)
    strict=lambda label:{k for k,r in all_rows[label].items() if r['status']=='LINEAR_CONTINUOUS_SOURCE_CLEAR_DIAGNOSTIC'}
    previous,current=strict('old'),strict('new');assert len(previous)==470 and previous=={r['task_key'] for r in old_index['proofs']}
    new_static_recoveries=set(json.loads((continuation/'relative-to-mixed-v32.json').read_text())['recovered_from_prior']);assert len(new_static_recoveries)==90
    proofs=[{'task_key':key,'source_result_sha256':all_rows['new'][key]['source_result_sha256'],'actions':all_rows['new'][key]['actions_replayed'],'replay_error':all_rows['new'][key]['replay_error']} for key in sorted(current)]
    regressions=[]
    for key in sorted(previous-current):
        a=json.loads(Path(all_results['old'][key]['result_path']).read_text());b=json.loads(Path(all_results['new'][key]['result_path']).read_text())
        regressions.append({'task_key':key,'new_status':all_rows['new'][key]['status'],'new_error':b.get('error'),'new_error_kind':b.get('error_kind'),'old_actions':len(a['actions']),'new_actions':len(b.get('actions',[])),'old_references':len(a['boundaries']),'new_references':len(b.get('boundaries',[])),'same_targets':a['targets']==b.get('targets'),'same_rotation':a['rotation']==b.get('rotation'),'same_mesh':a['mesh_sha256']==b.get('mesh_sha256'),'old_result_path':all_results['old'][key]['result_path'],'old_result_sha256':all_results['old'][key]['sha256'],'new_result_path':all_results['new'][key]['result_path'],'new_result_sha256':all_results['new'][key]['sha256']})
    counts=dict(collections.Counter(r['status'] for r in all_rows['new'].values()))
    output={'status':'COMPLETE_PARTIAL_STRICT_PROOF_COMPARISON_NOT_ADOPTED','scope_tasks':786,'global_denominator':33954,'old_strict_proven':470,'new_strict_proven':len(current),'new_counts':counts,'recovered_strict_keys':sorted(current-previous),'regressed_strict_keys':sorted(previous-current),'old_strict_retained':len(current&previous),'original6_retained':sorted(set(old_index['newly_recovered_static_tasks'])&current),'new90_proven':sorted(new_static_recoveries&current),'new90_failed':sorted(new_static_recoveries-current),'strict_proofs':proofs,'regressions':regressions,'old_index_sha256':digest(old_index_path),'new_independent_audit_sha256':digest(audit_path),'old_independent_audit_sha256':digest(old_audit_path),'script_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat(),'limits':'Complete fixed786 denominator and strict-source receipts checked. Search failure is not physical impossibility. Static90 recovery is separated from executed proofs. Different profile/targets/planning are not a causal model-SR claim. All33954/held114 remain; no production adoption or publication.'}
    atomic_json(O/'validation.json',output);note('COMPLETE_PARTIAL_COMPARISON_NOT_ADOPTED',new_strict=len(current),recovered=len(current-previous),regressed=len(previous-current),new90_proven=len(new_static_recoveries&current))
except Exception as error:note('FAILED_COMPARISON_PRESERVED',error=repr(error));raise

