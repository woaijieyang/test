"""Full132-task factorial diagnosis: mesh contour and native height fallback."""
import concurrent.futures,datetime,json,os,subprocess,sys,time
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
import psutil
B=R/'outputs/connectivity';O=B/'eu6-contour-motion-factorial-v1';O.mkdir(exist_ok=False)
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
def note(status,**values):atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**values})
try:
    build=B/'eu6-contour01-v1';assert json.loads((build/'state.json').read_text())['status']=='COMPLETE_STATIC_GATE_PENDING_MOTION'
    assert json.loads((build/'static-full.json').read_text())['status']=='PASS'
    baseline=R/'data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json'
    contour=R/'data/derived/navmeshes/awarevln-eu6-contour01-v3/profile.json'
    binding_receipt=json.loads((B/'pathfinder-height-boundary-binding-v2/validation.json').read_text());assert binding_receipt['status']=='PASS_ISOLATED_BINARY_CONTROL_AND_IMPORT'
    native_catalog=json.loads((R/'outputs/landmark-connectivity/native-source-catalog-v1/catalog.json').read_text());native=next(r for r in native_catalog['scenes'] if r['scene']=='EU6Fwq7SyZv');assert digest(native['native_geometry_path'])==native['native_geometry_sha256']
    original_run=R/'outputs/awarevln-r2r-valunseen-endpoint9-20261015-v2'
    records=[r for r in map(json.loads,(original_run/'results.jsonl').read_text().splitlines()) if '|mp3d/EU6Fwq7SyZv/EU6Fwq7SyZv.glb|' in r['task_key']];assert len(records)==132
    for row in records:row['trace_path']=str(original_run/row['trace_path']);assert digest(row['trace_path'])==row['trace_sha256']
    helper=R/'tests/landmark_diagnostics/audit_prb_step_interpretations.py';bound=json.loads((R/'outputs/landmark-connectivity/pRb-original-trace-step-interpretation-v1/validation.json').read_text());assert digest(helper)==bound['script_sha256']
    worker=R/'tests/landmark_diagnostics/formal_scene_openloop_worker.py'
    conditions={}
    for label,profile,patched in [('original_control',baseline,False),('contour_only',contour,False),('height_only',baseline,True),('contour_and_height',contour,True)]:
        conditions[label]={'profile_path':str(profile),'profile_sha256':digest(profile),'binding_sha256':binding_receipt['patched_binding_sha256' if patched else 'control_binding_sha256'],'pythonpath':str(R/'.cache/pathfinder-height-boundary-binding-v2/patched') if patched else str(R/'.cache/pathfinder-height-boundary-binding-v1/control')}
    m={'scope':'Complete132 R2R scene action replay, not modelevaluation or adoption','scene_id':'mp3d/EU6Fwq7SyZv/EU6Fwq7SyZv.glb','records':records,'original_run_manifest_sha256':digest(original_run/'run_manifest.json'),'original_results_sha256':digest(original_run/'results.jsonl'),'conditions':conditions,'worker_sha256':digest(worker),'native_geometry_path':native['native_geometry_path'],'native_geometry_sha256':native['native_geometry_sha256'],'native_geometry_receipt_path':native['receipt_path'],'native_geometry_receipt_sha256':digest(native['receipt_path']),'sweep_traversal_path':str(helper),'sweep_traversal_sha256':digest(helper),'static_full_receipt_sha256':digest(build/'static-full.json'),'height_binding_receipt_sha256':digest(B/'pathfinder-height-boundary-binding-v2/validation.json'),'global_landmark_denominator_unchanged':33954}
    atomic_json(O/'manifest.json',m)
    while True:
        usage=psutil.cpu_percent(interval=1,percpu=True);idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i]<10 and i not in [1,2,6,7,8,12,18,20,22,24,27,30]]
        if len(idle)>=2 and psutil.virtual_memory().available>8*2**30:cpus=sorted(idle,key=lambda i:usage[i])[:2];break
        note('WAITING_FOR_IDLE_CPUS');time.sleep(30)
    def execute(label,cpu):
        assert digest(worker)==m['worker_sha256']
        env={**os.environ,'PYTHONPATH':conditions[label]['pythonpath'],'PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
        cmd=[sys.executable,'-B',str(worker),'--manifest',str(O/'manifest.json'),'--condition',label,'--cpu',str(cpu)]
        with (O/(label+'.log')).open('xb') as log:
            p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,env=env)
            atomic_json(O/(label+'-launch.json'),{'pid':p.pid,'start_ticks':Path(f'/proc/{p.pid}/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':cpu,'command':cmd})
            code=p.wait()
        assert code==0,(label,code)
        result=json.loads((O/label/'validation.json').read_text());assert result['expected']==132 and result['manifest_sha256']==digest(O/'manifest.json')
        return label
    note('VERIFYING_ORIGINAL_NATIVE_REPLAY_ALL132',cpu_ids=cpus)
    execute('original_control',cpus[0])
    note('RUNNING_FULL_SCENE_FACTORIAL',cpu_ids=cpus)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(execute,'contour_only',cpus[0]),pool.submit(execute,'height_only',cpus[1])]
        for future in futures:future.result()
    execute('contour_and_height',cpus[0])
    results={label:{r['task_key']:r for r in json.loads((O/label/'validation.json').read_text())['records']} for label in conditions}
    clean=lambda label:{k for k,r in results[label].items() if r['status']=='STRICT_SOURCE_CLEAR_OPENLOOP_ONLY'}
    control=clean('original_control');summaries=[]
    for label in conditions:
        rows=list(results[label].values());passed=clean(label)
        summaries.append({'condition':label,'expected':132,'strict_clear_tasks':len(passed),'offmesh_positions':sum(r['offmesh_count'] for r in rows),'body_contact_positions':sum(r['body_contact_count'] for r in rows),'contact_chords':sum(r['chord_contact_count'] for r in rows),'changed_tasks':sum(r['max_difference_from_original']>1e-5 for r in rows),'recovered_from_original':sorted(passed-control),'regressed_from_original':sorted(control-passed),'validation_sha256':digest(O/label/'validation.json')})
    atomic_json(O/'validation.json',{'status':'COMPLETE_FULL132_FACTORIAL_DIAGNOSTIC_NOT_ACCEPTANCE','conditions':summaries,'manifest_sha256':digest(O/'manifest.json'),'script_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat(),'limits':'No model inference or metrics. Identical saved model actions were executed in each condition. All132 retained; native/source failures and changes preserved, independently initialized in-worker replay. New protocol requires separate broader validation and formal reruns before adoption.'})
    note('COMPLETE_FULL132_FACTORIAL_DIAGNOSTIC_NOT_ACCEPTANCE')
except Exception as error:note('FAILED_DIAGNOSTIC_PRESERVED',error=repr(error));raise

