"""Host-owned admission/publication bridge; never writes events in the consumer."""
from graphAdapter.map_memory.async_admission import AsyncObservationChannel,FrozenObservation,AdmissionFull

class StreamingMemoryBridge:
    def __init__(self,backend,coordinator,*,max_episode_observations,capacity=2,timeout=1200):
        self.channel=AsyncObservationChannel(backend,capacity=capacity,max_episode_observations=max_episode_observations)
        self.coordinator=coordinator;self.timeout=timeout;self.identity=None
        self._expired_reads=[]
        self.published_observations=0;self.last_publication=None
        self.pending_publications=[];self.publication_error=None;self.close_diagnostic_error=None;self.pose_provider=None
    def track_expired_read(self,request,receipt):
        self._flush_expired_reads()
        q=request['query']
        identity=dict(request_id=request['request_id'],decision_id=q['decision_id'],
            frame_uid=q['current_frame_uid'],snapshot_id=q['snapshot_id'],episode_instance=request['episode_instance'])
        if self.identity!=(q['episode_uid'],identity['episode_instance']):
            raise ValueError('Expired read receipt crossed an episode')
        self._expired_reads.append((identity,receipt))
        self._flush_expired_reads()

    def _flush_expired_reads(self):
        while self._expired_reads and self._expired_reads[0][1].done():
            identity,receipt=self._expired_reads[0]
            self.coordinator.emit('MemoryExpiredReadFinished',**identity,**receipt.result())
            self._expired_reads.pop(0)

    def _emit(self,completions):
        self.pending_publications.extend(value for value in completions if value.new_publication)
        if self.publication_error is not None:
            raise RuntimeError("Previous publication-log write failed; explicit recovery required")
        while self.pending_publications:
            value=self.pending_publications[0]
            event=value.publication();kind=event.pop('kind')
            event.update(admitted_monotonic_ns=value.admission.submitted_monotonic_ns,
                completion_observed_monotonic_ns=value.completed_monotonic_ns)
            if value.started_monotonic_ns is not None:event['work_started_monotonic_ns']=value.started_monotonic_ns
            try:self.coordinator.emit(kind,**event,shadow=True)
            except BaseException as error:
                self.publication_error=dict(error_type=type(error).__name__,message=str(error),
                    frame_uid=value.admission.frame_uid,snapshot_id=value.result['snapshot_id'])
                raise
            self.pending_publications.pop(0)
            self.last_publication=value.result
            if kind=='PublishedSnapshot':self.published_observations+=1
    def failure_snapshot(self):
        import copy
        return dict(consumer=self.channel.failure_snapshot(),publication_error=copy.deepcopy(self.publication_error),
            unlogged_commits=[value.publication() for value in self.pending_publications],
            close_diagnostic_error=copy.deepcopy(self.close_diagnostic_error))
    def poll(self):
        self._flush_expired_reads()
        self._emit(self.channel.poll_completions())
        status=self.channel.status()
        if status['failure'] is not None:
            from graphAdapter.map_memory.async_admission import ConsumerFailed
            raise ConsumerFailed(status['failure']['message'])
        return status
    def submit(self,packet,receipt,adapter):
        identity=adapter.get_mapping_session_identity()
        pair=(identity.episode_id,identity.episode_instance)
        if self.identity is None:
            if self.pending_publications:raise RuntimeError('Previous episode has unlogged publications')
            self.channel.begin_episode(*pair);self.identity=pair
            self.last_publication=None;self.pose_provider=packet.pose_provider
        elif self.identity!=pair:raise ValueError('End previous mapping session before admitting another')
        if packet.pose_provider!=self.pose_provider:raise ValueError('Pose provider changed within mapping session')
        sample=(None if self.pose_provider=='simulator_ground_truth' else
                adapter.get_mapping_frame_snapshot(packet.frame_uid,timestamp_ns=packet.sensor_timestamp_ns,episode_id=packet.episode_uid))
        item=FrozenObservation.create(packet,receipt,mapping_sample=sample,episode_instance=identity.episode_instance)
        self.poll()
        while True:
            try:return self.channel.submit_frozen(item)
            except AdmissionFull:
                self._emit(self.channel.wait_for_capacity(self.timeout))
    def await_visible(self,latest_capture_seq,*,max_capture_lag=1,read_deadline=None,poll_only=False):
        """Bound only host-visible committed snapshots, never queue-admission counts."""
        import time
        if type(max_capture_lag)is not int or max_capture_lag<0:raise ValueError('Nonnegative decision capture lag required')
        started=time.monotonic()
        status=self.poll()
        if type(latest_capture_seq)is not int or latest_capture_seq!=status['admitted_seq']:
            raise ValueError('Decision must identify the latest admitted source observation')
        deadline=None if self.timeout is None else time.monotonic()+self.timeout
        while True:
            visible=0 if self.last_publication is None else self.last_publication['cutoff']['capture_seq']
            now=time.monotonic()
            lag=latest_capture_seq-visible
            fresh=lag<=max_capture_lag
            if fresh or poll_only or (read_deadline is not None and now>=read_deadline):
                return dict(snapshot_id=None if self.last_publication is None else self.last_publication['snapshot_id'],
                    visible_capture_seq=visible,current_capture_seq=latest_capture_seq,capture_lag=lag,
                    wait_seconds=now-started,fresh_enough=fresh,poll_only=poll_only)
            limit=deadline
            if read_deadline is not None:
                limit=read_deadline if deadline is None else min(deadline,read_deadline)
            remaining=None if limit is None else max(0.,limit-now)
            try:
                completed=self.channel.wait_for_completions(remaining)
            except TimeoutError:
                if read_deadline is None or limit!=read_deadline or time.monotonic()<read_deadline:raise
                completed=()
            self._emit(completed)
            self.poll()
    def end_episode(self,adapter,cancelled_actions):
        if self.identity is None:return None
        identity=adapter.get_mapping_session_identity()
        if (identity.episode_id,identity.episode_instance)!=self.identity:
            raise ValueError('Pose session changed before final map drain')
        target=None if self.pose_provider=='simulator_ground_truth' else adapter.get_mapping_correction_snapshot()
        self.channel.seal_episode(correction=target)
        import time
        deadline=None if self.timeout is None else time.monotonic()+self.timeout
        while True:
            remaining=None if deadline is None else max(0.,deadline-time.monotonic())
            self._emit(self.channel.wait_for_completions(remaining))
            status=self.poll()
            if not status['pending_count'] and not status['active']:break
        result=self.channel.end_episode(cancelled_actions)
        self._flush_expired_reads()
        self.identity=None
        return result
    def close(self):
        try:completed=self.channel.close()
        except BaseException:
            self._flush_expired_reads()
            # close may fail after real commits but before returning completions.
            # Retain those receipts for audit; do not turn a failed close into a
            # successful event emission or replace its original exception.
            try:self.pending_publications.extend(value for value in self.channel.poll_completions() if value.new_publication)
            except BaseException as detail:
                self.close_diagnostic_error=dict(error_type=type(detail).__name__,message=str(detail))
            raise
        self._emit(completed)
        self._flush_expired_reads()
