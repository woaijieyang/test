"""Continue after correcting a coarse-corridor proxy that cannot test detail-height motion."""
import datetime,json,os,subprocess,sys
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
B=R/'outputs/landmark-connectivity';O=B/'d7-tiled-detail01-v1'
assert not (O/'motion-continuation-process.json').exists()
atomic_json(O/'motion-continuation-process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
def note(status,**kw):atomic_json(O/'motion-continuation-state.json',{'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**kw})
def execute(command,label):
    with (O/(label+'.log')).open('xb') as log:
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        fields=Path(f'/proc/{child.pid}/stat').read_text().rsplit(')',1)[1].split();note(label,child_pid=child.pid,child_start_ticks=fields[19]);code=child.wait()
    assert code==0,(label,code)
try:
    scope=json.loads((O/'corridor-screen-scope-review-v2.json').read_text());effect=json.loads((O/'native-detail-effect-v2.json').read_text());structure=json.loads((O/'structure-comparison-v2.json').read_text());delta=json.loads((O/'relative-to-v35.json').read_text())
    assert scope['status']=='COARSE_CORRIDOR_PROXY_INSUFFICIENT_FOR_DETAIL_MOTION_EFFECT' and scope['evidence_sha256']==digest(O/'native-detail-effect-v2.json')
    assert effect['changed_queries']==829 and effect['unique_queries']==2126
    assert structure['base_vertices_identical'] and structure['polygons_identical'] and structure['links_identical']
    assert not delta['regressed'] and delta['old_ready']==delta['new_ready']==762
    assert json.loads((O/'control-validation.json').read_text())['status']=='PASS_V35_MESH_BYTE_IDENTICAL_CONTROL'
    proposal='D7-grounded-tiled-detail01-v1';assert json.loads((B/proposal/'independent-static.json').read_text())['status']=='PASS_PROPOSAL_IDENTITY_BOUNDS_BODY_AND_CONNECTIVITY_NOT_MOTION'
    full='full-source-guard-D7-tiled-detail01-v1';audit='D7-tiled-detail01-source-independent-v1';assert not (B/full).exists() and not (B/audit).exists()
    command=[sys.executable,'-B','tests/landmark_diagnostics/run_tiled_candidate_source_guard.py','--scene','D7N2EKCX4Sj','--proposal',proposal,'--run',full]
    atomic_json(O/'motion-gate-scope-correction.json',{'status':'EXPERIMENT_SELECTION_PROXY_CORRECTED_PHYSICAL_GATES_UNCHANGED','original_controller_state_sha256':digest(O/'state.json'),'original_coarse_corridor_failures_sha256':digest(O/'corridor-gate.json'),'native_effect_sha256':digest(O/'native-detail-effect-v2.json'),'structure_sha256':digest(O/'structure-comparison-v2.json'),'reason':'Native movement changed in829/2126 identical queries while coarse graph unchanged. A coarse shortest-polyline source failure does not test the changed detail heights used by actual movement. No contact, body, budget, coverage or replay acceptance test is removed or weakened.','command':command,'time':datetime.datetime.now().astimezone().isoformat()})
    execute(command,'FULL786_DETAIL_MOTION')
    execute([sys.executable,'-B','tests/landmark_diagnostics/audit_tiled_source_guard.py','--source-run',full,'--scene','D7N2EKCX4Sj','--output-run',audit],'INDEPENDENT_FULL786_DETAIL_REPLAY')
    validation=B/audit/'validation.json';v=json.loads(validation.read_text());assert len(v['records'])==786
    note('COMPLETE_DETAIL_MOTION_CANDIDATE_NOT_ADOPTED',counts=v['counts'],validation_sha256=digest(validation))
except Exception as error:note('FAILED_CONTINUATION_PRESERVED',error=repr(error));raise

