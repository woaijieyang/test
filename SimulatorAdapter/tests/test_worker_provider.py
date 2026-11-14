import pytest
from graphAdapter.map_memory.worker import MemoryWorkerClient,validate_mapping_profile
from SimulatorAdapter.tests.test_pose import PoseOnly
from SimulatorAdapter import SimulatorAdapter
from graphAdapter.interfaces.pose import PoseReader
from SimulatorAdapter.tests.test_simulator_graph_boundary import observation
from test_continuous_graph import item

def profile():return dict(pose_provider='simulator_ground_truth',pose_input_mode='provider_pose',stage='001',simulator_pose_diagnostic=True)

def test_profile_rejects_ambiguous_and_native_correction_modes():
    p=profile();assert validate_mapping_profile(p)=='provider_pose'
    assert validate_mapping_profile(dict(p,stage='002',async_admission=True))=='provider_pose'
    for extra in [dict(pose_input_mode='continuous'),dict(stage='999'),dict(simulator_pose_diagnostic=False),dict(async_admission=1),dict(background_correction={'enabled':True})]:
        with pytest.raises(ValueError):validate_mapping_profile(dict(p,**extra))

def test_client_transports_packet_without_adapter_or_native_sampling():
    sim=PoseOnly();adapter=SimulatorAdapter(sim,rotation_matrix=lambda x:x);adapter.reset_episode('unit')
    packet,arrays=observation(1,PoseReader(adapter,source='simulator_ground_truth'),sim)
    client=MemoryWorkerClient.__new__(MemoryWorkerClient);client.profile=profile();client.active_episode='unit';client.count=0;client._begin_episode=lambda p:None
    calls=[]
    def call(m):
        calls.append(m)
        if m['op']=='prepare':return {'result':dict(duplicate=False,target_pose_map_version=0,candidate_hash='prepared')}
        return {'result':dict(snapshot_id='a'*64,versions={'pose_map_version':0},cutoff={'capture_seq':packet.capture_seq,'event_seq':packet.event_seq})}
    client.call=call
    result=client.consume(packet,arrays['committed_receipt'])
    assert result['frame_uid']==packet.frame_uid and [m['op'] for m in calls]==['prepare','commit']
    assert calls[0]['packet']['pose_provider']=='simulator_ground_truth' and 'mapping_sample' not in calls[0]
    with pytest.raises(ValueError):client.consume(packet,arrays['committed_receipt'],pose_adapter=adapter)
    native,native_arrays,_=item(2)
    with pytest.raises(ValueError,match='provider'):client.consume(native,native_arrays['committed_receipt'])
    assert len(calls)==2
