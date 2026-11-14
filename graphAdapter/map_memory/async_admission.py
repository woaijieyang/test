"""Bounded host admission to one real memory consumer.

No Coordinator is called here. Only the owner host thread polls/drains validated
commit completions and emits their original packet identities. Queue admission is
not publication. Stop admission, drain and emit completions, then
end the backend episode successfully, then emit terminal; raw/camera producers must retain their data until then.

Native historical correction may block its consumer. Simulator packets have no
native correction channel. Runtime overlap/freshness requires separate host
integration and timing evidence; queue admission alone does not prove either.
"""
from dataclasses import dataclass,field
from collections import deque
from concurrent.futures import Future,TimeoutError as FutureTimeout
from contextvars import copy_context
import copy,hashlib,json,re,threading,time
from .admission_receipt import validated_completion
from graphAdapter.observation_packet import ObservationPacket,thaw
from poseAdapter.interfaces.mapping import MappingSample,CorrectionSnapshot

MISSING=object()
def _bytes(value):return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
def _packet(value):return ObservationPacket(**json.loads(_bytes(value.to_record()if isinstance(value,ObservationPacket)else value)))
def _snapshot(value,kind):
    if not isinstance(value,kind):raise TypeError("Explicit validated "+kind.__name__+" required")
    return kind.from_record(json.loads(_bytes(value.to_record())))

@dataclass(frozen=True)
class FrozenObservation:
    packet_json:bytes
    receipt_json:bytes
    mapping_json:object
    episode_instance:str
    frozen_monotonic_ns:int=field(default_factory=time.monotonic_ns)
    @classmethod
    def create(cls,packet,receipt,*,mapping_sample=MISSING,episode_instance=MISSING):
        if mapping_sample is MISSING:raise TypeError("mapping_sample must be explicit; native None means unavailable, provider pose remains in its packet")
        if not isinstance(episode_instance,str)or not episode_instance:raise ValueError("Explicit public session identity required, including unavailable pose")
        packet=_packet(packet);p=packet.to_record();r=json.loads(_bytes(thaw(receipt)))
        expected=dict(episode_uid=packet.episode_uid,frame_uid=packet.frame_uid,capture_seq=packet.capture_seq,
            env_step=packet.env_step,packet_event_seq=packet.event_seq,calibration_hash=packet.calibration_hash,
            packet_record_hash=hashlib.sha256(_bytes(p)).hexdigest())
        if r.get("committed")is not True or any(r.get(k)!=v for k,v in expected.items()):
            raise ValueError("Matching committed stage000 receipt required")
        sample=None if mapping_sample is None else _snapshot(mapping_sample,MappingSample)
        if packet.pose_provider=='simulator_ground_truth':
            if sample is not None:raise ValueError('Simulator pose cannot carry a native mapping sample')
            if packet.pose_record.get('episode_instance')!=episode_instance:raise ValueError('Simulator frozen session differs')
        elif sample is None:
            if packet.pose_record.get("geometry_status")=="available":
                raise ValueError("Measured geometry cannot omit its frozen mapping sample")
        elif (sample.episode_id,sample.frame_id,sample.timestamp_ns,sample.latest_frame)!=(packet.episode_uid,packet.frame_uid,packet.sensor_timestamp_ns,True):
            raise ValueError("Frozen mapping sample does not identify this source frame")
        if sample is not None and sample.episode_instance!=episode_instance:raise ValueError("Mapping sample session identity differs")
        return cls(_bytes(p),_bytes(r),None if sample is None else _bytes(sample.to_record()),episode_instance)
    @property
    def packet(self):return ObservationPacket(**json.loads(self.packet_json))
    @property
    def receipt(self):return json.loads(self.receipt_json)
    @property
    def mapping_sample(self):return None if self.mapping_json is None else MappingSample.from_record(json.loads(self.mapping_json))

@dataclass(frozen=True)
class FrozenCorrection:
    packet_json:bytes
    correction_json:bytes
    frozen_monotonic_ns:int=field(default_factory=time.monotonic_ns)
    @classmethod
    def create(cls,packet,correction):
        p=_packet(packet)
        if p.pose_provider=='simulator_ground_truth':raise ValueError('Simulator pose has no native correction channel')
        c=_snapshot(correction,CorrectionSnapshot)
        if c.episode_id!=p.episode_uid or c.frame_id!=p.frame_uid:raise ValueError("Correction source frame/episode mismatch")
        available=p.pose_record.get("geometry_status")=="available"
        if c.timestamp_ns>p.sensor_timestamp_ns or(available and c.timestamp_ns!=p.sensor_timestamp_ns):
            raise ValueError("Correction timestamp is incompatible with its source observation")
        return cls(_bytes(p.to_record()),_bytes(c.to_record()))
    @property
    def packet(self):return ObservationPacket(**json.loads(self.packet_json))
    @property
    def correction(self):return CorrectionSnapshot.from_record(json.loads(self.correction_json))

def checked_commit(result,packet,*,target_version=MISSING,allow_noop=False):
    if result.get("duplicate")is True:
        if not allow_noop:raise ValueError("Duplicate observation cannot publish twice")
        # An explicit no-op correction is not a new publication. Still require
        # the backend's actual already-committed frontier; never infer identity.
        if result.get("frame_uid")!=packet.frame_uid or type(result.get("source_packet_event_seq"))is not int or result["source_packet_event_seq"]!=packet.event_seq:
            raise ValueError("No-op correction source mismatch")
        if not isinstance(result.get("snapshot_id"),str)or not re.fullmatch("[0-9a-f]{64}",result["snapshot_id"]):
            raise ValueError("No-op correction lacks committed snapshot")
        cutoff=result.get("cutoff")or{}
        if any(type(cutoff.get(k))is not int or cutoff[k]!=getattr(packet,k)for k in("capture_seq","event_seq")):
            raise ValueError("No-op correction cutoff mismatch")
        if result.get("episode_uid",packet.episode_uid)!=packet.episode_uid:raise ValueError("No-op correction episode mismatch")
        v=(result.get("versions")or{}).get("pose_map_version",MISSING)
        if v is MISSING or(v is not None and(type(v)is not int or v<0)):
            raise ValueError("No-op correction version missing")
        if packet.pose_record.get("geometry_status")=="available"and v is None:raise ValueError("Measured no-op cannot lose its revision")
        return json.loads(_bytes(result))
    value=validated_completion(packet,result)
    if target_version is not MISSING and value["versions"]["pose_map_version"]!=target_version:
        raise ValueError("Commit map version differs from prepared target")
    return value

@dataclass(frozen=True)
class Admission:
    ordinal:int
    frame_uid:str
    submitted_monotonic_ns:int

@dataclass(frozen=True)
class Completion:
    kind:str
    admission:Admission
    packet_json:bytes
    result_json:bytes
    completed_monotonic_ns:int
    started_monotonic_ns:object=None
    @property
    def result(self):return json.loads(self.result_json)
    @property
    def new_publication(self):return not self.result.get("duplicate",False)
    def publication(self):
        if not self.new_publication:raise ValueError("No-op correction is not a new publication")
        p=ObservationPacket(**json.loads(self.packet_json));r=self.result
        event=dict(kind="PublishedSnapshot"if self.kind=="observation"else"MapCorrectionPublished",
            frame_uid=p.frame_uid,capture_seq=p.capture_seq,source_packet_event_seq=p.event_seq,
            cutoff_event_seq=r["cutoff"]["event_seq"],snapshot_id=r["snapshot_id"],versions=r["versions"])
        for name in ("target_provenance","parent_snapshot_id"):
            if name in r:event[name]=r[name]
        return event

class AdmissionFull(RuntimeError):
    def __init__(self,item):
        super().__init__("Bounded admission is full; poll/drain then retry this frozen input")
        self.frozen_input=item

class ReadAdmissionFull(RuntimeError):
    pass

class ReadDeadlineExpired(TimeoutError):
    """The host stopped waiting for this specific read future."""

class _ReadFuture(Future):
    """One request's monotonic timings, updated under the admission channel lock."""
    def __init__(self, active_kind, queued_ahead):
        super().__init__()
        self.submitted_ns=time.monotonic_ns()
        self.started_ns=None
        self.finished_ns=None
        self.expiry_receipt=None
        self.active_kind=active_kind
        self.queued_ahead=queued_ahead


class ConsumerFailed(RuntimeError):
    pass

class AsyncObservationChannel:
    """One owner host, one backend consumer, bounded unacknowledged inputs.

    submit is nonblocking backpressure. AdmissionFull retains the frozen input;
    wait_for_capacity returns real completions for host emission, then it can be
    retried without another PoseAdapter read. max_episode_observations must use
    the caller's existing episode budget. One reserved final-correction slot is
    allowed after sealing. All source refs must stay immutable/alive until end.
    """
    def __init__(self,backend,*,capacity=2,max_episode_observations,max_payload_bytes=32*1024*1024):
        if type(capacity)is not int or capacity<1:raise ValueError("Positive capacity required")
        if type(max_episode_observations)is not int or max_episode_observations<1:raise ValueError("Existing episode budget required")
        if type(max_payload_bytes)is not int or max_payload_bytes<1:raise ValueError("Positive payload byte bound required")
        self.backend=backend;self.capacity=capacity;self.max_frames=max_episode_observations;self.max_bytes=max_payload_bytes
        self._owner=threading.get_ident();self._cv=threading.Condition();self._jobs=deque();self._done=deque()
        self._outstanding={};self._unpublished={};self._active=None;self._failure=None;self._close_error=None
        self._state="new";self._episode=None;self._pose_source=None;self._seen=set();self._last=None;self._ordinal=0
        self._admitted_seq=0;self._published_seq=0;self._completed_count=0;self._closing=False;self._noop_corrections=0;self._last_noop=None
        context=copy_context()
        self._committed_packets={};self._snapshot_ids=set();self._last_snapshot=None;self._snapshot_cutoffs={}
        self._read_pending=None;self._read_timeouts=0;self._reads_completed=0;self._reads_cancelled=0
        self._thread=threading.Thread(target=lambda:context.run(self._run),name="graph-admission-consumer",daemon=False)
        self._thread.start()
    def _host(self):
        if threading.get_ident()!=self._owner:raise RuntimeError("Only owner host thread may admit or poll completions")
    def _error(self):
        if self._failure is not None:raise ConsumerFailed("Background consumer failed: "+self._failure["message"])
    def begin_episode(self,episode_id,episode_instance):
        self._host()
        if not all(isinstance(v,str)and v for v in(episode_id,episode_instance)):raise ValueError("Full episode identities required")
        with self._cv:
            self._error()
            if self._closing or not self._thread.is_alive():raise RuntimeError("Admission channel is closed")
            if self._state not in("new","ended")or self._outstanding or self._active or self._jobs:
                raise RuntimeError("End/drain the prior episode before reset")
            self._episode=(episode_id,episode_instance);self._state="active";self._pose_source=None;self._seen.clear();self._last=None
            self._committed_packets.clear();self._snapshot_ids.clear();self._last_snapshot=None;self._snapshot_cutoffs.clear()
            self._read_timeouts=self._reads_completed=self._reads_cancelled=0
            self._admitted_seq=self._published_seq=self._completed_count=0;self._noop_corrections=0;self._last_noop=None
    def _accept(self,kind,item,*,reserved=False):
        with self._cv:
            self._error()
            if self._closing:raise RuntimeError("Admission channel is closed")
            if self._state not in(("sealed",)if reserved else("active",)):raise RuntimeError("Episode is not accepting observations")
            p=item.packet
            if self._episode is None or p.episode_uid!=self._episode[0]:raise ValueError("Cross-episode admission")
            if kind=="observation"and item.episode_instance!=self._episode[1]:raise ValueError("Cross-session frozen observation")
            sample=item.mapping_sample if kind=="observation"else item.correction
            if sample is not None and(sample.episode_id,sample.episode_instance)!=self._episode:raise ValueError("Cross-episode instance")
            size=len(item.packet_json)+(len(item.receipt_json)+(len(item.mapping_json)if item.mapping_json else 0)if kind=="observation"else len(item.correction_json))
            if size>self.max_bytes:raise ValueError("Frozen payload byte bound exceeded")
            if kind=="observation":
                if self._pose_source is not None and p.pose_provider!=self._pose_source:raise ValueError('Pose provider changed within admitted episode')
                uid_hash=hashlib.sha256(p.frame_uid.encode()).digest()
                if p.capture_seq!=self._admitted_seq+1 or uid_hash in self._seen:raise ValueError("Duplicate or nonconsecutive source frame")
                if p.capture_seq>self.max_frames:raise ValueError("Declared episode observation budget exceeded")
                if len(self._outstanding)>=self.capacity and not reserved:raise AdmissionFull(item)
                self._pose_source=p.pose_provider
                self._seen.add(uid_hash);self._admitted_seq=p.capture_seq;self._last=item
            elif len(self._outstanding)>=self.capacity and not reserved:raise AdmissionFull(item)
            self._ordinal+=1;a=Admission(self._ordinal,p.frame_uid,time.monotonic_ns())
            job=(kind,item,a,None);self._outstanding[a.ordinal]=job;self._unpublished[a.ordinal]=job
            self._jobs.append(job);self._cv.notify_all();return a
    def submit_observation(self,packet,receipt,*,mapping_sample=MISSING,episode_instance=MISSING):
        self._host();return self.submit_frozen(FrozenObservation.create(packet,receipt,mapping_sample=mapping_sample,episode_instance=episode_instance))
    def submit_frozen(self,item):
        self._host()
        if not isinstance(item,FrozenObservation):raise TypeError("FrozenObservation required")
        return self._accept("observation",item)
    def submit_read(self,request):
        """One bounded read queued on the same consumer as complete map transactions."""
        from graphAdapter.map_memory.retrieval import FrozenMemoryRead
        self._host();item=FrozenMemoryRead.create(request,max_bytes=min(self.max_bytes,1024*1024))
        value=item.request;query=value['query']
        with self._cv:
            self._error()
            if self._closing or self._state!='active':raise RuntimeError('Read requires an active unsealed episode')
            if (query['episode_uid'],value['episode_instance'])!=self._episode:raise ValueError('Cross-session read')
            cutoff=self._snapshot_cutoffs.get(query['snapshot_id'])
            if cutoff is None:raise ValueError('Read snapshot has not been committed in this session')
            if query['cutoff_capture_seq']!=cutoff['capture_seq']or query['cutoff_event_seq']!=cutoff['event_seq']:
                raise ValueError('Read cutoff differs from its committed snapshot')
            if self._last is None or query['current_capture_seq']!=self._admitted_seq or query['current_frame_uid']!=self._last.packet.frame_uid:
                raise ValueError('Read current frame differs from the latest admitted host observation')
            if self._read_pending is not None:raise ReadAdmissionFull('Previous read still owns the bounded read slot')
            active_kind=self._active[0] if self._active is not None else None
            future=_ReadFuture(active_kind,len(self._jobs))
            job=('read',item,None,future);self._read_pending=future
            self._jobs.append(job);self._cv.notify_all();return future

    def _finish_expired_read(self,future,outcome,error=None,terminal_ns=None):
        # Called under the channel lock. This second future carries only timing
        # and terminal status; neither the graph reply nor an exception is retained.
        receipt=future.expiry_receipt
        if receipt is not None and not receipt.done():
            receipt.set_result(dict(outcome=outcome,submitted_ns=future.submitted_ns,
                started_ns=future.started_ns,finished_ns=future.finished_ns,terminal_ns=terminal_ns or future.finished_ns,
                error_type=getattr(error,'remote_error_type',type(error).__name__) if error is not None else None))

    def wait_read(self,future,timeout):
        self._host()
        deadline_ns=None if timeout is None else time.monotonic_ns()+round(timeout*1e9)
        return self.wait_read_until(future,deadline_ns)

    def wait_read_until(self,future,deadline_ns):
        """Use worker completion time to resolve a deadline race, even when host polling is delayed."""
        self._host()
        remaining=None if deadline_ns is None else max(0.,(deadline_ns-time.monotonic_ns())/1e9)
        try:
            future.result(remaining)
        except FutureTimeout:
            # This can mean either host wait expiry or a backend transport timeout.
            pass
        except Exception:
            if not future.done():raise
        with self._cv:
            if future.done() and not future.cancelled():
                error=future.exception()
                if isinstance(error,(OSError,EOFError)):
                    # The transport is unusable; the consumer failure must reach the host.
                    return future.result()
                if deadline_ns is None or future.finished_ns<=deadline_ns:return future.result()
            if future.expiry_receipt is None:
                future.expiry_receipt=Future()
                if future.cancel():
                    self._finish_expired_read(future,'cancelled_before_start',terminal_ns=time.monotonic_ns())
                elif future.done():
                    error=future.exception()
                    self._finish_expired_read(future,'late_error' if error else 'late_reply',error)
                self._read_timeouts+=1
            self._cv.notify_all()
        raise ReadDeadlineExpired('Read decision wait expired; queued work cancelled or running reply remains isolated')

    def read_timing(self,future):
        self._host()
        with self._cv:
            return dict(submitted_ns=future.submitted_ns,started_ns=future.started_ns,
                        finished_ns=future.finished_ns,observed_ns=time.monotonic_ns(),
                        expired_read=future.expiry_receipt is not None,cancelled=future.cancelled(),active_at_admission=future.active_kind,
                        queued_jobs_ahead=future.queued_ahead)

    def _run_read(self,item,future):
        with self._cv:
            if not future.set_running_or_notify_cancel():
                self._read_pending=None;self._active=None;self._reads_cancelled+=1;self._cv.notify_all()
                return
            future.started_ns=time.monotonic_ns()
        try:result=item.validate_reply(self.backend.read_memory(item.request))
        except (OSError,EOFError):
            # Transport synchronization is lost. Let the outer failure path
            # poison the consumer; do not reuse this socket for a map commit.
            raise
        except Exception as error:
            with self._cv:
                future.finished_ns=time.monotonic_ns()
                self._read_pending=None;self._active=None;self._reads_completed+=1
                self._finish_expired_read(future,'late_error',error)
                future.set_exception(error);self._cv.notify_all()
        else:
            with self._cv:
                future.finished_ns=time.monotonic_ns()
                self._read_pending=None;self._active=None;self._reads_completed+=1
                self._finish_expired_read(future,'late_reply')
                future.set_result(result);self._cv.notify_all()

    def submit_correction(self,correction):
        self._host()
        if self._last is None:raise RuntimeError("Correction requires an admitted source packet")
        return self._accept("correction",FrozenCorrection.create(self._last.packet,correction))
    def seal_episode(self,*,correction=MISSING):
        self._host()
        if correction is MISSING:raise TypeError("Explicit final CorrectionSnapshot or None required")
        with self._cv:
            self._error()
            if self._state!="active":raise RuntimeError("Episode already sealed")
            item=None if correction is None else FrozenCorrection.create(self._last.packet,correction)if self._last else None
            if correction is not None and item is None:raise RuntimeError("No source packet for correction")
            if item is not None and(item.correction.episode_id,item.correction.episode_instance)!=self._episode:raise ValueError("Cross-episode final correction")
            self._state="sealed"
            try:
                if item is not None:self._accept("correction",item,reserved=True)
            except BaseException:
                self._state="active";raise
    def poll_completions(self):
        self._host()
        with self._cv:
            values=tuple(self._done);self._done.clear()
            for value in values:self._outstanding.pop(value.admission.ordinal,None)
            self._cv.notify_all();return values
    def wait_for_capacity(self,timeout=None):
        self._host();deadline=None if timeout is None else time.monotonic()+timeout
        with self._cv:
            while len(self._outstanding)>=self.capacity and not self._done:
                self._error();remaining=None if deadline is None else deadline-time.monotonic()
                if remaining is not None and remaining<=0:raise TimeoutError("Admission backpressure timeout")
                self._cv.wait(remaining)
            self._error()
        return self.poll_completions()
    def wait_for_completions(self,timeout=None):
        """Yield ready commits while later work continues; this is not end/drain."""
        self._host();deadline=None if timeout is None else time.monotonic()+timeout
        with self._cv:
            while not self._done:
                self._error()
                if not self._unpublished and self._active is None:return ()
                remaining=None if deadline is None else deadline-time.monotonic()
                if remaining is not None and remaining<=0:raise TimeoutError("Completion wait timeout")
                self._cv.wait(remaining)
        return self.poll_completions()
    def drain(self,timeout=None):
        self._host();deadline=None if timeout is None else time.monotonic()+timeout
        with self._cv:
            while self._unpublished or self._active or self._read_pending is not None:
                self._error();remaining=None if deadline is None else deadline-time.monotonic()
                if remaining is not None and remaining<=0:raise TimeoutError("Consumer drain timeout")
                self._cv.wait(remaining)
            self._error()
        return self.poll_completions()
    def end_episode(self,cancelled_actions=()):
        """After seal/drain and host publication emission; emit terminal only after this succeeds."""
        self._host()
        with self._cv:
            self._error()
            if self._state!="sealed"or self._outstanding or self._active or self._jobs:
                raise RuntimeError("Seal, drain and acknowledge committed completions before end/release")
            f=Future();self._jobs.append(("end",tuple(cancelled_actions),None,f));self._cv.notify_all()
        return f.result()
    def status(self):
        with self._cv:
            now=time.monotonic_ns();pending=[j[2].submitted_monotonic_ns for j in self._unpublished.values()]
            return dict(state=self._state,admitted_seq=self._admitted_seq,published_seq=self._published_seq,
                pending_count=len(pending),completed_unpolled=len(self._done),unacknowledged=len(self._outstanding),
                active=self._active is not None,read_pending=self._read_pending is not None,read_timeouts=self._read_timeouts,reads_completed=self._reads_completed,reads_cancelled=self._reads_cancelled,oldest_pending_age_seconds=(now-min(pending))/1e9 if pending else 0.,
                completed_tasks=self._completed_count,noop_corrections=self._noop_corrections,last_noop=copy.deepcopy(self._last_noop),failure=copy.deepcopy(self._failure),consumer_alive=self._thread.is_alive())
    def failure_snapshot(self):
        with self._cv:
            pending=[]
            for j in self._unpublished.values():
                item=j[1]
                material=dict(packet=json.loads(item.packet_json))
                if isinstance(item,FrozenObservation):
                    material.update(receipt=item.receipt,mapping_sample=None if item.mapping_json is None else json.loads(item.mapping_json),episode_instance=item.episode_instance)
                else:material["correction"]=json.loads(item.correction_json)
                pending.append(dict(kind=j[0],ordinal=j[2].ordinal,frozen_input=material))
            return dict(failure=copy.deepcopy(self._failure),unpublished=pending,close_error=copy.deepcopy(self._close_error))
    def close(self):
        """Join and close own backend; unfinished episodes are explicitly aborted."""
        self._host()
        with self._cv:
            self._closing=True
            for kind,item,admission,future in self._jobs:
                if kind=='read':future.cancel()
            self._cv.notify_all()
        self._thread.join()
        with self._cv:
            self._jobs=deque(job for job in self._jobs if job[0]!='read')
            if self._read_pending is not None and self._read_pending.done():self._read_pending=None
            if self._state not in("closed","closed_aborted"):
                self._state="closed"if self._state=="ended"or self._episode is None else"closed_aborted"
        if self._close_error is not None:raise ConsumerFailed("Backend resource close failed: "+self._close_error["message"])
        return self.poll_completions()
    def _prior_completions(self,result,admission):
        rows=result.get('prior_publications',[])
        if not isinstance(rows,list) or len(rows)>self.max_frames+1 or len(_bytes(rows))>self.max_bytes:
            raise ValueError('Background publication envelope exceeds its admission contract')
        values=[];parent=self._last_snapshot;seen=set(self._snapshot_ids)
        for row in rows:
            packet=ObservationPacket(**row['frontier_packet']);encoded=_bytes(packet.to_record())
            known=self._committed_packets.get(packet.frame_uid)
            if known is None or known['sha256']!=hashlib.sha256(encoded).hexdigest():
                raise ValueError('Background publication frontier is not a committed observation')
            checked=validated_completion(packet,row)
            target=CorrectionSnapshot.from_record(checked['target_provenance'])
            target_source=self._committed_packets.get(target.frame_id)
            if (target.episode_id,target.episode_instance)!=self._episode or target_source is None or target_source['timestamp_ns']!=target.timestamp_ns:
                raise ValueError('Background correction target source differs from committed inputs')
            if target.timestamp_ns>packet.sensor_timestamp_ns or checked['versions']['pose_map_version']!=target.native_map_version:
                raise ValueError('Background correction target/version differs')
            sid=checked['snapshot_id']
            if checked.get('parent_snapshot_id')!=parent or sid in seen:
                raise ValueError('Background publication chain differs or repeats')
            values.append(Completion('correction',Admission(admission.ordinal,packet.frame_uid,admission.submitted_monotonic_ns),
                encoded,_bytes(checked),time.monotonic_ns()))
            self._snapshot_cutoffs[sid]=dict(checked["cutoff"])
            seen.add(sid);parent=sid
        self._snapshot_ids=seen;self._last_snapshot=parent
        return values
    def _run(self):
        try:
            while True:
                with self._cv:
                    while not self._jobs and not self._closing:self._cv.wait()
                    if self._closing:break
                    job=self._jobs.popleft();self._active=job
                kind,item,admission,control=job
                work_started_ns=time.monotonic_ns()
                prior=[]
                try:
                    if kind=="read":
                        self._run_read(item,control);continue
                    if kind=="end":
                        result=(self.backend.end_episode(item) if self._pose_source=='simulator_ground_truth'
                                else self.backend.end_episode(item,frozen_correction=None))
                        with self._cv:
                            self._state="ended";self._active=None
                            control.set_result(result);self._cv.notify_all()
                        continue
                    else:
                        p=item.packet
                        if kind=="observation":
                            result=(self.backend.consume(p,item.receipt) if p.pose_provider=='simulator_ground_truth'
                                    else self.backend.consume(p,item.receipt,frozen_mapping_sample=item.mapping_sample))
                            if result.get("duplicate"):raise ValueError("Duplicate observation cannot emit another publication")
                        else:result=self.backend.flush_mapping_correction(frozen_correction=item.correction,packet=p)
                        if p.pose_provider=='simulator_ground_truth':
                            if result.get('prior_publications'):raise ValueError('Simulator provider cannot publish native correction receipts')
                            prior=[]
                        else:prior=self._prior_completions(result,admission)
                        result=dict(result);result.pop('prior_publications',None)
                        if kind=="correction"and result.get("duplicate")is True:
                            # A real backend no-op may expose only its existing
                            # snapshot. It is not a new commit/publication.
                            checked_commit(result,p,allow_noop=True)
                            with self._cv:
                                self._done.extend(prior);prior=[]
                                self._noop_corrections+=1
                                self._last_noop=dict(frame_uid=p.frame_uid,result=json.loads(_bytes(result)))
                                self._unpublished.pop(admission.ordinal);self._outstanding.pop(admission.ordinal)
                                self._completed_count+=1;self._active=None;self._cv.notify_all()
                            continue
                        result=checked_commit(result,p)
                        if p.pose_provider=='simulator_ground_truth' and result['snapshot_id'] in self._snapshot_ids:
                            raise ValueError('A distinct observation reused a published snapshot identity')
                        self._last_snapshot=result['snapshot_id'];self._snapshot_ids.add(result['snapshot_id'])
                        self._snapshot_cutoffs[result['snapshot_id']]=dict(result['cutoff'])
                        if kind=='observation' and p.pose_provider!='simulator_ground_truth':
                            self._committed_packets[p.frame_uid]=dict(sha256=hashlib.sha256(item.packet_json).hexdigest(),timestamp_ns=p.sensor_timestamp_ns)
                        value=Completion(kind,admission,item.packet_json,_bytes(result),time.monotonic_ns(),work_started_ns)
                        with self._cv:
                            self._done.extend(prior);prior=[]
                            self._done.append(value);self._unpublished.pop(admission.ordinal)
                            if kind=="observation":self._published_seq=p.capture_seq
                            self._completed_count+=1
                except BaseException as error:
                    receipt_error=None
                    reported=getattr(error,'prior_publications',[])
                    if reported:
                        try:prior.extend(self._prior_completions(dict(prior_publications=reported),admission))
                        except BaseException as invalid:receipt_error=repr(invalid)
                    with self._cv:
                        self._done.extend(prior);prior=[]
                        self._state="failed"
                        self._failure=dict(kind=kind,frame_uid=item.frame_uid if kind=="read"else item.packet.frame_uid if kind!="end"else None,error_type=type(error).__name__,message=str(error))
                        if receipt_error is not None:self._failure['prior_publication_validation_error']=receipt_error
                        if kind=="read":
                            self._read_pending=None
                            control.finished_ns=time.monotonic_ns()
                            self._finish_expired_read(control,'transport_failure',error)
                        if control is not None and not control.done():control.set_exception(error)
                        self._active=None;self._cv.notify_all()
                        while not self._closing:self._cv.wait()
                    break
                with self._cv:self._active=None;self._cv.notify_all()
        finally:
            try:self.backend.close(abort_reason=None if self._state=="ended"else"async consumer closed before successful episode end")
            except BaseException as error:
                with self._cv:self._close_error=dict(error_type=type(error).__name__,message=str(error))
            with self._cv:self._active=None;self._cv.notify_all()

