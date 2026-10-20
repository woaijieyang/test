"""Original CPU PathFinder rebuild; one known contour parameter, full static gate."""
import os,sys,json,shlex,subprocess,datetime,time,resource
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
import psutil
while True:
    usage=psutil.cpu_percent(interval=1,percpu=True)
    idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i]<10 and i not in [1,2,6,7,8,12,18,20,22,24,27,30]]
    if idle:os.sched_setaffinity(0,[min(idle,key=lambda i:usage[i])]);break
    time.sleep(30)
O=R/'outputs/connectivity/eu6-contour01-v1';C=R/'.cache/eu6-contour01-v1';O.mkdir(exist_ok=False);C.mkdir(exist_ok=False)
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':list(os.sched_getaffinity(0))})
def note(status,**values):atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**values})
try:
    B=R/'upstream/habitat-sim/build';source=R/'tests/landmark_diagnostics/build_eu6_contour_cpu.cpp'
    original_cpp=R/'upstream/habitat-sim/src/esp/nav/PathFinder.cpp'
    item=next(x for x in json.loads((B/'compile_commands.json').read_text()) if x['file']==str(original_cpp))
    compile_args=shlex.split(item['command']);obj=C/'driver.o';compile_args[compile_args.index('-o')+1]=str(obj);compile_args[compile_args.index('-c')+1]=str(source)
    ref=R/'outputs/landmark-connectivity/recast626-isolated-binding-v1/validation.json';reference=json.loads(ref.read_text())
    link=list(reference['commands'][0]);link[link.index('-o')+1]=str(C/'builder');link=[x for x in link if x!='-shared' and not x.endswith('.o')];link.insert(1,str(obj))
    tracked=[original_cpp,B/'esp/nav/libnav.a',B/'deps/recastnavigation/Recast/libRecast.a',B/'deps/recastnavigation/Detour/libDetour.a'];before={str(p):digest(p) for p in tracked}
    atomic_json(O/'commands.json',{'compile':compile_args,'link':link,'source_sha256':digest(source),'original_inputs':before})
    note('COMPILING_ISOLATED_CPU_DRIVER')
    for label,cmd in [('compile',compile_args),('link',link)]:
        with (O/(label+'.log')).open('xb') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    parent=R/'data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json';profile=json.loads(parent.read_text());scene='EU6Fwq7SyZv';asset=profile['assets'][f'mp3d/{scene}/{scene}.glb']
    expected={'agent_height':1.5,'agent_radius':.1,'cell_size':.05,'cell_height':.05,'agent_max_climb':.2,'agent_max_slope':45.,'region_min_size':20.,'region_merge_size':20.,'edge_max_len':12.,'edge_max_error':1.3,'verts_per_poly':6.,'detail_sample_dist':6.,'detail_sample_max_error':1.,'filter_low_hanging_obstacles':True,'filter_ledge_spans':True,'filter_walkable_low_height_spans':True}
    assert set(asset['build_settings'])==set(expected)
    assert all(abs(float(asset['build_settings'][k])-float(v))<1e-6 for k,v in expected.items())
    catalog=json.loads((R/'outputs/landmark-connectivity/native-source-catalog-v1/catalog.json').read_text());native=next(r for r in catalog['scenes'] if r['scene']==scene)
    receipt=json.loads(Path(native['receipt_path']).read_text());assert receipt['scene_sha256']==asset['scene_sha256'];assert digest(native['native_geometry_path'])==native['native_geometry_sha256']
    meshes={}
    for mode in ['control','tight']:
        note('BUILDING_NATIVE_MESH',mode=mode)
        mesh=O/(mode+'.navmesh')
        with (O/(mode+'.log')).open('xb') as log:subprocess.run([str(C/'builder'),native['native_geometry_path'],str(mesh),mode],stdout=log,stderr=subprocess.STDOUT,check=True)
        meshes[mode]=digest(mesh)
        if mode=='control':assert meshes[mode]==asset['navmesh_sha256'],'BYTE_CONTROL_MISMATCH_NO_CANDIDATE_ADMISSION'
    assert before=={p:digest(p) for p in before}
    build={'status':'PASS_ORIGINAL_NATIVE_BYTE_CONTROL_SINGLE_CONTOUR_CANDIDATE','scene':scene,'mesh_hashes':meshes,'native_geometry_sha256':native['native_geometry_sha256'],'native_geometry_receipt_sha256':digest(native['receipt_path']),'original_settings':asset['build_settings'],'candidate_settings':{**asset['build_settings'],'edge_max_error':.1},'driver_sha256':digest(C/'builder'),'source_sha256':digest(source),'original_inputs_unchanged':True}
    atomic_json(O/'build-validation.json',build)
    folder=R/'data/derived/navmeshes/awarevln-eu6-contour01-v3';folder.mkdir(exist_ok=False)
    profile['profile_id']=folder.name;profile['status']='CONTOUR_DIAGNOSTIC_NOT_ADOPTED';profile['parent_profile_sha256']=digest(parent)
    asset.update(navmesh_path=str(O/'tight.navmesh'),navmesh_sha256=meshes['tight'],build_settings=build['candidate_settings'],build_receipt={'path':str(O/'build-validation.json'),'sha256':digest(O/'build-validation.json')})
    atomic_json(folder/'profile.json',profile)
    note('CHECKING_ALL_3062_ANNOTATIONS_AND_REFERENCE_PATHS')
    with (O/'static-full.log').open('xb') as log:
        code=subprocess.run([sys.executable,'-B','tests/audit_connectivity.py','--profile',str(folder/'profile.json'),'--output',str(O/'static-full.json')],stdout=log,stderr=subprocess.STDOUT).returncode
    full=json.loads((O/'static-full.json').read_text());assert full['counts']['tasks']==3062
    assert (code==0)==(full['status']=='PASS')
    note('COMPLETE_STATIC_GATE_PENDING_MOTION' if code==0 else 'CANDIDATE_STATIC_REJECTED',static_status=full['status'],invalid=full['unreachable_or_invalid_count'],profile_path=str(folder/'profile.json'),profile_sha256=digest(folder/'profile.json'))
except Exception as error:note('FAILED_PRESERVED',error=repr(error));raise

