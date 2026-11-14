from pathlib import Path
import threading
from types import SimpleNamespace
from test_async_admission import LocalRPC
from test_continuous_graph import item
from poseAdapter.interfaces.mapping import MappingSessionIdentity
from graphAdapter.observation_pose.streaming_memory import StreamingMemoryBridge


def test_submit_returns_before_backend_and_events_remain_host_owned():
    gate=threading.Event();backend=LocalRPC(gate=gate);events=[];owner=threading.get_ident()
    def emit(kind,**fields):
        assert threading.get_ident()==owner
        events.append(dict(kind=kind,**fields))
    bridge=StreamingMemoryBridge(backend,SimpleNamespace(emit=emit),max_episode_observations=20,timeout=3)
    packet,arrays,sample=item(1)
    adapter=SimpleNamespace(get_mapping_session_identity=lambda:MappingSessionIdentity('unit','attempt-a'),
        get_mapping_frame_snapshot=lambda *a,**k:sample,get_mapping_correction_snapshot=lambda:None)
    try:
        admission=bridge.submit(packet,arrays['committed_receipt'],adapter)
        assert backend.entered.wait(1)
        assert admission.frame_uid==packet.frame_uid and not events and not backend.commits
        gate.set()
        bridge.end_episode(adapter,[])
        assert backend.ended and bridge.identity is None
        assert len(events)==1 and events[0]['kind']=='PublishedSnapshot'
        assert events[0]['frame_uid']==packet.frame_uid and events[0]['cutoff_event_seq']==packet.event_seq
        assert bridge.published_observations==1
    finally:gate.set();bridge.close()
    assert backend.closed


def test_log_failure_retains_commit_and_does_not_automatically_repeat_event():
    import pytest
    backend=LocalRPC();attempts=[]
    def emit(*a,**k):attempts.append(k);raise OSError('event flush failed')
    bridge=StreamingMemoryBridge(backend,SimpleNamespace(emit=emit),max_episode_observations=20,timeout=3)
    packet,arrays,sample=item(1)
    adapter=SimpleNamespace(get_mapping_session_identity=lambda:MappingSessionIdentity('unit','attempt-a'),
        get_mapping_frame_snapshot=lambda *a,**k:sample,get_mapping_correction_snapshot=lambda:None)
    try:
        bridge.submit(packet,arrays['committed_receipt'],adapter)
        done=bridge.channel.drain(3)
        with pytest.raises(OSError):bridge._emit(done)
        assert len(bridge.failure_snapshot()['unlogged_commits'])==1
        with pytest.raises(RuntimeError,match='recovery'):bridge.poll()
        assert len(attempts)==1
    finally:
        with pytest.raises(RuntimeError,match='recovery'):bridge.close()
    assert backend.closed


def test_failed_backend_end_does_not_emit_successful_terminal(tmp_path):
    import pytest
    from graphAdapter.observation_pose.aware_hook import AwarePoseHook,CaptureAttemptAborted
    events=[]
    def failed_end(*args):raise OSError('release failed')
    backend=SimpleNamespace(end_episode=failed_end,close=lambda **kw:None)
    hook=AwarePoseHook.__new__(AwarePoseHook)
    hook.memory=backend;hook.memory_stream=None;hook.pose=None;hook.macro=None;hook.storage=None
    hook._aborted=False;hook.abort_receipt=None;hook._clear_latest=lambda:None
    hook.coordinator=SimpleNamespace(root=tmp_path,episode_uid='unit',pending_endpoint={},
        emit=lambda kind,**kw:events.append(kind),end_episode=lambda *a:events.append('terminal'))
    with pytest.raises(CaptureAttemptAborted):hook.end_episode([])
    assert 'attempt_aborted' in events and 'terminal' not in events


def test_abort_waits_for_consumer_before_closing_backend(tmp_path):
    import pytest
    from graphAdapter.observation_pose.aware_hook import AwarePoseHook,CaptureAttemptAborted
    gate=threading.Event();backend=LocalRPC(gate=gate);events=[]
    coordinator=SimpleNamespace(root=tmp_path,episode_uid='unit',pending_endpoint={},emit=lambda kind,**kw:events.append(kind))
    bridge=StreamingMemoryBridge(backend,coordinator,max_episode_observations=20,timeout=3)
    packet,arrays,sample=item(1)
    adapter=SimpleNamespace(get_mapping_session_identity=lambda:MappingSessionIdentity('unit','attempt-a'),get_mapping_frame_snapshot=lambda *a,**k:sample)
    bridge.submit(packet,arrays['committed_receipt'],adapter);assert backend.entered.wait(1)
    entered=threading.Event();original_close=bridge.close
    def close():entered.set();return original_close()
    bridge.close=close
    original_backend_close=backend.close
    def checked_close(**kwargs):
        assert backend.commits==[1]
        return original_backend_close(**kwargs)
    backend.close=checked_close
    def release():assert entered.wait(1);gate.set()
    helper=threading.Thread(target=release);helper.start()
    hook=AwarePoseHook.__new__(AwarePoseHook);hook.memory=backend;hook.memory_stream=bridge
    hook.pose=None;hook.storage=None;hook.coordinator=coordinator;hook.abort_receipt=None;hook._clear_latest=lambda:None
    try:
        with pytest.raises(CaptureAttemptAborted):hook._abort_capture('test',RuntimeError('stop'),None,None)
    finally:gate.set();helper.join()
    assert backend.closed and hook.memory is None and hook.memory_stream is None
    assert (Path(hook.abort_receipt).with_name('attempt-abort-cleanup.json')).exists()


def test_failed_close_retains_unpolled_real_commit_without_emitting():
    import pytest,time
    from graphAdapter.map_memory.async_admission import ConsumerFailed
    backend=LocalRPC(close_error=True);events=[]
    bridge=StreamingMemoryBridge(backend,SimpleNamespace(emit=lambda *a,**k:events.append((a,k))),max_episode_observations=20,timeout=3)
    packet,arrays,sample=item(1)
    adapter=SimpleNamespace(get_mapping_session_identity=lambda:MappingSessionIdentity('unit','attempt-a'),get_mapping_frame_snapshot=lambda *a,**k:sample)
    bridge.submit(packet,arrays['committed_receipt'],adapter)
    with bridge.channel._cv:
        deadline=time.monotonic()+3
        while bridge.channel._unpublished or bridge.channel._active:
            remaining=deadline-time.monotonic();assert remaining>0
            bridge.channel._cv.wait(remaining)
    with pytest.raises(ConsumerFailed,match='close'):bridge.close()
    evidence=bridge.failure_snapshot()
    assert len(evidence['unlogged_commits'])==1 and evidence['unlogged_commits'][0]['frame_uid']==packet.frame_uid
    assert evidence['consumer']['close_error']['message']=='resource release failed'
    assert not events and backend.closed


def test_end_publishes_ready_observation_before_final_correction_finishes():
    from test_correction_channel import correction
    gate=threading.Event();backend=LocalRPC();events=[];finished=[]
    original=backend.dispatch
    def dispatch(message):
        if message['op']=='prepare_correction':
            assert gate.wait(3),'Final drain withheld an already committed observation'
            result=original(message);finished.append(True);return result
        return original(message)
    backend.dispatch=dispatch
    def emit(kind,**fields):
        events.append(kind)
        if kind=='PublishedSnapshot':
            assert not finished
            gate.set()
    bridge=StreamingMemoryBridge(backend,SimpleNamespace(emit=emit),max_episode_observations=20,timeout=3)
    packet,arrays,sample=item(1)
    adapter=SimpleNamespace(get_mapping_session_identity=lambda:MappingSessionIdentity('unit','attempt-a'),
        get_mapping_frame_snapshot=lambda *a,**k:sample,get_mapping_correction_snapshot=lambda:correction(sample))
    try:
        bridge.submit(packet,arrays['committed_receipt'],adapter)
        bridge.end_episode(adapter,[])
        assert events==['PublishedSnapshot','MapCorrectionPublished']
        assert backend.ended and len(backend.commits)==2
    finally:gate.set();bridge.close()


def prior_receipt(previous,packet,sample):
    from test_correction_channel import correction
    return dict(snapshot_id='b'*64,parent_snapshot_id=previous['snapshot_id'],
        versions={'pose_map_version':sample.native_map_version},
        cutoff=dict(capture_seq=packet.capture_seq,event_seq=packet.event_seq),
        frame_uid=packet.frame_uid,source_packet_event_seq=packet.event_seq,
        frontier_packet=packet.to_record(),target_provenance=correction(sample).to_record())


def test_background_publication_is_emitted_before_next_observation():
    from graphAdapter.evaluation.publications import index_publications
    backend=LocalRPC();events=[];original=backend.consume;p1,a1,m1=item(1);p2,a2,m2=item(2)
    def consume(packet,*args,**kwargs):
        previous=getattr(backend,'last_reply',None);result=original(packet,*args,**kwargs)
        if packet.capture_seq==2:result['prior_publications']=[prior_receipt(previous,p1,m1)]
        return result
    backend.consume=consume
    bridge=StreamingMemoryBridge(backend,SimpleNamespace(emit=lambda kind,**kw:events.append(dict(kind=kind,**kw))),max_episode_observations=20,timeout=3)
    current=[m1]
    adapter=SimpleNamespace(get_mapping_session_identity=lambda:MappingSessionIdentity('unit','attempt-a'),
        get_mapping_frame_snapshot=lambda *a,**k:current[0],get_mapping_correction_snapshot=lambda:None)
    try:
        bridge.submit(p1,a1['committed_receipt'],adapter);current[0]=m2
        bridge.submit(p2,a2['committed_receipt'],adapter);bridge.end_episode(adapter,[])
        assert [e['kind'] for e in events]==['PublishedSnapshot','MapCorrectionPublished','PublishedSnapshot']
        assert [e['capture_seq'] for e in events]==[1,1,2]
        assert events[1]['target_provenance']['frame_id']==p1.frame_uid
        endpoints,revisions=index_publications(events,{p.frame_uid:p.to_record() for p in [p1,p2]})
        assert len(endpoints)==2 and len(revisions)==3 and bridge.published_observations==2
    finally:bridge.close()


def test_prior_publication_survives_final_noop():
    from test_correction_channel import correction
    backend=LocalRPC(noop=True);events=[];p,a,m=item(1);original=backend.flush_mapping_correction
    def flush(*args,**kwargs):
        result=original(*args,**kwargs);prior=prior_receipt(result,p,m)
        result=dict(result,snapshot_id=prior['snapshot_id'],prior_publications=[prior]);return result
    backend.flush_mapping_correction=flush
    bridge=StreamingMemoryBridge(backend,SimpleNamespace(emit=lambda kind,**kw:events.append(kind)),max_episode_observations=20,timeout=3)
    adapter=SimpleNamespace(get_mapping_session_identity=lambda:MappingSessionIdentity('unit','attempt-a'),
        get_mapping_frame_snapshot=lambda *a,**k:m,get_mapping_correction_snapshot=lambda:correction(m))
    try:
        bridge.submit(p,a['committed_receipt'],adapter);bridge.end_episode(adapter,[])
        assert events==['PublishedSnapshot','MapCorrectionPublished']
        assert bridge.channel.status()['noop_corrections']==1
    finally:bridge.close()


def test_prior_publication_log_failure_retains_correction_and_following_commit():
    import pytest
    backend=LocalRPC();original=backend.consume;p1,a1,m1=item(1);p2,a2,m2=item(2);attempts=[]
    def consume(packet,*args,**kwargs):
        previous=getattr(backend,'last_reply',None);result=original(packet,*args,**kwargs)
        if packet.capture_seq==2:result['prior_publications']=[prior_receipt(previous,p1,m1)]
        return result
    backend.consume=consume
    def emit(kind,**fields):
        attempts.append(kind)
        if kind=='MapCorrectionPublished':raise OSError('correction log failed')
    bridge=StreamingMemoryBridge(backend,SimpleNamespace(emit=emit),max_episode_observations=20,timeout=3)
    current=[m1];adapter=SimpleNamespace(get_mapping_session_identity=lambda:MappingSessionIdentity('unit','attempt-a'),get_mapping_frame_snapshot=lambda *a,**k:current[0])
    try:
        bridge.submit(p1,a1['committed_receipt'],adapter);current[0]=m2;bridge.submit(p2,a2['committed_receipt'],adapter)
        done=bridge.channel.drain(3)
        with pytest.raises(OSError,match='correction log'):bridge._emit(done)
        pending=bridge.failure_snapshot()['unlogged_commits']
        assert [x['kind'] for x in pending]==['MapCorrectionPublished','PublishedSnapshot']
        with pytest.raises(RuntimeError,match='recovery'):bridge.poll()
        assert attempts.count('MapCorrectionPublished')==1
    finally:
        with pytest.raises(RuntimeError,match='recovery'):bridge.close()


def test_prior_publication_with_wrong_parent_is_rejected_before_emission():
    import pytest
    from test_async_admission import channel,submit
    from graphAdapter.map_memory.async_admission import ConsumerFailed
    backend=LocalRPC();original=backend.consume;p1,a1,m1=item(1)
    def consume(packet,*args,**kwargs):
        previous=getattr(backend,'last_reply',None);result=original(packet,*args,**kwargs)
        if packet.capture_seq==2:
            prior=prior_receipt(previous,p1,m1);prior['parent_snapshot_id']='f'*64
            result['prior_publications']=[prior]
        return result
    backend.consume=consume;c=channel(backend)
    try:
        submit(c,1);first=c.drain(3);assert len(first)==1
        submit(c,2)
        with pytest.raises(ConsumerFailed,match='chain'):c.drain(3)
        assert c.poll_completions()==()
    finally:c.close()


def test_worker_failure_preserves_prior_committed_correction_receipt():
    import pytest
    from test_correction_channel import correction
    from graphAdapter.map_memory.async_admission import ConsumerFailed
    backend=LocalRPC();events=[];p,a,m=item(1)
    def failed_flush(*args,**kwargs):
        error=RuntimeError('later terminal target rejected')
        error.prior_publications=[prior_receipt(backend.last_reply,p,m)]
        raise error
    backend.flush_mapping_correction=failed_flush
    bridge=StreamingMemoryBridge(backend,SimpleNamespace(emit=lambda kind,**kw:events.append(kind)),max_episode_observations=20,timeout=3)
    adapter=SimpleNamespace(get_mapping_session_identity=lambda:MappingSessionIdentity('unit','attempt-a'),
        get_mapping_frame_snapshot=lambda *a,**k:m,get_mapping_correction_snapshot=lambda:correction(m))
    try:
        bridge.submit(p,a['committed_receipt'],adapter)
        with pytest.raises(ConsumerFailed,match='terminal target'):bridge.end_episode(adapter,[])
        assert events==['PublishedSnapshot','MapCorrectionPublished']
        assert not backend.ended
    finally:bridge.close()
