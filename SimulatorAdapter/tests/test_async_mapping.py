"""Simulator pose must support bounded mapping overlap without native pose APIs."""
import hashlib,threading
import pytest
from SimulatorAdapter import SimulatorAdapter
from graphAdapter.interfaces.pose import PoseReader
from SimulatorAdapter.tests.test_pose import PoseOnly
from SimulatorAdapter.tests.test_simulator_graph_boundary import observation
from graphAdapter.map_memory.async_admission import FrozenObservation
from graphAdapter.observation_pose.streaming_memory import StreamingMemoryBridge

class Backend:
    profile={'pose_provider':'simulator_ground_truth','pose_input_mode':'provider_pose'}
    def __init__(self):self.gate=threading.Event();self.gate.set();self.frames=[];self.ends=0
    def consume(self,p,receipt,**kwargs):
        assert not kwargs, 'Simulator packet must not enter a native mapping-sample API'
        assert self.gate.wait(3)
        self.frames.append(p.frame_uid)
        return dict(frame_uid=p.frame_uid,source_packet_event_seq=p.event_seq,
            snapshot_id=hashlib.sha256((p.frame_uid+p.pose_record['episode_instance']).encode()).hexdigest(),
            versions={'pose_map_version':0},cutoff={'capture_seq':p.capture_seq,'event_seq':p.event_seq})
    def end_episode(self,cancelled,**kwargs):
        assert not kwargs, 'No native correction arguments in provider-only end'
        self.ends+=1;return {'frames':len(self.frames)}
    def close(self,abort_reason=None):pass

class Coordinator:
    def __init__(self):self.events=[];self.owner=threading.get_ident()
    def emit(self,kind,**event):
        assert threading.get_ident()==self.owner
        self.events.append(dict(kind=kind,**event))

def setup():
    simulator=PoseOnly();provider=SimulatorAdapter(simulator,rotation_matrix=lambda x:x)
    provider.reset_episode('unit');reader=PoseReader(provider,source='simulator_ground_truth')
    return simulator,provider,reader

def test_frozen_gt_pose_needs_no_native_mapping_sample():
    sim,provider,reader=setup()
    try:
        packet,args=observation(1,reader,sim);instance=provider.get_mapping_session_identity().episode_instance
        frozen=FrozenObservation.create(packet,args['committed_receipt'],mapping_sample=None,episode_instance=instance)
        assert frozen.mapping_sample is None
        assert frozen.packet.pose_record['episode_instance']==instance
        with pytest.raises(ValueError,match='session'):
            FrozenObservation.create(packet,args['committed_receipt'],mapping_sample=None,episode_instance='wrong')
    finally:provider.shutdown()

def test_stream_overlaps_and_drains_without_native_calls_or_previous_episode_snapshot():
    sim,provider,reader=setup();backend=Backend();coordinator=Coordinator()
    stream=StreamingMemoryBridge(backend,coordinator,max_episode_observations=8,capacity=2,timeout=3)
    try:
        backend.gate.clear()
        p,a=observation(1,reader,sim)
        stream.submit(p,a['committed_receipt'],provider)
        assert stream.last_publication is None and not coordinator.events
        # Admission returned while actual consumption is still blocked.
        assert stream.channel.status()['unacknowledged']==1
        backend.gate.set();stream.end_episode(provider,[])
        assert stream.published_observations==1 and backend.ends==1
        assert all(e['kind']=='PublishedSnapshot' for e in coordinator.events)
        previous=stream.last_publication
        provider.reset_episode('unit');backend.gate.clear()
        p,a=observation(1,reader,sim);stream.submit(p,a['committed_receipt'],provider)
        assert stream.last_publication is None, 'Old episode snapshot cannot leak into new decision'
        backend.gate.set();stream.end_episode(provider,[])
        assert stream.last_publication['snapshot_id']!=previous['snapshot_id']
    finally:
        backend.gate.set();stream.close();provider.shutdown()

def test_visible_snapshot_lag_is_bounded_at_decision():
    sim,provider,reader=setup();backend=Backend();coordinator=Coordinator()
    stream=StreamingMemoryBridge(backend,coordinator,max_episode_observations=8,capacity=2,timeout=3)
    try:
        for seq in (1,2):
            p,a=observation(seq,reader,sim);stream.submit(p,a['committed_receipt'],provider)
        visible=stream.await_visible(2,max_capture_lag=1)
        assert visible['capture_lag']<=1 and visible['visible_capture_seq']>=1
        assert visible['snapshot_id']==stream.last_publication['snapshot_id']
        stream.end_episode(provider,[])
        assert [e['capture_seq'] for e in coordinator.events]==[1,2]
    finally:stream.close();provider.shutdown()
