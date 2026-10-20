"""One predeclared detail-height factor, with exact control and gated full-scene continuation."""
import datetime,json,os,subprocess,sys,time
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
import psutil
while True:
    usage=psutil.cpu_percent(interval=1,percpu=True);idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i]<10 and i not in [6,12,18,20,22,24,27,30]]
    if idle:os.sched_setaffinity(0,[min(idle,key=lambda i:usage[i])]);break
    time.sleep(30)
B=R/'outputs/landmark-connectivity';O=B/'d7-tiled-detail01-v1';C=R/'.cache/d7-tiled-detail01-v1';O.mkdir(exist_ok=False);C.mkdir(exist_ok=False)
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':list(os.sched_getaffinity(0))})
def note(status,**kw):atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**kw})
def execute(command,label,env=None):
    with (O/(label+'.log')).open('xb') as log:
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,env=env)
        stat=Path(f'/proc/{child.pid}/stat').read_text().rsplit(')',1)[1].split();note(label,child_pid=child.pid,child_start_ticks=stat[19]);code=child.wait()
    assert code==0,(label,code)
try:
    previous=B/'d7-tiled-phasehalf-v1';compile_receipt=json.loads((previous/'compile-command.json').read_text());archives=compile_receipt['original_archives'];assert all(digest(p)==h for p,h in archives.items())
    source=R/'tests/landmark_diagnostics/build_tiled_detail_scene.cpp';header=R/'tests/landmark_diagnostics/tiled_recast_builder_detail.h';command=[str(source) if p.endswith('/build_tiled_phase_scene.cpp') else p for p in compile_receipt['command']];command[command.index('-o')+1]=str(C/'builder');atomic_json(O/'compile-command.json',{'command':command,'source_sha256':digest(source),'header_sha256':digest(header),'original_archives':archives,'rationale_sha256':digest(B/'D7-detail-height-rationale-v1.json')});execute(command,'COMPILE_ISOLATED_BUILDER')
    native=next(r for r in json.loads((B/'native-source-catalog-v1/catalog.json').read_text())['scenes'] if r['scene']=='D7N2EKCX4Sj');assert digest(native['native_geometry_path'])==native['native_geometry_sha256'];rule=json.loads((previous/'spatial-rule.json').read_text());patch=rule['coarse_patch_xz'];atomic_json(O/'spatial-rule.json',{**rule,'inherited_rule_sha256':digest(previous/'spatial-rule.json'),'detail_error_factor':.1,'grid_phase_xz_m':-.0125})
    for label,factor in [('control','1'),('mixed','0.1')]:
        directory=O/label;directory.mkdir();command=[str(C/'builder'),native['native_geometry_path'],str(directory),'mixed','2',*[str(x) for x in patch],'-0.0125'];env={**os.environ,'CASE1_DETAIL_ERROR_FACTOR':factor};execute(command,'BUILD_'+label.upper(),env)
        assert digest(directory/'input-copy.bin')==native['native_geometry_sha256'];tiles=[json.loads(x) for x in (directory/'tiles.jsonl').read_text().splitlines()]
        assert all(abs(r['detail_sample_max_error_m']-.05*float(factor))<1e-8 for r in tiles)
        if label=='control':
            assert digest(directory/'scene.navmesh')==digest(previous/'mixed/scene.navmesh'),'CONTROL_MESH_MISMATCH'
            before=[json.loads(x) for x in (previous/'mixed/tiles.jsonl').read_text().splitlines()];assert [{k:v for k,v in r.items() if k!='detail_sample_max_error_m'} for r in tiles]==before
            atomic_json(O/'control-validation.json',{'status':'PASS_V35_MESH_BYTE_IDENTICAL_CONTROL','mesh_sha256':digest(directory/'scene.navmesh'),'old_tile_fields_identical':True,'actual_detail_error_factor':1,'new_metadata_field':'detail_sample_max_error_m'})
        else:
            atomic_json(directory/'build-validation.json',{'status':'BUILT_SINGLE_FACTOR_CANDIDATE_NOT_ADOPTED','mode':'mixed','mesh_sha256':digest(directory/'scene.navmesh'),'source_geometry_sha256':native['native_geometry_sha256'],'actual_detail_error_factor':.1,'actual_detail_max_error_m':.005,'tile_manifest_sha256':digest(directory/'tiles.jsonl'),'source_sha256':digest(source),'header_sha256':digest(header),'builder_sha256':digest(C/'builder'),'control_receipt_sha256':digest(O/'control-validation.json')})
    assert all(digest(p)==h for p,h in archives.items())
    execute([sys.executable,'-B','tests/landmark_diagnostics/audit_tiled_detail_headers.py'],'AUDIT_HEADERS')
    parent=R/'data/derived/navmeshes/landmark-d7-tiled-phasehalf-mixed-v35/profile.json';profile=json.loads(parent.read_text());folder=R/'data/derived/navmeshes/landmark-d7-tiled-detail01-v36';folder.mkdir(exist_ok=False);profile['profile_id']=folder.name;profile['status']='DETAIL_HEIGHT_DIAGNOSTIC_NOT_ADOPTED';profile['parent_profile_sha256']=digest(parent);asset=profile['assets']['mp3d/D7N2EKCX4Sj/D7N2EKCX4Sj.glb'];asset.update(navmesh_path=str(O/'mixed/scene.navmesh'),navmesh_sha256=digest(O/'mixed/scene.navmesh'),build_receipt={'path':str(O/'mixed/build-validation.json'),'sha256':digest(O/'mixed/build-validation.json')});asset['build_settings'].update(detail_sample_max_error=.1,per_tile_settings_path=str(O/'mixed/tiles.jsonl'),per_tile_settings_sha256=digest(O/'mixed/tiles.jsonl'));atomic_json(folder/'profile.json',profile)
    proposal='D7-grounded-tiled-detail01-v1'
    execute([sys.executable,'-B','tests/landmark_diagnostics/probe_source_bounded_scene_profile_v3.py','--scene','D7N2EKCX4Sj','--profile',str(folder/'profile.json'),'--geometry-receipt',native['receipt_path'],'--run',proposal],'ALL786_SOURCE_STATIC')
    execute([sys.executable,'-B','tests/landmark_diagnostics/audit_source_bounded_scene_candidates_v3.py','--run',proposal],'INDEPENDENT_ALL786_STATIC')
    old=json.loads((B/'D7-grounded-tiled-phasehalf-mixed-v1/validation.json').read_text());new=json.loads((B/proposal/'validation.json').read_text());ready=lambda v:{r['task_key'] for r in v['rows'] if r['status']=='SOURCE_CLEAR_TARGETS_COMMON_COMPONENT_PENDING_MOTION'};a,b=ready(old),ready(new);assert len(a)==762 and len(new['rows'])==len(old['rows'])==786;delta={'old_ready':len(a),'new_ready':len(b),'recovered':sorted(b-a),'regressed':sorted(a-b),'new_static_sha256':digest(B/proposal/'independent-static.json')};atomic_json(O/'relative-to-v35.json',delta)
    if a-b:
        note('REJECTED_STATIC_REGRESSION_NOT_ADOPTED',**delta)
    else:
        execute([sys.executable,'-B','tests/landmark_diagnostics/audit_d7_detail01_corridors.py'],'ALL90_NATIVE_CORRIDOR_SOURCE_CHECK')
        corridor=B/'D7-detail01-new90-native-corridors-v1/validation.json';cv=json.loads(corridor.read_text());counts=cv['counts'];atomic_json(O/'corridor-gate.json',{'status':'CORRIDOR_IMPROVEMENT_PENDING_MOTION' if counts['nominal_source_clear_tasks']>0 else 'NO_COMPLETE_NOMINAL_CORRIDOR_RECOVERY','counts':counts,'source_sha256':digest(corridor)})
        if counts['nominal_source_clear_tasks']==0:
            note('COMPLETE_DIAGNOSTIC_NO_NOMINAL_CORRIDOR_RECOVERY_NOT_ADOPTED',static=delta,corridors=counts)
        else:
            full='full-source-guard-D7-tiled-detail01-v1';audit='D7-tiled-detail01-source-independent-v1';assert not (B/full).exists() and not (B/audit).exists()
            # Restore a broad affinity so the existing controller can choose its four idle CPUs.
            os.sched_setaffinity(0,list(range(min(64,os.cpu_count()))))
            execute([sys.executable,'-B','tests/landmark_diagnostics/run_tiled_candidate_source_guard.py','--scene','D7N2EKCX4Sj','--proposal',proposal,'--run',full],'FULL786_SOURCE_GUARD')
            execute([sys.executable,'-B','tests/landmark_diagnostics/audit_tiled_source_guard.py','--source-run',full,'--scene','D7N2EKCX4Sj','--output-run',audit],'INDEPENDENT_FULL786_REPLAY')
            v=json.loads((B/audit/'validation.json').read_text());assert len(v['records'])==786;note('COMPLETE_FULL_SCENE_CANDIDATE_NOT_ADOPTED',counts=v['counts'],independent_sha256=digest(B/audit/'validation.json'))
except Exception as error:note('FAILED_PRESERVED',error=repr(error));raise

