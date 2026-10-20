"""Bounded paired diagnosis of the sole old-proof regression; no result overwrite."""
import datetime,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
import psutil
B=R/'outputs/landmark-connectivity';comparison=json.loads((B/'D7-tiled-phasehalf-proof-comparison-v1/validation.json').read_text());assert comparison['regressed_strict_keys']==['train:84497'];row=comparison['regressions'][0];assert row['same_targets'] and row['same_rotation']
O=B/'D7-phasehalf-strict-seed-84497-v1';O.mkdir(exist_ok=False);run=O/'guarded';run.mkdir();(run/'episodes').mkdir();atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
def note(status,**kw):atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**kw})
try:
    previous=B/'full-source-guard-D7-tiled-mixed-v1/guarded';current=B/'full-source-guard-D7-tiled-phasehalf-v1/guarded';m=json.loads((current/'manifest.json').read_text());key='train:84497';tid=hashlib.sha256(key.encode()).hexdigest()[:24]
    worker=R/'tests/landmark_diagnostics/source_guard_strict_seed_worker.py';m['worker_sha256']=digest(worker);m['expected_tasks']=[r for r in m['expected_tasks'] if r['task_key']==key];assert len(m['expected_tasks'])==1;m['expected']=1;m['scope_mode']='targeted_probe';m['scope']='Single same-target/same-rotation oldstrict action proposal revalidated with actual newmesh motion, not model rerun or copied proof.'
    old_audit=B/'D7-tiled-mixed-source-independent-v1/validation.json'
    m['strict_action_seeds']={key:{'result_path':row['old_result_path'],'result_sha256':row['old_result_sha256'],'manifest_path':str(previous/'manifest.json'),'manifest_sha256':digest(previous/'manifest.json'),'independent_audit_path':str(old_audit),'independent_audit_sha256':digest(old_audit)}}
    m['original_full_attempt_manifest_sha256']=digest(current/'manifest.json');m['comparison_sha256']=digest(B/'D7-tiled-phasehalf-proof-comparison-v1/validation.json');atomic_json(run/'manifest.json',m)
    while True:
        u=psutil.cpu_percent(interval=1,percpu=True);idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<10 and i not in [6,12,18,20,22,24,27,30]]
        if idle:cpu=min(idle,key=lambda i:u[i]);break
        note('WAITING_FOR_IDLE_CPU');time.sleep(30)
    output=run/'episodes'/(tid+'.json');command=[sys.executable,'-B',str(worker),'--manifest',str(run/'manifest.json'),'--task-file',str(current/'inputs'/(tid+'.json')),'--output',str(output),'--cpu',str(cpu)]
    with (O/'worker.log').open('xb') as log:
        p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','PYTHONHASHSEED':'0'})
        note('RUNNING_BOUNDED_STRICT_SEED_DIAGNOSTIC',worker_pid=p.pid,worker_start_ticks=Path(f'/proc/{p.pid}/stat').read_text().rsplit(')',1)[1].split()[19],cpu=cpu);code=p.wait()
    assert code==0 and output.exists();d=json.loads(output.read_text());assert d['guard_manifest_sha256']==digest(run/'manifest.json') and d['script_sha256']==digest(worker)
    result={'task_key':key,'status':d['status'],'result_path':str(output),'sha256':digest(output),'actions':len(d['actions']),'error':d['error']};atomic_json(run/'results-index.json',[result]);atomic_json(run/'validation.json',{'status':'COMPLETE_TARGETED_DIAGNOSTIC_NOT_ACCEPTANCE','expected':1,'results':[result]})
    note('INDEPENDENT_SOURCE_AND_NATIVE_REPLAY')
    with (O/'independent.log').open('xb') as log:subprocess.run([sys.executable,'-B','tests/landmark_diagnostics/audit_tiled_source_guard.py','--source-run',O.name,'--targeted-scope','--scene','D7N2EKCX4Sj','--output-run','D7-phasehalf-strict-seed-84497-independent-v1'],stdout=log,stderr=subprocess.STDOUT,check=True)
    receipt=B/'D7-phasehalf-strict-seed-84497-independent-v1/validation.json';v=json.loads(receipt.read_text());assert len(v['records'])==1 and not v['records'][0]['exact_guard_contradiction']
    note('COMPLETE_TARGETED_EXISTENCE_DIAGNOSTIC_NOT_ADOPTION',counts=v['counts'],actions=len(d['actions']),independent_sha256=digest(receipt))
except Exception as error:note('FAILED_DIAGNOSTIC_PRESERVED',error=repr(error));raise

