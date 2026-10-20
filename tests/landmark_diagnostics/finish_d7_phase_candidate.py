"""One-shot continuation: only a nonregressing full-scene candidate gets motion tests."""
import datetime,json,os,subprocess,sys,time
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
assert os.environ.get('CASE1_PROTECTION')
B=R/'outputs/landmark-connectivity';O=B/'d7-tiled-phasehalf-v1'
assert O.exists() and not (O/'continuation-process.json').exists()
atomic_json(O/'continuation-process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
def state(status,**values):atomic_json(O/'continuation-state.json',{'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**values})
def run(command,label):
    with (O/(label+'.log')).open('xb') as log:
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        stat=Path(f'/proc/{child.pid}/stat').read_text().rsplit(')',1)[1].split()
        state(label,child_pid=child.pid,child_start_ticks=stat[19])
        code=child.wait()
    assert code==0,(label,code)
try:
    identity=json.loads((O/'process.json').read_text())
    state('WAITING_FOR_EXISTING_STATIC_CONTROLLER',controller=identity)
    while not (O/'validation.json').exists():
        observed=json.loads((O/'state.json').read_text())
        assert observed['status']!='FAILED',observed
        proc=Path(f"/proc/{identity['pid']}/stat")
        assert proc.exists(),'static_controller_disappeared_without_validation'
        fields=proc.read_text().rsplit(')',1)[1].split()
        assert fields[0]!='Z' and fields[19]==str(identity['start_ticks']),'static_controller_identity_changed'
        time.sleep(30)
    controls=json.loads((O/'zero-phase-control.json').read_text())
    assert controls['status']=='PASS_THREE_BYTE_IDENTICAL_CONTROLS'
    headers=json.loads((O/'header-audit.json').read_text())
    assert headers['status']=='PASS_ALL_TILE_BODY_HEADER_IDENTITY_AND_NO_OFFMESH_LINKS'
    proposal=B/'D7-grounded-tiled-phasehalf-mixed-v1'
    old_proposal=B/'D7-grounded-tiled-mixed-v1'
    old=json.loads((old_proposal/'validation.json').read_text())
    new=json.loads((proposal/'validation.json').read_text())
    ready=lambda report:{r['task_key'] for r in report['rows'] if r['status']=='SOURCE_CLEAR_TARGETS_COMMON_COMPONENT_PENDING_MOTION'}
    prior,current=ready(old),ready(new)
    assert len(prior)==672 and len(old['rows'])==len(new['rows'])==786
    transition=json.loads((proposal/'static-transition-audit.json').read_text())
    delta={'prior_ready':len(prior),'candidate_ready':len(current),'recovered_from_prior':sorted(current-prior),'regressed_from_prior':sorted(prior-current),
           'old_report_sha256':digest(old_proposal/'validation.json'),'new_report_sha256':digest(proposal/'validation.json')}
    atomic_json(O/'relative-to-mixed-v32.json',delta)
    if prior-current or not current-prior or transition['regressed']:
        state('CANDIDATE_REJECTED_OR_NO_RECOVERY_NO_MOTION_LAUNCHED',**delta)
    else:
        assert transition['status']=='STATIC_NONREGRESSION_WITH_RECOVERY_PENDING_MOTION'
        static=json.loads((proposal/'independent-static.json').read_text())
        assert static['status']=='PASS_PROPOSAL_IDENTITY_BOUNDS_BODY_AND_CONNECTIVITY_NOT_MOTION'
        full='full-source-guard-D7-tiled-phasehalf-v1'
        audit='D7-tiled-phasehalf-source-independent-v1'
        assert not (B/full).exists() and not (B/audit).exists()
        command=[sys.executable,'-B','tests/landmark_diagnostics/run_tiled_candidate_source_guard.py','--scene','D7N2EKCX4Sj','--proposal',proposal.name,'--run',full]
        sources={p:digest(R/p) for p in ['tests/landmark_diagnostics/run_tiled_candidate_source_guard.py','tests/landmark_diagnostics/source_guard_tiled_candidate_worker.py','tests/landmark_diagnostics/audit_tiled_source_guard.py']}
        atomic_json(O/'motion-launch-receipt.json',{'command':command,'sources':sources,'candidate_static_sha256':digest(proposal/'independent-static.json'),'relative_comparison_sha256':digest(O/'relative-to-mixed-v32.json'),'global_denominator':33954,'scope':786})
        run(command,'RUNNING_COMPLETE_SCENE_SOURCE_GUARD')
        assert all(digest(R/p)==h for p,h in sources.items())
        run([sys.executable,'-B','tests/landmark_diagnostics/audit_tiled_source_guard.py','--source-run',full,'--scene','D7N2EKCX4Sj','--output-run',audit],'INDEPENDENT_COMPLETE_SCENE_REPLAY')
        report=json.loads((B/audit/'validation.json').read_text())
        assert len(report['records'])==786
        state('COMPLETE_FULL_SCENE_CANDIDATE_NOT_GLOBAL_ACCEPTANCE',counts=report['counts'],independent_validation_sha256=digest(B/audit/'validation.json'))
except Exception as error:
    state('FAILED_CONTINUATION_PRESERVED',error=repr(error));raise

