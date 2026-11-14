import copy,threading,time
from concurrent.futures import CancelledError
import pytest
from graphAdapter.tests.test_async_admission import LocalRPC,channel,submit,finish
from graphAdapter.map_memory.async_admission import ReadAdmissionFull,ConsumerFailed,ReadDeadlineExpired

class ReadBackend(LocalRPC):
    def __init__(self,**kw):
        super().__init__(**kw);self.read_entered=threading.Event();self.read_gate=None
        self.reads=[];self.read_error=None;self.threads=[]
    def consume(self,*a,**kw):
        self.threads.append(threading.get_ident());return super().consume(*a,**kw)
    def read_memory(self,request):
        self.threads.append(threading.get_ident());self.read_entered.set()
        if self.read_gate is not None:assert self.read_gate.wait(3)
        self.reads.append(copy.deepcopy(request))
        if self.read_error:raise self.read_error
        return {'request_id':request['request_id'],'episode_uid':request['query']['episode_uid'],
            'episode_instance':request['episode_instance'],'snapshot_id':request['query']['snapshot_id'],'value':'read-only'}

def request(c,request_id='r1'):
    return {'protocol_version':1,'request_id':request_id,'episode_instance':'attempt-a','mode':'graph_image_only','budget':8,
        'query':{'episode_uid':'unit','snapshot_id':c._last_snapshot,'current_frame_uid':c._last.packet.frame_uid,
            'current_capture_seq':c._admitted_seq,'cutoff_capture_seq':c._snapshot_cutoffs[c._last_snapshot]['capture_seq'],
            'cutoff_event_seq':c._snapshot_cutoffs[c._last_snapshot]['event_seq'],'instruction':'Pass the door.'}}

def ready():
    b=ReadBackend();c=channel(b);submit(c,1);c.drain(3);return b,c

def test_read_uses_same_consumer_between_complete_observations_and_no_publication():
    b,c=ready()
    try:
        before=c.status()['published_seq'];future=c.submit_read(request(c));result=c.wait_read(future,3)
        times=c.read_timing(future)
        assert times['submitted_ns']<=times['started_ns']<=times['finished_ns']<=times['observed_ns']
        assert times['queued_jobs_ahead']==0 and not times['cancelled']
        assert result['value']=='read-only'and c.status()['published_seq']==before
        assert c.poll_completions()==()and len(set(b.threads))==1 and b.threads[0]!=threading.get_ident()
        submit(c,2);done=finish(c);assert len(done)==1 and b.commits==[1,2]
    finally:c.close()

def test_running_read_timeout_keeps_reply_with_its_future_and_blocks_queue_growth():
    b,c=ready();b.read_gate=threading.Event()
    try:
        first=c.submit_read(request(c));assert b.read_entered.wait(2)
        with pytest.raises(ReadDeadlineExpired):c.wait_read(first,.001)
        times=c.read_timing(first)
        assert not times['cancelled'] and times['started_ns'] is not None and times['finished_ns'] is None
        with pytest.raises(ReadAdmissionFull):c.submit_read(request(c,'r2'))
        b.read_gate.set();assert first.result(3)['request_id']=='r1'
        second=c.submit_read(request(c,'r2'));assert c.wait_read(second,3)['request_id']=='r2'
        assert c.status()['read_timeouts']==1 and c.status()['failure'] is None
        finish(c)
    finally:b.read_gate.set();c.close()

def test_queued_timeout_cancels_before_backend_work():
    b,c=ready();b.gate=threading.Event();b.entered.clear()
    try:
        submit(c,2);assert b.entered.wait(2)
        future=c.submit_read(request(c))
        with pytest.raises(ReadDeadlineExpired):c.wait_read(future,.001)
        times=c.read_timing(future)
        assert times['active_at_admission']=='observation' and times['cancelled']
        assert times['started_ns'] is None and times['finished_ns'] is None
        terminal=future.expiry_receipt.result(1)
        assert terminal['outcome']=='cancelled_before_start' and terminal['started_ns'] is None and terminal['finished_ns'] is None
        assert terminal['terminal_ns']>=terminal['submitted_ns']
        b.gate.set();c.drain(3)
        assert future.cancelled()and b.reads==[]
        finish(c)
    finally:b.gate.set();c.close()

def test_read_validation_error_does_not_poison_map_transport():
    b,c=ready();b.read_error=ValueError('bad query')
    try:
        f=c.submit_read(request(c))
        with pytest.raises(ValueError):c.wait_read(f,3)
        assert c.status()['failure']is None
        submit(c,2);finish(c);assert b.commits==[1,2]
    finally:c.close()

def test_transport_failure_marks_consumer_failed_instead_of_reusing_socket():
    b,c=ready();b.read_error=EOFError('socket lost')
    try:
        f=c.submit_read(request(c))
        with pytest.raises(EOFError):c.wait_read(f,3)
        with pytest.raises(ConsumerFailed):c.drain(3)
        assert c.failure_snapshot()['failure']['kind']=='read'
    finally:c.close()

def test_read_reply_identity_mismatch_fails_without_becoming_mapping_commit():
    b,c=ready();original=b.read_memory
    def wrong(req):return dict(original(req),snapshot_id='wrong')
    b.read_memory=wrong
    try:
        with pytest.raises(ValueError):c.wait_read(c.submit_read(request(c)),3)
        assert c.status()['published_seq']==1 and not c.poll_completions()
        finish(c)
    finally:c.close()

def test_cross_session_and_unpublished_snapshot_read_rejected():
    b,c=ready()
    try:
        req=request(c);req['episode_instance']='other'
        with pytest.raises(ValueError):c.submit_read(req)
        req=request(c);req['query']['snapshot_id']='f'*64
        with pytest.raises(ValueError):c.submit_read(req)
        finish(c)
        with pytest.raises(RuntimeError):c.submit_read(request(c))
    finally:c.close()

    

def test_remote_timeout_is_not_a_local_host_read_deadline():
    b,c=ready();b.read_error=TimeoutError('backend socket timeout')
    try:
        f=c.submit_read(request(c))
        with pytest.raises(TimeoutError) as caught:c.wait_read(f,3)
        assert not isinstance(caught.value,ReadDeadlineExpired)
        assert c.status()['failure']['kind']=='read'
        with pytest.raises(ConsumerFailed):c.drain(3)
    finally:c.close()


@pytest.mark.parametrize('error,outcome',[(None,'late_reply'),(ValueError('bad material'),'late_error'),(OSError('broken socket'),'transport_failure')])
def test_late_terminal_receipt_keeps_original_identity_and_no_payload(error,outcome):
    from types import SimpleNamespace
    from graphAdapter.observation_pose.streaming_memory import StreamingMemoryBridge
    b,c=ready();b.read_error=error;b.read_gate=threading.Event()
    events=[]
    bridge=StreamingMemoryBridge.__new__(StreamingMemoryBridge)
    bridge.channel=c;bridge.identity=('unit','attempt-a');bridge._expired_reads=[]
    bridge.coordinator=SimpleNamespace(emit=lambda kind,**fields:events.append((kind,fields)))
    try:
        raw=request(c,'late-original')
        f=c.submit_read(raw);assert b.read_entered.wait(2)
        with pytest.raises(ReadDeadlineExpired):c.wait_read(f,.001)
        raw['query']['decision_id']=7  # v1 fixture lacks this v3 host field; production supplies it.
        bridge.track_expired_read(raw,f.expiry_receipt);assert not events
        b.read_gate.set()
        terminal=f.expiry_receipt.result(3)
        assert terminal['outcome']==outcome and terminal['started_ns']<=terminal['finished_ns']==terminal['terminal_ns']
        assert set(terminal)=={'outcome','submitted_ns','started_ns','finished_ns','terminal_ns','error_type'}
        bridge._flush_expired_reads();bridge._flush_expired_reads();assert len(events)==1
        kind,record=events[0];assert kind=='MemoryExpiredReadFinished' and record['decision_id']==7 and record['request_id']=='late-original'
        assert record['snapshot_id']==raw['query']['snapshot_id'] and record['frame_uid']==raw['query']['current_frame_uid']
        assert record['error_type']==(type(error).__name__ if error else None)
        if outcome!='transport_failure':
            b.read_error=None
            follow=c.wait_read(c.submit_read(request(c,'next')),3);assert follow['request_id']=='next'
            finish(c)
        else:assert c.status()['failure']['kind']=='read'
    finally:b.read_gate.set();c.close()


def test_completed_read_does_not_win_an_expired_absolute_deadline():
    b,c=ready()
    try:
        first=c.submit_read(request(c,'late-done'))
        assert first.result(3)['request_id']=='late-done'
        with pytest.raises(ReadDeadlineExpired):
            c.wait_read_until(first,first.finished_ns-1)
        receipt=first.expiry_receipt.result(1)
        assert receipt['outcome']=='late_reply' and receipt['terminal_ns']==first.finished_ns
        second=c.submit_read(request(c,'on-time-done'))
        assert second.result(3)['request_id']=='on-time-done'
        assert c.wait_read_until(second,second.finished_ns)['request_id']=='on-time-done'
        assert second.expiry_receipt is None
        finish(c)
    finally:c.close()
