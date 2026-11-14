import numpy as np
import pytest
from types import SimpleNamespace
from SimulatorAdapter import SimulatorAdapter

class PoseOnly:
    def __init__(self):self.position=np.zeros(3);self.rotation=np.eye(3);self.reads=0
    def get_agent_state(self,agent_id=0):
        self.reads+=1
        class State:
            @property
            def sensor_states(self):raise AssertionError('Sensor state leak')
        state=State();state.position=self.position;state.rotation=self.rotation;return state
    def __getattr__(self,key):raise AssertionError('Forbidden simulator access: '+key)

def test_pose_only_axes_cache_and_source():
    sim=PoseOnly();adapter=SimulatorAdapter(sim,rotation_matrix=lambda r:r)
    adapter.reset_episode('ep');sim.position=np.array([0.,0.,-2.])
    pose=adapter.push_observation(frame_id='ep:1',timestamp_ns=1)
    np.testing.assert_allclose(pose.T_map_base[:3,3],[2.,0.,0.],atol=1e-12)
    sim.position=np.array([-1.,3.,-2.]);second=adapter.push_observation(frame_id='ep:2',timestamp_ns=2)
    np.testing.assert_allclose(second.T_map_base[:3,3],[2.,1.,3.],atol=1e-12)
    reads=sim.reads;assert adapter.push_observation(frame_id='ep:2',timestamp_ns=2) is second and sim.reads==reads
    matrix=second.T_map_base;matrix[0,3]=999;assert second.T_map_base[0,3]==2
    row=second.to_record();assert row['source']=='simulator_ground_truth' and 'measurement_support' not in row['diagnostics']
    assert 'rtab_keyframe_id' not in row
    with pytest.raises(ValueError):adapter.get_pose_for_frame('ep:2',timestamp_ns=1)
    before=adapter.get_mapping_session_identity();adapter.reset_episode('ep')
    assert before.episode_instance!=adapter.get_mapping_session_identity().episode_instance
    with pytest.raises(KeyError):adapter.get_pose_for_frame('ep:2')
    adapter.shutdown()
    with pytest.raises(RuntimeError):adapter.push_observation(frame_id='ep:3',timestamp_ns=3)


def test_failed_vector_reset_preserves_rpc_binding_and_cached_session():
    from SimulatorAdapter.host_bridge import _VectorPoseAdapter,_VectorPoseSource
    observed=[]
    class RPC:
        def call_at(self,index,method,args):
            episode=args['expected_episode_uid'];observed.append(episode)
            if episode=='broken':raise ValueError('injected endpoint failure')
            row=dict(episode_uid=episode,T_episode_base=np.eye(4).tolist())
            if args['pose_session'] is None:row['pose_session']='a'*32
            return row
    provider=_VectorPoseAdapter(_VectorPoseSource(RPC(),0,'test'))
    provider.reset_episode('original')
    first=provider.push_observation(frame_id='original:1',timestamp_ns=1)
    session=provider.get_mapping_session_identity()
    with pytest.raises(ValueError,match='injected'):provider.reset_episode('broken')
    assert provider.get_mapping_session_identity()==session and provider.get_pose_for_frame('original:1') is first
    with pytest.raises(ValueError):provider.push_observation(frame_id='original:1',timestamp_ns=True)
    provider.push_observation(frame_id='original:2',timestamp_ns=2)
    assert observed==['original','original','broken','original']
    provider.reset_episode('next')
    with pytest.raises(KeyError):provider.get_pose_for_frame('original:1')
    provider.shutdown()
    with pytest.raises(RuntimeError,match='closed'):provider.reset_episode('next')


def test_public_clock_matches_pose_adapter_contract():
    from poseAdapter.pose_sync import logical_sensor_timestamp
    for rate in [60,120,128,10**9]:
        for sequence in [0,1,2,501,2**53+1]:
            assert SimulatorAdapter.logical_sensor_timestamp(sequence,rate)==logical_sensor_timestamp(sequence,rate)
    for bad in (True,False,0,60.,10**9+1):
        with pytest.raises(ValueError):SimulatorAdapter.logical_sensor_timestamp(1,bad)
