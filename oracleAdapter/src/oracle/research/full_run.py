"""Streamed, resumable full validation with owned process identities and permits."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import signal
import math

from oracle.common.artifacts import digest,owned_output,require_sources,timestamp,write_json
from oracle.common.journal import ResultJournal
from oracle.common.task_index import verify_entry


class IntegrityStop(RuntimeError):pass

STARTUP_POLL_SECONDS = 0.05
EXIT_WAIT_SECONDS = 2.


def live(identity,proc_root=Path('/proc')):
    path=Path(proc_root)/str(identity['pid'])/'stat'
    try:fields=path.read_text().rsplit(')',1)[1].split()
    except FileNotFoundError:return False
    return fields[0]!='Z' and fields[19]==str(identity['start_ticks'])


def signal_owned(identity,sig):
    if not hasattr(os,'pidfd_open') or not hasattr(signal,'pidfd_send_signal'):
        raise IntegrityStop('Owned timeout requires pidfd support; refusing an unpinned PID signal')
    try:descriptor=os.pidfd_open(identity['pid'])
    except ProcessLookupError:return False
    try:
        if not live(identity):return False
        try:signal.pidfd_send_signal(descriptor,sig)
        except ProcessLookupError:return False
        return True
    finally:os.close(descriptor)


def wait_for_phase_exit(start, own, granted, wall_limit):
    """Use our child handle for prompt exit detection; keep identity safety.

    A timeout of Popen.wait is only an observation interval. The pre-existing
    permit-based phase deadline and pidfd termination rules remain unchanged.
    Recovered phases without a Popen handle retain identity-based polling.
    """
    if own is not None and own.pid != start['pid']:
        raise IntegrityStop('Startup PID differs from owned process handle')
    while live(start):
        remaining=wall_limit+15-(time.monotonic()-granted)
        if remaining < 0:
            signal_owned(start,signal.SIGTERM);time.sleep(3)
            if live(start):signal_owned(start,signal.SIGKILL);time.sleep(2)
            if live(start):raise IntegrityStop('Owned timeout termination still pending; do not duplicate work')
            break
        interval=min(EXIT_WAIT_SECONDS,max(.001,remaining))
        if own is None:
            time.sleep(interval)
        else:
            try:own.wait(timeout=interval)
            except subprocess.TimeoutExpired:pass
    if own is not None:
        if own.poll() is None:
            raise IntegrityStop('Owned process still alive without its expected PID/start identity')
        own.wait()


def phase_charge(directory,cap,observed=None):
    directory=Path(directory);end=directory/'exit.json';settled=directory/'settled-cost.json'
    if settled.exists():
        record=json.loads(settled.read_text())
        if record['exit_sha256']!=(digest(end) if end.exists() else None):raise IntegrityStop('Settled exit evidence changed')
        return record['charged_cpu_upper_bound_seconds']
    if not end.exists():return cap
    record=json.loads(end.read_text())
    # The exit receipt is written before interpreter teardown. One pinned CPU
    # cannot consume more than elapsed wall time after that receipt.
    tail=max(0.,(time.monotonic() if observed is None else observed)-record['ended_monotonic'])
    return min(cap,record['process_cpu_seconds']+tail)


def settle_phase(directory,cap):
    directory=Path(directory);value=phase_charge(directory,cap)
    if not (directory/'settled-cost.json').exists():
        write_json(directory/'settled-cost.json',{'charged_cpu_upper_bound_seconds':value,
            'exit_sha256':digest(directory/'exit.json') if (directory/'exit.json').exists() else None,
            'settled_at':timestamp(),'scope':'Observed completion bound, retained across resume; not growing with later idle time'})
    return value


def has_execution_result(directory):
    preflight=directory/'preflight.json'
    if not preflight.exists():return False
    data=json.loads(preflight.read_text())
    return not data['native_ready'] or (directory/'motion/result.json').exists()


class Budget:
    def __init__(self,limit,initial):self.limit=limit;self.values=dict(initial);self.lock=threading.Lock()
    def reserve(self,key,cap):
        with self.lock:
            if key not in self.values:
                if sum(self.values.values())+cap>self.limit:raise RuntimeError('Full-run CPU budget reservation exhausted')
                self.values[key]=cap
    def settle(self,key,value):
        with self.lock:self.values[key]=value
    def charged(self):
        with self.lock:return sum(self.values.values())


def budget_worker_cap(limit,charged,phase_cap,active=0):
    """Each new concurrent slot needs one full phase reservation.

    Existing phases have already been charged; never evict them to satisfy
    this launch cap. This does not alter the budget or a worker's limits.
    """
    if (any(not math.isfinite(v) for v in (limit,charged,phase_cap))
            or limit<0 or charged<0 or phase_cap<=0 or type(active) is not int or active<0):
        raise ValueError('Invalid phase reservation accounting')
    return active+int(max(0.,limit-charged)//phase_cap)


def run(case_root,manifest_path,dispatch_limit=None):
    import fcntl
    import psutil
    import resource
    root=Path(case_root).resolve();manifest_path=Path(manifest_path).resolve();study=owned_output(root,manifest_path.parent)
    manifest=json.loads(manifest_path.read_text());require_sources(manifest['sources']);msha=digest(manifest_path)
    if digest(study/'tasks.jsonl')!=manifest['tasks_file_sha256'] or digest(study/'index.json')!=manifest['index_sha256']:raise ValueError('Full inputs changed')
    lock=(study/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    entries=json.loads((study/'index.json').read_text());keys=[verify_entry(e,manifest['task_merkle_root'],manifest['task_count'])['task_key'] for e in entries]
    if len(keys)!=manifest['task_count'] or len(set(keys))!=len(keys):raise ValueError('Index coverage changed')
    if (study/'validation.json').exists():return json.loads((study/'validation.json').read_text())
    config=manifest['config'];cap=config['per_process_wall_seconds']+5
    controllers=study/'controllers';controllers.mkdir(exist_ok=True)
    number=len(list(controllers.glob('[0-9][0-9][0-9][0-9].json')))+1
    process={'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],
             'started_at':timestamp(),'manifest_sha256':msha,'reserved_cpu_seconds':3605,'dispatch_limit':dispatch_limit}
    resource.setrlimit(resource.RLIMIT_CPU,(3600,3605))
    write_json(controllers/f'{number:04}.json',process);write_json(study/'controller-process.json',process,immutable=False)
    write_json(study/'source-freeze.json',{'status':'OPEN','manifest_sha256':msha},immutable=False)
    initial={str(p):json.loads(p.read_text())['reserved_cpu_seconds'] for p in controllers.glob('[0-9][0-9][0-9][0-9].json')}
    # Reserve existing phase costs before dispatching anything new, including orphans.
    for p in (study/'jobs').glob('*/*/*/intent.json') if (study/'jobs').exists() else []:
        initial[str(p.parent)]=phase_charge(p.parent,cap)
    budget=Budget(config['total_cpu_budget_hours']*3600,initial)
    active_jobs={}
    for p in (study/'jobs').glob('*/*/*/start.json') if (study/'jobs').exists() else []:
        identity=json.loads(p.read_text())
        if live(identity):active_jobs[identity['entry']['task_key']]=identity['cpu']
    usage=psutil.cpu_percent(interval=1,percpu=True)
    allowed=sorted(os.sched_getaffinity(0))[:64]
    if any(cpu not in allowed for cpu in active_jobs.values()):raise IntegrityStop('Existing worker outside allowed CPU set')
    idle=[i for i in allowed if usage[i]<15 and i not in active_jobs.values()]
    candidates=sorted(set(active_jobs.values()))+sorted(idle,key=lambda i:usage[i])
    reservation_slots=budget_worker_cap(budget.limit,budget.charged(),cap,len(active_jobs))
    workers=min(config['max_workers'],manifest['task_count'],len(candidates),max(len(active_jobs),int(psutil.virtual_memory().available//(2*2**30))),reservation_slots)
    if workers<1:raise RuntimeError('No idle CPU/memory or full-phase budget reservation; no worker started')
    cpus=candidates[:workers];free=list(cpus);mutex=threading.Lock();stop=threading.Event()
    write_json(controllers/f'{number:04}-resources.json',{'cpu_ids':cpus,'gpu_ids':[],'reserved_cpu_seconds':0,
        'concurrent_slots_per_initial_budget':reservation_slots,'phase_reservation_seconds':cap,
        'phase_wait_policy':{'owned_exit':'Popen.wait_timeout','exit_observation_seconds':EXIT_WAIT_SECONDS,
                             'startup_poll_seconds':STARTUP_POLL_SECONDS,'permit_deadline_unchanged':True}})

    def wait_phase(directory,ticket_path,role,cpu):
        budget.reserve(str(directory),cap)
        receipt=directory/'receipt.json';start_path=directory/'start.json'
        existing=(directory/'intent.json').exists()
        own=None
        if not existing:
            directory.mkdir(parents=True,exist_ok=True)
            command=[sys.executable,'-B',str(root/'oracleAdapter/run.py'),'full-phase-worker','--case-root',str(root),
                     '--manifest',str(manifest_path),'--task-file',str(ticket_path),'--output',str(directory),'--cpu',str(cpu),'--method',role]
            write_json(directory/'intent.json',{'command':command,'manifest_sha256':msha,'time':timestamp()})
            log=(directory/'process.log').open('xb')
            own=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                env={**os.environ,'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','PYTHONHASHSEED':'0'})
            log.close()
            stat=Path(f'/proc/{own.pid}/stat')
            if stat.exists():write_json(directory/'spawn.json',{'pid':own.pid,'start_ticks':stat.read_text().rsplit(')',1)[1].split()[19]})
        deadline=time.monotonic()+330
        while not start_path.exists():
            if own is not None and own.poll() is not None:raise RuntimeError('Worker exited before startup binding')
            if time.monotonic()>deadline:raise RuntimeError('No identity-bound startup; no permit granted, attempt remains preserved')
            time.sleep(STARTUP_POLL_SECONDS)
        start=json.loads(start_path.read_text())
        if start['manifest_sha256']!=msha or start['role']!=role or start['ticket_sha256']!=digest(ticket_path):raise ValueError('Worker startup identity mismatch')
        if live(start) and not (directory/'permit.json').exists():
            write_json(directory/'permit.json',{**{k:start[k] for k in ('pid','start_ticks','manifest_sha256','task_sha256')},'granted_monotonic':time.monotonic()})
        permit_path=directory/'permit.json'
        granted=json.loads(permit_path.read_text()).get('granted_monotonic',start['started_monotonic']) if permit_path.exists() else start['started_monotonic']
        wait_for_phase_exit(start,own,granted,config['per_process_wall_seconds'])
        exit_path=directory/'exit.json'
        ended=json.loads(exit_path.read_text()) if exit_path.exists() else None
        budget.settle(str(directory),settle_phase(directory,cap))
        if ended and ended['status']!='COMPLETE' and ended.get('error_type') not in {'TimeoutError','OSError','IOError'}:
            raise IntegrityStop('Worker error requires review: '+str(ended.get('error')))
        if receipt.exists():return json.loads(receipt.read_text())
        if role=='execute' and has_execution_result(directory):return {'status':'RECOVERED_COMPLETED_RESULT_FOR_INDEPENDENT_AUDIT'}
        raise RuntimeError('Phase ended without a complete result/receipt')

    def job(entry):
        key=entry['record']['task_key'];jobdir=study/'jobs'/hashlib.sha256(key.encode()).hexdigest()[:24]
        with mutex:
            preferred=active_jobs.get(key)
            if preferred in free:cpu=preferred;free.remove(cpu)
            else:cpu=free.pop()
        jobdir.mkdir(parents=True,exist_ok=True)
        try:
            for attempt_number in range(1,config['maximum_infrastructure_attempts']+1):
                attempt=jobdir/f'attempt-{attempt_number:02}';attempt.mkdir(exist_ok=True)
                ticket=attempt/'execute-ticket.json'
                if not ticket.exists():write_json(ticket,{'entry':entry,'manifest_sha256':msha})
                execution=attempt/'execute'
                try:wait_phase(execution,ticket,'execute',cpu)
                except (ValueError,IntegrityStop):raise
                except Exception as error:
                    write_json(attempt/'execution-infrastructure-error.json',{'error':repr(error),'time':timestamp()},immutable=False)
                    if not has_execution_result(execution):continue
                # A complete navigation failure is audited and retained, never rerun.
                for audit_number in range(1,config['maximum_infrastructure_attempts']+1):
                    directory=attempt/f'audit-{audit_number:02}';ticket=attempt/f'audit-{audit_number:02}-ticket.json'
                    if not ticket.exists():write_json(ticket,{'entry':entry,'manifest_sha256':msha,'execution_directory':str(execution)})
                    try:
                        result=wait_phase(directory,ticket,'audit',cpu)
                        if result['task_key']!=key or result['manifest_sha256']!=msha:raise ValueError('Final audit identity mismatch')
                        return {'task_key':key,'dataset':entry['record']['dataset'],'cohort':entry['record']['cohort'],
                            'status':result['status'],'failure':result['failure'],'actual_actions':result['actual_actions'],
                            'replayed_actions':result['replayed_actions'],'receipt':str(directory/'receipt.json'),
                            'receipt_sha256':digest(directory/'receipt.json'),'attempt':attempt_number,'audit_attempt':audit_number}
                    except (ValueError,IntegrityStop):raise
                    except Exception as error:
                        write_json(directory/'infrastructure-error.json',{'error':repr(error),'time':timestamp()},immutable=False)
                raise RuntimeError('Independent audit infrastructure attempts exhausted')
            raise RuntimeError('Execution infrastructure attempts exhausted')
        except Exception as error:
            stop.set();return {'task_key':key,'status':'INFRASTRUCTURE_OR_INTEGRITY_STOP','error':repr(error),'directory':str(jobdir)}
        finally:
            with mutex:free.append(cpu)

    with ResultJournal(study/'journal') as journal:
        # Reconcile durable accepted records, including ordinary navigation failures.
        key_set=set(keys)
        for key,row in journal.records.items():
            if key not in key_set or digest(row['receipt'])!=row['receipt_sha256']:raise ValueError('Completed journal evidence changed')
        pending=iter(sorted((e for e in entries if e['record']['task_key'] not in journal.records),key=lambda e:e['record']['task_key'] not in active_jobs))
        def note(status):write_json(study/'state.json',{'status':status,'time':timestamp(),'completed':len(journal.records),
            'expected':manifest['task_count'],'cpu_ids':cpus,'charged_cpu_upper_bound_seconds':budget.charged()},immutable=False)
        note('RUNNING')
        dispatched=0
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures={}
            # Only one first job before opening the pool on a fresh run.
            first=next(pending,None)
            if first is not None:
                dispatched+=1
                row=job(first)
                if row['status']=='INFRASTRUCTURE_OR_INTEGRITY_STOP':write_json(study/f'stop-{number:04}.json',row)
                else:journal.append(row['task_key'],row)
            while not stop.is_set() or futures:
                while not stop.is_set() and len(futures)<workers and (dispatch_limit is None or dispatched<dispatch_limit):
                    entry=next(pending,None)
                    if entry is None:break
                    dispatched+=1
                    futures[pool.submit(job,entry)]=entry['record']['task_key']
                if not futures:break
                done,_=concurrent.futures.wait(futures,return_when=concurrent.futures.FIRST_COMPLETED,timeout=30)
                for future in done:
                    key=futures.pop(future);row=future.result()
                    if row['status']=='INFRASTRUCTURE_OR_INTEGRITY_STOP':write_json(study/f'stop-{number:04}-{hashlib.sha256(key.encode()).hexdigest()[:12]}.json',row)
                    else:journal.append(key,row)
                note('STOPPING_FOR_REVIEW' if stop.is_set() else 'RUNNING')
        complete=len(journal.records)==manifest['task_count'] and not stop.is_set()
        if complete:
            write_json(study/'results-index.json',list(journal.records.values()))
            write_json(study/'validation.json',{'status':'COMPLETE_EXECUTION_ACCOUNTING_PENDING_INDEPENDENT_FULL_REVIEW',
                'records':len(journal.records),'manifest_sha256':msha,'results_index_sha256':digest(study/'results-index.json'),
                'charged_cpu_upper_bound_seconds':budget.charged(),'all_passed':all(r['status']=='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES' for r in journal.records.values())})
        note('COMPLETE_PENDING_FULL_REVIEW' if complete else 'CHECKPOINT_DISPATCH_CAP' if dispatch_limit is not None and dispatched>=dispatch_limit and not stop.is_set() else 'STOPPED_RESUMABLE_AFTER_REVIEW')
    # Phase workers have self-caps; an unpermitted late startup can only wait/exit.
    active=[]
    for p in (study/'jobs').glob('*/*/*/start.json'):
        identity=json.loads(p.read_text())
        if live(identity):active.append(str(p))
    write_json(study/'source-freeze.json',{'status':'OPEN' if active else 'CLOSED','manifest_sha256':msha,'live_phase_receipts':active},immutable=False)
    return complete


def dispatch(args):
    if not os.environ.get('CASE1_PROTECTION') or not args.case_root:raise RuntimeError('Protected case runtime required')
    if args.command in {'prepare-full-validation','prepare-full-gate'}:
        from oracle.research.full_compile import compile_run
        m=compile_run(args.case_root,args.output,engineering=args.command=='prepare-full-gate');print({'tasks':m['task_count'],'branches':m['information_branches']})
    elif args.command=='run-full-validation':run(args.case_root,args.manifest,args.max_new_tasks)
    elif args.command=='full-phase-worker':
        from oracle.research.full_worker import phase
        phase(args.case_root,args.manifest,args.task_file,args.output,args.cpu,args.method)
    elif args.command=='review-full-validation':
        from oracle.research.full_review import review
        report=review(args.case_root,args.input,args.output)
        print({'status':report['status'],'records':report['records'],'groups':report['information_condition_groups']})
