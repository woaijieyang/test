"""Full132-case isolated collision-response experiment; no formal adoption."""
import concurrent.futures,datetime,json,os,subprocess,sys,time
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
import psutil
B=R/'outputs/connectivity';O=B/'eu6-source-collision-response-v1';O.mkdir(exist_ok=False)
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
def note(status,**kw):atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**kw})
try:
    fixture=B/'source-collision-filter-fixtures-v2/validation.json';f=json.loads(fixture.read_text());assert f['direction_cases']==12 and f['guarded_primitive_actions']==144 and f['initial_invalid_rejections']==2
    prior=B/'eu6-contour-motion-factorial-v1';m=json.loads((prior/'manifest.json').read_text());assert len(m['records'])==132
    worker=R/'tests/landmark_diagnostics/formal_scene_collision_filter_worker.py';filter_path=R/'tests/landmark_diagnostics/source_collision_filter.py';assert digest(filter_path)==f['filter_sha256']
    old_conditions=m['conditions'];m['conditions']={'source_filter_original_native':old_conditions['original_control'],'source_filter_height_native':old_conditions['height_only']}
    m.update(scope='Full132 isolated sourcecollision response. NOT formal baseline or adopted runtime; original annotations unchanged.',worker_sha256=digest(worker),filter_sha256=digest(filter_path),native_fixture_sha256=digest(fixture),original_manifest_sha256=digest(prior/'manifest.json'),initial_failure_policy='Preserve all initial sourceblockers without executing an invalidinitialpose',model_policy_changed=False,simulator_response_changed=True)
    atomic_json(O/'manifest.json',m)
    while True:
        usage=psutil.cpu_percent(interval=1,percpu=True);idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i]<10 and i not in [1,2,6,7,8,12,18,20,22,24,27,30]]
        if len(idle)>=2 and psutil.virtual_memory().available>8*2**30:cpus=sorted(idle,key=lambda i:usage[i])[:2];break
        note('WAITING_FOR_IDLE_CPUS');time.sleep(30)
    def execute(label,cpu):
        assert digest(worker)==m['worker_sha256'] and digest(filter_path)==m['filter_sha256']
        env={**os.environ,'PYTHONPATH':m['conditions'][label]['pythonpath'],'PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
        command=[sys.executable,'-B',str(worker),'--manifest',str(O/'manifest.json'),'--condition',label,'--cpu',str(cpu)]
        with (O/(label+'.log')).open('xb') as log:
            p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,stdin=subprocess.DEVNULL)
            atomic_json(O/(label+'-launch.json'),{'pid':p.pid,'start_ticks':Path(f'/proc/{p.pid}/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':cpu,'command':command})
            code=p.wait()
        assert code==0,(label,code)
        v=json.loads((O/label/'validation.json').read_text());assert v['expected']==132
        return label,v
    note('RUNNING_FULL132_RESPONSE_DIAGNOSTIC',cpu_ids=cpus)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        pending=[pool.submit(execute,label,cpu) for label,cpu in zip(m['conditions'],cpus)]
        conditions=dict(p.result() for p in pending)
    original=json.loads((prior/'original_control/validation.json').read_text());old_clear={r['task_key'] for r in original['records'] if r['status']=='STRICT_SOURCE_CLEAR_OPENLOOP_ONLY'};assert len(old_clear)==18
    summaries=[]
    for label,v in conditions.items():
        rows={r['task_key']:r for r in v['records']};assert len(rows)==132 and set(rows)=={r['task_key'] for r in m['records']}
        executed=[r for r in rows.values() if r.get('executed')];blocked=[r for r in rows.values() if r['status']=='INITIAL_SOURCE_BLOCKED_PRESERVED'];assert len(executed)+len(blocked)==132 and len(blocked)==12
        assert all(r['status']=='STRICT_SOURCE_CLEAR_OPENLOOP_ONLY' and r['replay_error']<=1e-5 for r in executed)
        if label=='source_filter_original_native':assert all(rows[k]['max_difference_from_original']<=1e-5 for k in old_clear)
        summaries.append({'condition':label,'all_records':132,'executed':len(executed),'initial_source_blocked':len(blocked),'rejected_native_proposals':sum(r['filter_rejections'] for r in executed),'actual_primitive_actions':sum(r['actions'] for r in executed),'changed_tasks':sum(r['max_difference_from_original']>1e-5 for r in executed),'actual_contacts':sum(r['body_contact_count'] for r in executed),'continuous_contacts':sum(r['chord_contact_count'] for r in executed),'native_offmesh':sum(r['offmesh_count'] for r in executed),'validation_sha256':digest(O/label/'validation.json')})
    atomic_json(O/'validation.json',{'status':'COMPLETE_EXPERIMENTAL_RESPONSE_SAFETY_DIAGNOSTIC_NOT_ACCEPTANCE','conditions':summaries,'manifest_sha256':digest(O/'manifest.json'),'script_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat(),'limits':'Different simulator collisionresponse, not adopted. No taskremoved and no initialposition moved. Fixed oldmodel actions are not newmodel inference; no goalcompletion/SR/efficiency claim. Fullroute reachability, independent event verification and any needed protocoldecision remain prerequisites.'})
    note('COMPLETE_EXPERIMENTAL_RESPONSE_NOT_ADOPTED',conditions=summaries)
except Exception as error:note('FAILED_DIAGNOSTIC_PRESERVED',error=repr(error));raise

