"""Frozen three-case key refinement diagnostic; no formal evaluator changes."""
import datetime, hashlib, json, os, subprocess, sys, time
from pathlib import Path
R=Path.cwd()
sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
import psutil
assert os.environ.get('CASE1_PROTECTION')
os.environ['CUDA_VISIBLE_DEVICES']=''
os.nice(15)
B=R/'outputs/landmark-connectivity'
source=B/'D7-search-key-diagnostic-v1'
selection=json.loads((source/'selection.json').read_text())
review=json.loads((source/'refinement-source-review.json').read_text())
assert digest(source/'independent-replay.json')==review['counterexample_receipt_sha256']
worker=R/'tests/landmark_diagnostics/source_guard_tiled_two_step_worker.py'
assert digest(worker)==review['new_worker_sha256']
old=B/'full-source-guard-D7-tiled-mixed-v1/guarded'
assert digest(old/'manifest.json')==selection['old_guard_manifest_sha256']
O=B/'D7-search-two-step-key-v1'
O.mkdir(exist_ok=False)
run=O/'guarded'
run.mkdir()
for name in ['episodes','logs']:(run/name).mkdir()
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
def note(status,**values):
    atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**values})
try:
    selected={r['task_key'] for r in selection['tasks']}
    m=json.loads((old/'manifest.json').read_text())
    m['expected_tasks']=[t for t in m['expected_tasks'] if t['task_key'] in selected]
    assert len(m['expected_tasks'])==3
    m.update(worker_sha256=digest(worker),expected=3,scope_mode='targeted_probe',
             scope='Three-case search key diagnostic, whole33954 denominator retained; not scene adoption.',
             key_refinement_source_review_sha256=digest(source/'refinement-source-review.json'),
             original_guard_manifest_sha256=digest(old/'manifest.json'))
    atomic_json(run/'manifest.json',m)
    while True:
        usage=psutil.cpu_percent(interval=1,percpu=True)
        idle=[c for c in sorted(os.sched_getaffinity(0))[:64] if usage[c]<10]
        if idle and psutil.virtual_memory().available>4*2**30:
            cpu=min(idle,key=lambda c:usage[c]);break
        note('WAITING_FOR_IDLE_CPU');time.sleep(30)
    rows=[]
    for selected_row in selection['tasks']:
        key=selected_row['task_key'];tid=hashlib.sha256(key.encode()).hexdigest()[:24]
        result=run/'episodes'/(tid+'.json')
        assert digest(worker)==m['worker_sha256']
        command=[sys.executable,'-B',str(worker),'--manifest',str(run/'manifest.json'),
                 '--task-file',str(old/'inputs'/(tid+'.json')),'--output',str(result),'--cpu',str(cpu)]
        with (run/'logs'/(tid+'.log')).open('xb') as log:
            p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,
                               env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','PYTHONHASHSEED':'0'})
            stat=Path(f'/proc/{p.pid}/stat').read_text().rsplit(')',1)[1].split()
            identity={'pid':p.pid,'start_ticks':stat[19],'task_key':key,'cpu':cpu}
            atomic_json(run/'logs'/(tid+'.process.json'),identity)
            note('RUNNING_TARGETED_KEY_DIAGNOSTIC',worker=identity,completed=len(rows))
            code=p.wait()
        assert code==0 and result.exists(),('worker_failure',key,code)
        d=json.loads(result.read_text())
        assert d['guard_manifest_sha256']==digest(run/'manifest.json') and d['script_sha256']==digest(worker)
        assert d['error_kind']!='INFRASTRUCTURE_FAILURE'
        rows.append({'task_key':key,'status':d['status'],'actions':len(d['actions']),
                     'error':d['error'],'result_path':str(result),'sha256':digest(result)})
        atomic_json(run/'results-index.json',rows)
    assert {r['task_key'] for r in rows}==selected
    atomic_json(run/'validation.json',{'status':'COMPLETE_TARGETED_DIAGNOSTIC_NOT_ACCEPTED','expected':3,
                                     'global_denominator':33954,'results':rows,'manifest_sha256':digest(run/'manifest.json')})
    note('INDEPENDENT_REPLAY_AND_SOURCE_AUDIT',completed=3)
    auditor=R/'tests/landmark_diagnostics/audit_tiled_source_guard.py'
    command=[sys.executable,'-B',str(auditor),'--source-run',O.name,'--targeted-scope',
             '--scene','D7N2EKCX4Sj','--output-run','D7-search-two-step-key-independent-v1']
    with (O/'audit.log').open('xb') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    validation=B/'D7-search-two-step-key-independent-v1/validation.json'
    v=json.loads(validation.read_text())
    assert len(v['records'])==3 and not any(r['exact_guard_contradiction'] for r in v['records'])
    note('COMPLETE_TARGETED_KEY_DIAGNOSTIC_NOT_ACCEPTANCE',completed=3,
         counts=v['counts'],independent_validation_sha256=digest(validation))
except Exception as e:
    note('FAILED',error=repr(e));raise

