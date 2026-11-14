import numpy as np
import pytest
from types import SimpleNamespace
from SimulatorAdapter import SimulatorAdapter
from graphAdapter.interfaces.pose import PoseFrame,PoseReader
from SimulatorAdapter.tests.test_pose import PoseOnly
from test_continuous_graph import item
from poseAdapter.interfaces.mapping import MappingSessionIdentity

def test_simulator_shared_contract_is_pose_only_and_session_bound():
    sim=PoseOnly();provider=SimulatorAdapter(sim,rotation_matrix=lambda x:x);provider.reset_episode('ep')
    reader=PoseReader(provider,source='simulator_ground_truth');sim.position=np.array([0.,0.,-2.])
    frame=reader.capture(episode_id='ep',frame_id='ep:1',timestamp_ns=1)
    np.testing.assert_allclose(np.asarray(frame.T_map_base)[:3,3],[2.,0.,0.])
    row=frame.to_record();assert PoseFrame.from_record(row)==frame
    assert set(row)=={'schema_version','source','episode_id','episode_instance','frame_id','timestamp_ns','map_version','valid','T_map_base','T_odom_base','T_map_odom'}
    with pytest.raises(TypeError):PoseFrame.from_record(dict(row,goal_position=[0,0,0]))
    with pytest.raises(ValueError,match='source'):PoseReader(provider,source='cuvslam_rtabmap_rgbd').read(episode_id='ep',frame_id='ep:1',timestamp_ns=1)
    saved=frame.episode_instance;provider.reset_episode('ep');provider.push_observation(frame_id='ep:1',timestamp_ns=1)
    with pytest.raises(ValueError,match='session'):reader.read(episode_id='ep',frame_id='ep:1',timestamp_ns=1,expected_instance=saved)

def test_native_provider_uses_same_reader_without_simulator_fields():
    p,a,m=item(1);record=p.to_record()['pose_record']
    record['forbidden_scene_payload']='must not be serialized'
    provider=SimpleNamespace(reset_episode=lambda *a,**k:None,push_observation=lambda **k:None,shutdown=lambda:None,
        get_mapping_session_identity=lambda:MappingSessionIdentity('unit','attempt-a'),
        get_frame_snapshot=lambda *a,**k:(SimpleNamespace(to_record=lambda:record),m.bindings))
    frame=PoseReader(provider,source='cuvslam_rtabmap_rgbd').read(episode_id='unit',frame_id=p.frame_uid,timestamp_ns=p.sensor_timestamp_ns)
    assert frame.valid and 'forbidden_scene_payload' not in frame.to_record()
    record['diagnostics']['measurement_support']['used']=0
    with pytest.raises(ValueError,match='support'):PoseReader(provider,source='cuvslam_rtabmap_rgbd').read(episode_id='unit',frame_id=p.frame_uid,timestamp_ns=p.sensor_timestamp_ns)


def test_pose_reader_does_not_materialize_history(monkeypatch):
    sim=PoseOnly()
    provider=SimulatorAdapter(sim,rotation_matrix=lambda v:v)
    provider.reset_episode("e")
    for i in range(3):
        sim.position=np.array([i,0.,0.])
        provider.push_observation(frame_id=f"e:{i}",timestamp_ns=i)
    exact,full=provider.get_frame_snapshot("e:0",timestamp_ns=0,episode_id="e")
    assert len(full["pose_anchors"])==3
    def reject_full_history():
        raise AssertionError("pose-only read expanded mapping anchors")
    monkeypatch.setattr(provider,"spatial_bindings",reject_full_history)
    reader=PoseReader(provider,source="simulator_ground_truth")
    reads=sim.reads
    got=reader.read(episode_id="e",frame_id="e:0",timestamp_ns=0)
    assert sim.reads==reads and np.array_equal(got.T_map_base,exact.T_map_base)
    _,compact=provider.get_pose_only_snapshot("e:0",timestamp_ns=0,episode_id="e")
    assert compact=={k:v for k,v in full.items() if k!="pose_anchors"}
    with pytest.raises(ValueError,match="timestamp"):reader.read(episode_id="e",frame_id="e:0",timestamp_ns=2)
    provider.shutdown()


def test_same_name_reset_between_check_and_insert_does_not_write_to_new_session(monkeypatch):
    from graphAdapter.interfaces.pose.contracts import PoseSessionChanged
    sim=PoseOnly();provider=SimulatorAdapter(sim,rotation_matrix=lambda v:v);provider.reset_episode("same")
    original=provider.get_mapping_session_identity()
    reader=PoseReader(provider,source="simulator_ground_truth")
    insert=provider.push_observation_if_current
    def reset_then_insert(expected,**args):
        provider.reset_episode("same")
        return insert(expected,**args)
    monkeypatch.setattr(provider,"push_observation_if_current",reset_then_insert)
    with pytest.raises(PoseSessionChanged):
        reader.capture(episode_id="same",frame_id="same:f1",timestamp_ns=1,expected_instance=original.episode_instance)
    assert provider.get_mapping_session_identity()!=original and provider.get_status()["frames"]==0
    assert sim.reads==2


def test_duplicate_read_and_failed_reset_keep_original_bridge_binding(monkeypatch):
    from graphAdapter.interfaces.pose.contracts import PoseSessionChanged
    from graphAdapter.observation_pose.pose_bridge import PoseBridge
    from graphAdapter.observation_pose.tests.suite import cal,aligned
    from poseAdapter.coordinate.calibration import DepthSpec
    sim=PoseOnly();provider=SimulatorAdapter(sim,rotation_matrix=lambda v:v)
    bridge=PoseBridge(None,None,cal(),aligned_depth_spec=DepthSpec("meters","z","float32",0,10),adapter=provider,pose_provider="simulator_ground_truth")
    bridge.reset("ep");value=aligned();original=bridge.ingest("ep:f1",1,value);session=bridge.pose_session
    sim.position=np.array([np.nan,0,0])
    with pytest.raises(ValueError):bridge.reset("failed")
    assert bridge.pose_session==session and bridge.episode_uid=="ep" and bridge.latest_timestamp==1
    assert bridge.ingest("ep:f1",1,value)==original
    with pytest.raises(ValueError):provider.get_pose_for_frame("ep:f1",timestamp_ns=True)
    sim.position=np.zeros(3);provider.reset_episode("ep")
    provider.push_observation(frame_id="ep:f1",timestamp_ns=1)
    with pytest.raises(PoseSessionChanged):bridge.ingest("ep:f1",1,value)
    assert bridge.pose_session==session
    provider.shutdown()
    with pytest.raises(PoseSessionChanged):bridge.ingest("ep:f1",1,value)


@pytest.mark.parametrize('guarded', [True, False])
def test_simulator_capture_passes_frame_identity_only(monkeypatch, guarded):
    provider = SimulatorAdapter(PoseOnly(), rotation_matrix=lambda matrix: matrix)
    provider.reset_episode('ep')
    seen = []
    original = provider.push_observation

    def record(**kwargs):
        seen.append(set(kwargs))
        return original(**kwargs)

    monkeypatch.setattr(provider, 'push_observation', record)
    if not guarded:
        monkeypatch.setattr(provider, 'push_observation_if_current', None)
    try:
        frame = PoseReader(provider, source='simulator_ground_truth').capture(
            episode_id='ep', frame_id='ep:f1', timestamp_ns=1,
            rgb=object(), depth=object(), action='move_forward', collided=True,
        )
        assert frame.valid
        assert seen == [{'frame_id', 'timestamp_ns'}]
    finally:
        provider.shutdown()


def test_native_capture_receives_the_callers_sensor_inputs():
    packet, _, mapping = item(1)
    pose = packet.to_record()['pose_record']
    seen = []
    provider = SimpleNamespace(
        reset_episode=lambda *args, **kwargs: None,
        shutdown=lambda: None,
        get_mapping_session_identity=lambda: MappingSessionIdentity('unit', 'instance-a'),
        push_observation=lambda **kwargs: seen.append(kwargs),
        get_frame_snapshot=lambda *args, **kwargs: (SimpleNamespace(to_record=lambda: pose), mapping.bindings),
    )
    inputs = dict(rgb=object(), depth=object(), collided=False, action='move_forward')
    frame = PoseReader(provider, source='cuvslam_rtabmap_rgbd').capture(
        episode_id='unit', frame_id=packet.frame_uid, timestamp_ns=packet.sensor_timestamp_ns, **inputs)
    assert frame.valid
    assert seen == [dict(frame_id=packet.frame_uid, timestamp_ns=packet.sensor_timestamp_ns, **inputs)]
