import json
from pathlib import Path
import numpy as np
import pytest
from SimulatorAdapter import SimulatorAdapter
from graphAdapter.observation_pose.aware_hook import AwarePoseHook
from graphAdapter.observation_pose.tests.fixtures import sensor_spec
from SimulatorAdapter.tests.test_pose import PoseOnly
from graphAdapter.observation_packet import require_same_frame

def profile():
    root=Path(__file__).resolve().parents[3]
    p=json.loads((root/'src/graphAdapter/observation_pose/profiles/000_pose_shadow.json').read_bytes())
    p.update(stage='001',simulator_pose_diagnostic=True,pose_provider='simulator_ground_truth',pose_sampling='primitive_endpoints')
    p.pop('map_memory',None);return p

def test_hook_reads_truth_at_endpoint_and_preserves_observation_binding(tmp_path):
    sim=PoseOnly();created=[]
    def factory(*args):
        value=SimulatorAdapter(sim,rotation_matrix=lambda x:x);created.append(value);return value
    hook=AwarePoseHook(tmp_path/'observations',profile(),adapter_factory=factory)
    rgb=np.zeros((8,8,3),np.uint8);depth=np.ones((8,8),np.float32)
    try:
        first=hook.reset('ep',sensor_spec(),rgb,depth,1)
        assert first.pose_provider=='simulator_ground_truth' and first.pose_record['geometry_status']=='available'
        assert hook.native_initialization_attempts==0 and hook.provider_initialization_attempts==1
        sim.position=np.array([0.,0.,-.25]);hook.begin_macro(1,1)
        second=hook.capture(rgb,depth,2,action_id=1)
        assert second.capture_seq==2 and second.pose_record['source']=='simulator_ground_truth'
        np.testing.assert_allclose(np.asarray(second.pose_record['T_map_base'])[:3,3],[.25,0,0])
        assert require_same_frame(hook.latest_geometry_input,hook.latest_perception_input)
        packet,receipt=hook.committed_endpoint();assert receipt['committed'] and packet is second
        assert sim.reads==3  # reset origin + one pose read per captured observation
    finally:hook.close()
    assert created[0].closed

def test_episode_reset_and_shutdown_release_host_map_cache(tmp_path):
    sim=PoseOnly()
    hook=AwarePoseHook(tmp_path/'release',profile(),adapter_factory=lambda *args:SimulatorAdapter(sim,rotation_matrix=lambda v:v))
    rgb=np.zeros((8,8,3),np.uint8)
    depth=np.ones((8,8),np.float32)
    try:
        hook.global_map_tile_cache=object()
        hook.reset('one',sensor_spec(),rgb,depth,1)
        assert hook.global_map_tile_cache is None
        from graphAdapter.map_memory.storage.pages import EpisodeImageCache
        image_cache=EpisodeImageCache(tmp_path,1024,episode='one')
        from graphAdapter.map_memory.retrieval.input_audit import AttachmentFeatureCache
        cache=AttachmentFeatureCache(1024)
        cache.signature=('previous-model',)
        hook.attachment_feature_cache=cache
        hook.retrieval_image_cache=image_cache
        hook.global_map_tile_cache=object()
        hook.end_episode(())
        assert hook.global_map_tile_cache is None and hook.retrieval_image_cache is None and image_cache.closed
        assert hook.attachment_feature_cache is None and cache.signature is None
        hook.reset('two',sensor_spec(),rgb,depth,1)
        hook.global_map_tile_cache=object()
    finally:
        hook.close()
    assert hook.global_map_tile_cache is None

def test_hook_requires_explicit_diagnostic_source_selection(tmp_path):
    p=profile();p['simulator_pose_diagnostic']=False
    with pytest.raises(ValueError,match='diagnostic'):AwarePoseHook(tmp_path,p,adapter_factory=lambda *a:None)


def test_hook_aborts_replaced_session_and_keeps_failed_frame_out_of_stream(tmp_path):
    from graphAdapter.observation_pose.aware_hook import CaptureAttemptAborted
    sim=PoseOnly();provider=SimulatorAdapter(sim,rotation_matrix=lambda v:v)
    hook=AwarePoseHook(tmp_path/"events",profile(),adapter_factory=lambda *args:provider)
    rgb=np.zeros((8,8,3),np.uint8);depth=np.ones((8,8),np.float32)
    try:
        first=hook.reset("same",sensor_spec(),rgb,depth,1)
        provider.reset_episode("same")
        hook.begin_macro(1,1)
        with pytest.raises(CaptureAttemptAborted):hook.capture(rgb,depth,2,action_id=1,collision=False)
        assert hook.latest_packet is None and provider.get_status()["frames"]==0
        packets=[json.loads(l) for l in (hook.coordinator.root/"observation-packets.jsonl").read_text().splitlines()]
        assert [p["frame_uid"] for p in packets]==[first.frame_uid]
    finally:hook.close()


def test_nonfinite_position_archives_unavailable_frame_then_recovers(tmp_path):
    from graphAdapter.observation_pose.provider_contract import audit_simulator_endpoints
    sim=PoseOnly();provider=SimulatorAdapter(sim,rotation_matrix=lambda v:v)
    hook=AwarePoseHook(tmp_path/"bad-pose",profile(),adapter_factory=lambda *args:provider)
    rgb=np.zeros((8,8,3),np.uint8);depth=np.ones((8,8),np.float32)
    try:
        first=hook.reset("ep",sensor_spec(),rgb,depth,1);sim.position=np.array([np.nan,0,0])
        hook.begin_macro(1,1);bad=hook.capture(rgb,depth,2,action_id=1,collision=False)
        assert bad.raw_rgb_ref and bad.raw_depth_ref and bad.aligned_ref
        assert bad.pose_record["episode_instance"]==first.pose_record["episode_instance"]
        assert bad.pose_record["geometry_status"]=="unavailable" and bad.pose_record["T_map_camera_cv"] is None
        sim.position=np.array([0.,0.,-.5]);hook.begin_macro(1,1)
        good=hook.capture(rgb,depth,3,action_id=1,collision=False)
        assert good.pose_record["geometry_status"]=="available" and provider.get_status()["frames"]==2
        events=[json.loads(l) for l in (hook.coordinator.root/"flow_trace.jsonl").read_text().splitlines()]
        assert audit_simulator_endpoints([x.to_record()for x in (first,bad,good)],events)["valid_pose_endpoints"]==2
    finally:hook.close()

def test_vector_pose_measurement_failure_keeps_environment_and_rgb_flow(tmp_path,monkeypatch):
    import copy
    import quaternion
    from types import SimpleNamespace as NS
    from case1_runtime.episode_scope import episode_scope
    from graphAdapter.observation_pose.aware_hook import CaptureAttemptAborted
    from graphAdapter.observation_pose.provider_contract import audit_simulator_endpoints
    from SimulatorAdapter.host_bridge import pose_rpc_reply,_VectorPoseSource,_VectorPoseAdapter,profile_identity
    cfg=profile();path=tmp_path/'profile.json';path.write_text(json.dumps(cfg))
    monkeypatch.setenv('CASE2_HOOK_MODE','on')
    monkeypatch.setenv('CASE2_POSE_PROFILE',str(path));monkeypatch.setenv('CASE2_DATASET_KEY','r2r')
    monkeypatch.setenv('CASE2_RUN_UID','fault-test')
    episode=NS(scene_id='fixture/test.glb',episode_id='fixture',instruction=NS(instruction_id=2))
    uid=episode_scope(episode)['episode_uid']
    rotation=np.quaternion(1,0,0,0);calls=[];replace_episode=False
    def get_state(_):
        calls.append(1)
        if replace_episode:env._env.current_episode=copy.copy(episode)
        return NS(position=np.array([0.,0.,-.2*len(calls)]),rotation=rotation)
    env=NS(_env=NS(current_episode=episode,sim=NS(get_agent_state=get_state)))
    replies=[]
    class RPC:
        def call_at(self,index,method,args):
            row=pose_rpc_reply(env,**args);replies.append(row);return row
    provider=_VectorPoseAdapter(_VectorPoseSource(RPC(),0,profile_identity(cfg)))
    hook=AwarePoseHook(tmp_path/'packets',cfg,adapter_factory=lambda *args:provider)
    rgb=np.zeros((8,8,3),np.uint8);depth=np.ones((8,8),np.float32)
    try:
        start=hook.reset(uid,sensor_spec(),rgb,depth,1)
        rotation=np.quaternion(0,0,0,0);hook.begin_macro(1,1)
        missing=hook.capture(rgb,depth,2,action_id=1,collision=False)
        assert replies[-1]==dict(episode_uid=uid,pose_error='invalid_measurement')
        assert missing.raw_rgb_ref and missing.aligned_ref and not missing.pose_record['valid']
        assert all(missing.pose_record[k] is None for k in ('T_odom_base','T_map_base','T_map_camera_cv'))
        assert provider.get_status()['frames']==1
        rotation=np.quaternion(-1,0,0,0);hook.begin_macro(1,1)
        recovered=hook.capture(rgb,depth,3,action_id=1,collision=False)
        assert recovered.pose_record['valid'] and provider.get_status()['frames']==2
        assert provider.get_mapping_session_identity().episode_instance==start.pose_record['episode_instance']
        events=[json.loads(l)for l in (hook.coordinator.root/'flow_trace.jsonl').read_text().splitlines()]
        assert audit_simulator_endpoints([p.to_record()for p in (start,missing,recovered)],events)['valid_pose_endpoints']==2
        replace_episode=True;hook.begin_macro(1,1)
        with pytest.raises(CaptureAttemptAborted):hook.capture(rgb,depth,4,action_id=1,collision=False)
        assert replies[-1]==dict(episode_uid=uid,pose_error='session_changed')
        assert hook.latest_packet is None and provider.closed and provider.get_status()['frames']==0
        packets=[json.loads(l)for l in (hook.coordinator.root/'observation-packets.jsonl').read_text().splitlines()]
        assert [p['frame_uid'] for p in packets]==[p.frame_uid for p in (start,missing,recovered)]
    finally:hook.close()


def test_falsey_injected_pose_provider_is_used_without_native_fallback(tmp_path):
    class Provider(SimulatorAdapter):
        def __bool__(self):
            return False

    provider = Provider(PoseOnly(), rotation_matrix=lambda value: value)
    hook = AwarePoseHook(tmp_path / 'observations', profile(), adapter_factory=lambda *args: provider)
    try:
        packet = hook.reset('ep', sensor_spec(), np.zeros((8, 8, 3), np.uint8), np.ones((8, 8), np.float32), 1)
        assert packet.pose_provider == 'simulator_ground_truth'
        assert provider.get_status()['frames'] == 1
        assert hook.native_initialization_attempts == 0
    finally:
        hook.close()
