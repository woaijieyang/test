"""Freeze and validate endpoint115; complete3062 native tasks and independent replays."""
import collections,concurrent.futures,datetime,fcntl,hashlib,json,os,subprocess,sys,threading,time
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import digest,atomic_json
from preflight import SPECS,load,task_key
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(10)
import psutil
O=R/'outputs/connectivity/endpoint115-full-motion-v2';O.mkdir(exist_ok=False);lock=(O/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
def note(status,**kwargs):atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**kwargs})
def execute(command,logpath,identity):
    with logpath.open('xb') as log:
        p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        stat=Path(f'/proc/{p.pid}/stat').read_text().rsplit(')',1)[1].split();atomic_json(logpath.with_suffix('.process.json'),{'pid':p.pid,'start_ticks':stat[19],**identity});return p.wait()
try:
    note('VERIFYING_MATERIALIZED_FULL_STATIC')
    assert json.loads((R/'outputs/connectivity/endpoint115-full-motion-v1/validation.json').read_text())['coverage_complete'], 'Prior full run must finish first'
    regression=R/'outputs/connectivity/endpoint115-horizontal-planner-regression-v1/validation.json';assert json.loads(regression.read_text())['status']=='PASS_NATIVE_RECORDED_OVERSTEP_REJECTION';assert json.loads(regression.read_text())['worker_v2_sha256']==digest(R/'tests/landmark_diagnostics/endpoint115_motion_worker_v2.py')
    D=R/'data/derived/annotations/awarevln-endpoint115-v1';dm=D/'manifest.json';bound=json.loads(dm.read_text());protocol=json.loads((D/'protocol.json').read_text());static=R/'outputs/connectivity/endpoint115-materialized-v1/independent-static-validation.json';sv=json.loads(static.read_text());assert sv['status']=='PASS_MATERIALIZED_ENDPOINTS_AND_REFERENCE_CONNECTIVITY' and sv['derivative_manifest_sha256']==digest(dm)
    assert all(digest(p)==h for p,h in bound['derived_files'].items())
    worker=R/'tests/landmark_diagnostics/endpoint115_motion_worker.py';auditor=R/'tests/landmark_diagnostics/audit_endpoint115_motion.py';helper=R/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';oracle=worker.with_name('robust_oracle.py');geometry=worker.with_name('projected_distance_reference.py');sweep=worker.with_name('swept_cylinder_reference.py');traversal=worker.with_name('audit_prb_step_interpretations.py')
    sources={str(p):digest(p) for p in [worker,auditor,helper,oracle,geometry,sweep,traversal,Path(__file__)]}
    catalog={r['scene']:r for r in json.loads((R/'outputs/landmark-connectivity/native-source-catalog-v1/catalog.json').read_text())['scenes']}
    tasks=[]
    for ds,spec in SPECS.items():
        ap=R/protocol['dataset_roots'][ds]/'val_unseen'/spec[1];annotation_sha=digest(ap)
        for ep in load(ap)['episodes']:
            if ds=='rxr' and ep['instruction']['language']!='en-US':continue
            points=[ep['start_position'],*ep.get('reference_path',[]),*[g['position'] for g in ep['goals']]]
            targets=[]
            for point in points:
                if not targets or point!=targets[-1]:targets.append(point)
            tasks.append({'task_key':task_key(ds,ep),'dataset':ds,'scene':ep['scene_id'].split('/')[1],'targets':targets,'start_rotation':ep['start_rotation'],'source_record_sha256':hashlib.sha256(json.dumps(ep,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),'annotation_sha256':annotation_sha})
    assert len(tasks)==3062 and len({t['task_key'] for t in tasks})==3062
    for folder in ['inputs','scenes','episodes','audits','logs']:(O/folder).mkdir()
    taskpaths={};taskhashes={};manifests={}
    for t in tasks:
        p=O/'inputs'/(hashlib.sha256(t['task_key'].encode()).hexdigest()[:24]+'.json');atomic_json(p,t);taskpaths[t['task_key']]=str(p);taskhashes[t['task_key']]=digest(p)
    for scene in sorted({t['scene'] for t in tasks}):
        selected=[t for t in tasks if t['scene']==scene];native=catalog[scene];geo=json.loads(Path(native['receipt_path']).read_text());m={'worker_sha256':digest(worker),'auditor_sha256':digest(auditor),'helper_sha256':digest(helper),'oracle_sha256':digest(oracle),'geometry_reference_sha256':digest(geometry),'sweep_helper_sha256':digest(sweep),'independent_sweep_traversal_sha256':digest(traversal),'profile_path':protocol['profile_path'],'profile_sha256':protocol['profile_sha256'],'scene_sha256':geo['scene_sha256'],'native_geometry':{'receipt_path':native['receipt_path'],'receipt_sha256':digest(native['receipt_path'])},'derivative_manifest_path':str(dm),'derivative_manifest_sha256':digest(dm),'static_validation_path':str(static),'static_validation_sha256':digest(static),'task_paths':{t['task_key']:taskpaths[t['task_key']] for t in selected},'task_files':{t['task_key']:taskhashes[t['task_key']] for t in selected}}
        path=O/'scenes'/(scene+'.json');atomic_json(path,m);manifests[scene]=str(path)
    atomic_json(O/'manifest.json',{'expected':3062,'datasets':{'r2r':1839,'rxr':1223},'task_keys':[t['task_key'] for t in tasks],'sources':sources,'derivative_manifest_sha256':digest(dm),'profile_path':protocol['profile_path'],'profile_sha256':protocol['profile_sha256'],'scene_manifests':{p:digest(p) for p in manifests.values()},'protocol':'Native primitive .25m/15deg; height1.5/radius.1; exact continuous straight sweep; .25m reference goal radius; vertical.5; horizontal.2501;5000nodes/search;1500actions/reference;10000actions/task. Original sparse references plus explicit terminal goal, consecutive exact duplicates collapsed. Dense GT is checked statically, not treated as thousands of new navigation targets. Offline Oracle only, formal model budget remains500.','strict_formal_launch_gate':'All3062 strict source/native/independent results required, plus environment and complete release gates; no automatic formal launch from partial success.'})
    while True:
        u=psutil.cpu_percent(interval=1,percpu=True);idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<15 and i not in [6,12,18,20,22,24,27,30]]
        if len(idle)>=4 and psutil.virtual_memory().available>=16*2**30:cpus=sorted(idle,key=lambda i:u[i])[:4];break
        note('WAITING_IDLE_CPUS');time.sleep(30)
    alloc=threading.Lock();free=list(cpus);stop=threading.Event();rows=[]
    def job(t):
        if stop.is_set():return None
        with alloc:cpu=free.pop()
        key=t['task_key'];tid=Path(taskpaths[key]).stem;result=O/'episodes'/(tid+'.json');audit=O/'audits'/(tid+'.json');m=manifests[t['scene']]
        try:
            assert all(digest(p)==h for p,h in sources.items())
            code=execute([sys.executable,'-B',str(worker),'--manifest',m,'--task-file',taskpaths[key],'--output',str(result),'--cpu',str(cpu)],O/'logs'/(tid+'.motion.log'),{'task_key':key,'cpu':cpu})
            assert code==0,('motion infrastructure',key,code)
            code=execute([sys.executable,'-B',str(auditor),'--manifest',m,'--result',str(result),'--output',str(audit),'--cpu',str(cpu)],O/'logs'/(tid+'.audit.log'),{'task_key':key,'cpu':cpu})
            assert code==0,('independent audit',key,code)
            v=json.loads(audit.read_text());assert v['task_key']==key
            return {'task_key':key,'status':v['status'],'error':v['error'],'error_kind':v['error_kind'],'result_path':str(result),'result_sha256':digest(result),'audit_path':str(audit),'audit_sha256':digest(audit)}
        except Exception as e:stop.set();return {'task_key':key,'status':'INFRASTRUCTURE_FAILURE','error':repr(e)}
        finally:
            with alloc:free.append(cpu)
    pilot=tasks[0];value=job(pilot);assert value and value['status']!='INFRASTRUCTURE_FAILURE',value;rows.append(value)
    note('RUNNING_FULL3062_STRICT_MOTION_AND_INDEPENDENT_REPLAY',records=1,cpu_ids=cpus)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(job,t) for t in tasks[1:]]
        for future in concurrent.futures.as_completed(futures):
            value=future.result()
            if value is None:continue
            rows.append(value);atomic_json(O/'results-index.json',rows);note('INFRASTRUCTURE_FAILURE' if stop.is_set() else 'RUNNING_FULL3062_STRICT_MOTION_AND_INDEPENDENT_REPLAY',records=len(rows),expected=3062,counts=dict(collections.Counter(r['status'] for r in rows)),cpu_ids=cpus)
    assert not stop.is_set() and len(rows)==3062 and {r['task_key'] for r in rows}==set(taskpaths)
    assert all(digest(p)==h for p,h in bound['source_files_unchanged'].items()) and all(digest(p)==h for p,h in bound['derived_files'].items())
    counts=dict(collections.Counter(r['status'] for r in rows));passed=counts.get('PASS_STRICT_MOTION_REPLAY',0)==3062
    atomic_json(O/'validation.json',{'status':'PASS_FULL3062_STRICT_MOTION_AND_REPLAY' if passed else 'COMPLETE_FULL3062_FAILURES_PRESERVED_NOT_ACCEPTED','expected':3062,'coverage_complete':True,'counts':counts,'results':rows,'manifest_sha256':digest(O/'manifest.json'),'formal_launch_allowed':False,'limits':'This offline gate alone never authorizes publication or proves model evaluation complete.'});note('PASS_FULL3062_STRICT_MOTION_AND_REPLAY' if passed else 'COMPLETE_FULL3062_FAILURES_PRESERVED_NOT_ACCEPTED',counts=counts)
except Exception as error:note('FAILED_PIPELINE_PRESERVED',error=repr(error));raise
