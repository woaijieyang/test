"""Explicit new X7 recipe, not a guessed reconstruction of unknown original settings."""
import datetime,json,os,subprocess,sys,time
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
import psutil
while True:
    usage=psutil.cpu_percent(interval=1,percpu=True);idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i]<10 and i not in [1,2,6,7,8,12,18,20,22,24,27,30]]
    if idle:os.sched_setaffinity(0,[min(idle,key=lambda i:usage[i])]);break
    time.sleep(30)
B=R/'outputs/connectivity';O=B/'x7-explicit05-v1';O.mkdir(exist_ok=False)
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':list(os.sched_getaffinity(0))})
def note(status,**values):atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**values})
def run(command,label):
    with (O/(label+'.log')).open('xb') as log:
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        fields=Path(f'/proc/{child.pid}/stat').read_text().rsplit(')',1)[1].split();note(label,child_pid=child.pid,child_start_ticks=fields[19]);code=child.wait()
    return code
try:
    known=B/'eu6-contour01-v1/build-validation.json';verification=json.loads(known.read_text());builder=R/'.cache/eu6-contour01-v1/builder'
    assert digest(builder)==verification['driver_sha256'] and verification['status']=='PASS_ORIGINAL_NATIVE_BYTE_CONTROL_SINGLE_CONTOUR_CANDIDATE'
    parent=R/'data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json';profile=json.loads(parent.read_text());scene='X7HyMhZNoso';asset=profile['assets'][f'mp3d/{scene}/{scene}.glb'];assert asset['build_settings'] is None
    catalog=json.loads((R/'outputs/landmark-connectivity/native-source-catalog-v1/catalog.json').read_text());native=next(r for r in catalog['scenes'] if r['scene']==scene);receipt=json.loads(Path(native['receipt_path']).read_text());assert receipt['scene_sha256']==asset['scene_sha256'];assert digest(native['native_geometry_path'])==native['native_geometry_sha256']
    settings=verification['original_settings'];assert settings['agent_height']==1.5 and abs(settings['agent_radius']-.1)<1e-6 and abs(settings['agent_max_climb']-.2)<1e-6
    atomic_json(O/'rationale.json',{'status':'NEW_EXPLICIT_RECIPE_NOT_ORIGINAL_PARAMETER_RECONSTRUCTION','scene':scene,'original_settings':None,'original_mesh_sha256':asset['navmesh_sha256'],'new_settings':settings,'reason':'The sole unresolved formal endpoint has sourcefloor contact0.088-0.093m above foot and all673 current mesh candidates collide. Test a declared .05m vertical/horizontal native rebuild, preserving body/climb and originalgeometry, rather than enlarge displacement or alter source geometry.','cpu_driver_control_scope':'Same original native PathFinder driver reproduces EU6 byteexactly; this is a pipeline control, not evidence of originalX7 recipe equivalence.','source_geometry_sha256':native['native_geometry_sha256'],'prohibition':'No adoption or annotation changes; all3062 static and prospective endpoint/source checks required.'})
    mesh=O/'explicit05.navmesh';code=run([str(builder),native['native_geometry_path'],str(mesh),'control'],'BUILDING_NEW_EXPLICIT_RECIPE');assert code==0
    build={'status':'BUILT_NEW_DECLARED_RECIPE_PENDING_VALIDATION','scene':scene,'mesh_sha256':digest(mesh),'settings':settings,'source_geometry_sha256':native['native_geometry_sha256'],'source_geometry_receipt_sha256':digest(native['receipt_path']),'builder_sha256':digest(builder),'pipeline_control_sha256':digest(known),'original_recipe_unknown':True,'original_mesh_byte_equivalence_claimed':False}
    atomic_json(O/'build-validation.json',build)
    folder=R/'data/derived/navmeshes/awarevln-x7-explicit05-v3';folder.mkdir(exist_ok=False);profile['profile_id']=folder.name;profile['status']='EXPLICIT_X7_RECIPE_DIAGNOSTIC_NOT_ADOPTED';profile['parent_profile_sha256']=digest(parent);asset.update(navmesh_path=str(mesh),navmesh_sha256=digest(mesh),build_settings=settings,build_receipt={'path':str(O/'build-validation.json'),'sha256':digest(O/'build-validation.json')});atomic_json(folder/'profile.json',profile)
    code=run([sys.executable,'-B','tests/audit_connectivity.py','--profile',str(folder/'profile.json'),'--output',str(O/'static-full.json')],'CHECKING_ALL3062_STATIC')
    static=json.loads((O/'static-full.json').read_text());assert static['counts']['tasks']==3062
    if code!=0:
        assert static['status']=='FAIL';note('REJECTED_STATIC_GATE',invalid=static['unreachable_or_invalid_count'])
    else:
        assert static['status']=='PASS'
        assert run([sys.executable,'-B','tests/landmark_diagnostics/preview_formal_endpoint_repairs_v2.py'],'GENERATING_UNAPPLIED_ENDPOINT_PREVIEW')==0
        assert run([sys.executable,'-B','tests/landmark_diagnostics/verify_formal_endpoint_preview_v2.py'],'INDEPENDENT_ALL6124_PROSPECTIVE_CHECK')==0
        validation=B/'formal-endpoint-repair-preview-v2/independent-prospective-validation.json';v=json.loads(validation.read_text())
        note('COMPLETE_UNAPPLIED_PROSPECTIVE_CHECK_NOT_MOTION_ACCEPTANCE',counts=v['counts'],resolved=v['resolved_endpoint_changes'],validation_sha256=digest(validation))
except Exception as error:note('FAILED_PRESERVED',error=repr(error));raise

