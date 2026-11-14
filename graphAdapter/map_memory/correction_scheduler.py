"""Writer-owned detached correction lifecycle. No navigation policy or pose tuning."""
import json,time,threading
from pathlib import Path
from .correction_process import BackgroundCorrectionChannel
from .correction_workspace import CorrectionJob,install_detached
from .tail_journal import FrozenTailJournal
from .storage.store import IntegrityError

class DetachedCorrectionScheduler:
    def __init__(self,service,root,*,journal_bytes,journal_entries):
        if any(type(x)is not int or x<=0 for x in (journal_bytes,journal_entries)):raise ValueError('Positive scheduler journal limits required')
        self.service=service;self.root=Path(root);self.root.mkdir(parents=True,exist_ok=False)
        self.owner=threading.get_ident();self.channel=BackgroundCorrectionChannel()
        self.journal_bytes=journal_bytes;self.journal_entries=journal_entries
        self.job=None;self.journal=None;self.workspace=None;self.run=None
        self.ordinal=0;self.round=0;self.failure=None;self.publication=None;self.closed=False
        self.releasing=False;self.installed=None
    def _owner(self):
        if threading.get_ident()!=self.owner:raise RuntimeError('Scheduler requires the sole writer thread')
        if self.closed:raise RuntimeError('Scheduler is closed')
        if self.failure is not None:raise RuntimeError('Detached scheduler failed: '+self.failure)
    def status(self):
        return dict(active=self.job is not None,failed=self.failure is not None,closed=self.closed,
            target=None if self.job is None else self.job.record['target_provenance'],
            current_cutoff=None if self.service.pointer is None else dict(self.service.pointer['cutoff']),
            pending_publication=self.publication is not None,phase="releasing_workspace" if self.releasing else "correcting" if self.job else "idle",
            scope='Applied map remains readable; pending target is not claimed applied')
    def request(self,target):
        self._owner()
        if self.job is not None:return dict(started=False,reason='one_job_active',status=self.status())
        if self.publication is not None:raise RuntimeError('Collect the committed publication before starting another job')
        if self.service.prepared is not None:raise IntegrityError('Finish ordinary publication before requesting correction')
        self.ordinal+=1;self.run=self.root/f'job-{self.ordinal:06d}';self.run.mkdir()
        try:
            self.channel.start(self.service,target,self.run/'build')
            self.job=CorrectionJob((self.run/'build/job.json').read_bytes());self.workspace=self.run/'build/map'
            self.journal=FrozenTailJournal(self.run/'tail',self.job,max_bytes=self.journal_bytes,max_entries=self.journal_entries)
            self.service.attach_tail_journal(self.journal);self.round=0
        except BaseException as exc:
            self.failure=repr(exc);self.channel.close()
            if self.journal is not None:self.journal.close()
            raise
        return dict(started=True,status=self.status())
    def advance(self):
        self._owner()
        if self.job is None:return self.status()
        if self.service.prepared is not None:return dict(self.status(),waiting_for='ordinary_publication')
        try:
            state=self.channel.poll()
            if state['state']=='RUNNING':return dict(self.status(),process=state)
            if state['state']!='READY':raise RuntimeError('Background correction did not finish successfully: '+str(state))
            outcome=self.channel.collect()
            if self.releasing:
                if outcome['mode']!='release' or outcome['result'].get('workspace_closed')is not True:
                    raise IntegrityError('Expected private workspace release acknowledgement')
                from .correction_cleanup import reclaim_workspace
                reclaim_workspace(self.service,self.job,self.workspace,self.installed)
                self.job=None;self.releasing=False;self.installed=None
                return self.status()
            cutoff=outcome['result']['replayed_through']
            current=self.service.pointer['cutoff']
            if cutoff['capture_seq']>current['capture_seq']:raise IntegrityError('Detached frontier is ahead of source')
            if outcome['mode']=='build' or cutoff!=current:
                self.round+=1
                self.channel.start_catchup(self.service,self.job,self.workspace,self.journal.snapshot(),
                    self.run/f'catchup-{self.round:06d}',max_journal_bytes=self.journal_bytes)
                return dict(self.status(),waiting_for='tail_and_blob_preparation')
            if self.journal.pending() is not None:raise IntegrityError('Unbound observation before correction install')
            frozen=self.journal.snapshot();self.service.detach_tail_journal()
            result=install_detached(self.service,self.job,self.workspace,frozen)
            # Retain a publication receipt until the caller explicitly collects it.
            from dataclasses import fields
            from graphAdapter.observation_packet import ObservationPacket
            latest=max(self.service.frames.values(),key=lambda row:row['capture_seq'])
            packet=ObservationPacket(**{field.name:latest[field.name] for field in fields(ObservationPacket) if field.name in latest})
            self.publication=dict(result,target_provenance=self.job.record['target_provenance'],
                frontier_packet=packet.to_record(),frame_uid=packet.frame_uid,source_packet_event_seq=packet.event_seq)
            (self.run/'INSTALLED.json').write_text(json.dumps(self.publication,indent=2)+'\n')
            self.journal.close();self.journal=None
            self.installed=result;self.releasing=True
            self.channel.start_release(self.service,self.job,self.workspace,self.run/'release')
            return self.status()
        except BaseException as exc:
            self.failure=repr(exc)
            (self.run/'SCHEDULER_FAILURE.json').write_text(json.dumps(dict(error=self.failure,status=self.status()),indent=2)+'\n')
            raise
    def collect_publication(self):
        # A later cleanup failure cannot invalidate an already committed receipt.
        if threading.get_ident()!=self.owner:raise RuntimeError('Publication receipt requires its owner')
        result=self.publication;self.publication=None;return result
    def drain(self,timeout):
        self._owner();deadline=time.monotonic()+timeout
        while self.job is not None:
            self.advance()
            if self.job is not None:
                if time.monotonic()>=deadline:raise TimeoutError('Correction drain timed out; live child and pins retained')
                time.sleep(.02)
        return self.status()
    def close(self,timeout=5.):
        if threading.get_ident()!=self.owner:raise RuntimeError('Scheduler close requires its owner')
        if self.closed:return self.status()
        outcome=self.channel.close(timeout=timeout)
        if self.journal is not None:
            if self.service.tail_journal is self.journal:self.service.detach_tail_journal()
            self.journal.close();self.journal=None
        self.closed=True
        return dict(self.status(),child=outcome)


class WorkerCorrectionController:
    """Small worker integration boundary; receipts remain pending until sent."""
    def __init__(self,service,root,options):
        self.service=service;self.timeout=options['drain_timeout_s'];self.pending=[]
        self.policy=(dict(max_difference_m=options['max_correction_difference_m'],point_radius_m=options['mapping_point_radius_m'])
            if 'max_correction_difference_m' in options else None)
        self.scheduler=DetachedCorrectionScheduler(service,root,journal_bytes=options['journal_bytes'],journal_entries=options['journal_entries'])
    def advance(self):
        try:self.scheduler.advance()
        finally:self._collect()
    def _collect(self):
        receipt=self.scheduler.collect_publication()
        if receipt is not None:self.pending.append(receipt)
    def after_observation_commit(self,target):
        if target is not None:self.scheduler.request(target)
    def finish(self,target):
        try:
            if self.scheduler.job is not None:self.scheduler.drain(self.timeout)
        finally:self._collect()
        # Match the original no-op contract. Tail append clears correction_applied.
        from .storage.store import canonical
        graph=self.service.graph
        latest=max(self.service.frames.values(),key=lambda row:row['capture_seq'])
        if target.frame_id!=latest['frame_uid'] or target.timestamp_ns>latest['sensor_timestamp_ns']:
            raise IntegrityError('Terminal correction must identify the latest source observation')
        assessment=self.service.assess_terminal_correction(target,**self.policy) if self.policy is not None else None
        if assessment is None and self.service.mapping_chart is not None:self.service.mapping_chart.propose_correction(target)
        done=(graph is not None and graph.get('mapping_state',{}).get('correction_applied') is True
              and canonical(self.service.bindings)==canonical(target.bindings))
        if assessment is not None and assessment['action']=='retain':
            done=True
            self.service.store._append('updates.jsonl',dict(kind='correction_threshold_retained',
                frame_uid=latest['frame_uid'],assessment=assessment))
        if not done:
            self.scheduler.request(target)
            try:self.scheduler.drain(self.timeout)
            finally:self._collect()
        pointer=self.service.pointer;latest=max(self.service.frames.values(),key=lambda row:row['capture_seq'])
        return dict(duplicate=True,snapshot_id=pointer['snapshot_id'],versions=pointer['versions'],cutoff=pointer['cutoff'],
            frame_uid=latest['frame_uid'],source_packet_event_seq=latest['event_seq'],prior_publications=self.receipts(),
            correction_assessment=assessment)
    def receipts(self):return json.loads(json.dumps(self.pending))
    def acknowledge_sent(self):self.pending.clear()
    def assert_drained(self):
        if self.scheduler.job is not None or self.pending:raise RuntimeError('Final correction and publication receipts must drain before successful episode end')
    def close(self):return self.scheduler.close()
