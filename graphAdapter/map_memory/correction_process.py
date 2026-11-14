"""Single-flight correction process owner; publication stays with the main writer."""
from pathlib import Path
import json,os,subprocess,sys,threading,time,uuid
from .correction_workspace import freeze_correction_job,PinnedCorrectionJob,validate_append_only_lineage
from .storage.store import IntegrityError,canonical

class BackgroundCorrectionChannel:
    def __init__(self):
        self.owner=threading.get_ident();self.process=None;self.lease=None
        self.log=None;self.outcome=None;self.work=None;self.started=None
        self.active=False;self.spawn_count=0;self.phase_id=None
    def _owner(self):
        if threading.get_ident()!=self.owner:raise RuntimeError('Correction channel requires its owning writer thread')
    def _available(self):
        self._owner()
        if self.active or self.outcome is not None:
            raise RuntimeError('Previous correction must finish and be collected before another start')
        from .correction_runtime import require_correction_runtime
        require_correction_runtime()
    def start(self,service,target,work_root):
        self._available()
        return self._launch(freeze_correction_job(service,target),work_root,None,None)
    def start_catchup(self,service,job,workspace,journal,work_root,*,max_journal_bytes=64*1024*1024):
        self._available()
        if type(max_journal_bytes)is not int or max_journal_bytes<=0:raise ValueError('Positive journal byte budget required')
        if service.store.root.resolve()!=Path(job.record['source_root']).resolve():raise IntegrityError('Catch-up source differs')
        reader=service.store.open_reader()
        lease=PinnedCorrectionJob(reader,job)
        try:
            journal=list(journal);validate_append_only_lineage(job,reader,journal)
            from .tail_journal import frozen_to_record
            rows=[frozen_to_record(item) for item in journal]
            payload=canonical(dict(job_sha256=job.digest,source_snapshot_id=reader.snapshot_id,journal=rows))
            if len(payload)>max_journal_bytes:raise ValueError('Frozen tail journal exceeds admitted byte budget')
        except BaseException:lease.close();raise
        return self._launch(lease,work_root,Path(workspace).absolute(),payload)
    def start_release(self,service,job,workspace,work_root):
        self._available()
        if service.store.root.resolve()!=Path(job.record['source_root']).resolve():
            raise IntegrityError('Release source differs from the frozen job')
        lease=PinnedCorrectionJob(service.store.open_reader(),job)
        return self._launch(lease,work_root,Path(workspace).absolute(),None,operation='release')
    def _launch(self,lease,work_root,workspace,tail_payload,*,operation=None):
        work=Path(work_root).absolute();active_root=Path(lease.job.record['source_root']).resolve()
        submitted=False
        try:
            if work.resolve().is_relative_to(active_root) or active_root.is_relative_to(work.resolve()):
                raise IntegrityError('Correction work must be outside the active episode')
            work.mkdir(parents=True,exist_ok=False)
            (work/'job.json').write_bytes(lease.job.payload_json)
            workspace=work/'map' if workspace is None else workspace
            mode=operation or ('build' if tail_payload is None else 'catchup')
            if tail_payload is not None:(work/'tail.json').write_bytes(tail_payload)
            if self.process is not None and self.process.poll() is not None:
                raise RuntimeError('Persistent correction process exited; explicit recovery required')
            if self.process is None:
                self.log=(work/'process.log').open('xb')
                self.process=subprocess.Popen([sys.executable,'-B',str(Path(__file__).with_name('correction_daemon.py'))],
                    stdin=subprocess.PIPE,stdout=self.log,stderr=subprocess.STDOUT)
                self.spawn_count+=1
            self.lease=lease;self.work=work;self.workspace=workspace;self.mode=mode
            self.phase_id=uuid.uuid4().hex;self.started=time.monotonic();self.active=True
            command=dict(mode=mode,job=str(work/'job.json'),job_sha256=lease.job.digest,workspace=str(workspace),
                work=str(work),tail=str(work/'tail.json') if tail_payload is not None else None,phase_id=self.phase_id)
            submitted=True;self.process.stdin.write(canonical(command)+b'\n');self.process.stdin.flush()
        except BaseException:
            if submitted:
                # A partial pipe write may already have started work. Observe exit before releasing its pin.
                self._stop(5.)
            if self.lease is lease:self.lease=None;self.active=False
            lease.close()
            if self.process is None and self.log is not None:self.log.close();self.log=None
            raise
        return self.poll()
    def _finish_phase(self,code,*,ack=None,aborted=False):
        job=self.lease.job
        state='ABORTED' if aborted else ('READY' if ack is not None and ack['state']=='READY' else 'FAILED')
        error=ack.get('error') if ack else 'Correction process exited before phase acknowledgement'
        result=None
        try:
            if state=='READY':
                pointer=json.loads((self.workspace/'CURRENT.json').read_bytes())
                result_path=(self.workspace/'WORKSPACE_RELEASE.json' if self.mode=='release' else
                    self.workspace/'CORRECTION_RESULT.json' if self.mode=='build' else
                    self.workspace/'tail-results'/(pointer['snapshot_id']+'.json'))
                result=json.loads(result_path.read_bytes())
                if self.mode=='release' and result.get('workspace_closed') is not True:raise IntegrityError('Missing workspace close acknowledgement')
                if (result['job_sha256']!=job.digest or result['target_provenance']!=job.record['target_provenance']
                    or result['installed_in_active_store'] is not False or result['detector_frames']!=0
                    or pointer!=result['detached_snapshot'] or pointer['snapshot_id']!=ack['snapshot_id']):
                    raise IntegrityError('Child result does not identify the frozen correction job')
        except BaseException as exc:state='FAILED';error=repr(exc)
        finally:
            self.lease.close();self.lease=None;self.active=False
        self.outcome=dict(state=state,returncode=None if ack else code,phase_exit_code=code if ack else None,job_sha256=job.digest,work_root=str(self.work),
            workspace=str(self.workspace),mode=self.mode,result=result,error=error,
            elapsed_s=time.monotonic()-self.started,installed_in_active_store=False,
            child_pid=self.process.pid if self.process is not None else None,spawn_count=self.spawn_count,
            completion_basis='phase_acknowledgement' if ack else 'observed_process_exit',
            service_creations=ack.get('service_creations') if ack else None,service_reuses=ack.get('service_reuses') if ack else None)
        (self.work/'PROCESS_OUTCOME.json').write_text(json.dumps(self.outcome,indent=2)+'\n')
        return dict(self.outcome)
    def poll(self):
        self._owner()
        if self.outcome is not None:return dict(self.outcome)
        if not self.active:
            if self.process is not None and self.process.poll() is not None:
                raise RuntimeError('Persistent correction process exited while idle')
            return dict(state='IDLE',installed_in_active_store=False)
        receipt=self.work/'DAEMON_PHASE.json'
        if receipt.exists():
            ack=json.loads(receipt.read_bytes())
            if (ack.get('phase_id')!=self.phase_id or ack.get('job_sha256')!=self.lease.job.digest
                or ack.get('mode')!=self.mode or ack.get('pid')!=self.process.pid or ack.get('state')not in('READY','FAILED')):
                raise IntegrityError('Background phase acknowledgement identity differs')
            return self._finish_phase(0 if ack['state']=='READY' else 1,ack=ack)
        code=self.process.poll()
        if code is not None:return self._finish_phase(code)
        return dict(state='RUNNING',pid=self.process.pid,job_sha256=self.lease.job.digest,
            work_root=str(self.work),elapsed_s=time.monotonic()-self.started,installed_in_active_store=False)
    def collect(self):
        self._owner();status=self.poll()
        if status['state'] in ('IDLE','RUNNING'):raise RuntimeError('No terminal correction outcome to collect')
        self.outcome=None;return status
    def _stop(self,timeout):
        if self.process is None:return None
        process=self.process
        if process.poll() is None:
            if self.active:process.terminate()
            else:
                try:process.stdin.write(b'{"mode":"shutdown"}\n');process.stdin.flush()
                except (BrokenPipeError,OSError):process.terminate()
            try:process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=timeout)
        if process.stdin is not None:
            try:process.stdin.close()
            except (BrokenPipeError,OSError):pass
        if self.log is not None:self.log.close();self.log=None
        self.process=None;return process.returncode
    def close(self,timeout=5.):
        self._owner()
        # Even an idle successful daemon is owned and must be reaped.
        code=self._stop(timeout)
        if self.active:return self._finish_phase(code,aborted=True)
        return dict(self.outcome) if self.outcome is not None else dict(state='IDLE',installed_in_active_store=False)
