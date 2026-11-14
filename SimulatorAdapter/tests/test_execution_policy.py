"""User-selected simulator pose policy across stages and actual async Hook entry."""
import json
import numpy as np
import pytest
from SimulatorAdapter.host_bridge import profile_identity
from graphAdapter.map_memory.worker import validate_mapping_profile
from graphAdapter.observation_pose.aware_hook import AwarePoseHook
from graphAdapter.observation_pose.tests.fixtures import sensor_spec
from SimulatorAdapter import SimulatorAdapter
from SimulatorAdapter.tests.test_pose import PoseOnly
from SimulatorAdapter.tests.test_simulator_hook import profile
from SimulatorAdapter.tests.test_async_mapping import Backend

@pytest.mark.parametrize('stage',['000','001','002','003','004','005','006'])
def test_explicit_pose_only_simulator_profile_supports_all_planned_stages(stage):
    p=profile();p['stage']=stage
    assert len(profile_identity(p))==64


def test_provider_pose_async_is_independent_of_native_correction():
    p=dict(stage='002',pose_provider='simulator_ground_truth',simulator_pose_diagnostic=True,
           pose_input_mode='provider_pose',async_admission=True,execution_mode='live')
    assert validate_mapping_profile(p)=='provider_pose'
    with pytest.raises(ValueError,match='correction'):
        validate_mapping_profile(dict(p,background_correction={'enabled':True}))


def test_actual_hook_admits_gt_pose_without_waiting_for_native_interfaces(tmp_path,monkeypatch):
    import graphAdapter.map_memory.worker as worker
    sim=PoseOnly();backend=Backend();backend.session=tmp_path/'memory-session'
    p=profile();p['stage']='002'
    p['map_memory']=dict(enabled=True,stage='002',pose_provider='simulator_ground_truth',
        simulator_pose_diagnostic=True,pose_input_mode='provider_pose',async_admission=True,
        max_episode_observations=501,admission_capacity=2,decision_max_capture_lag=1,frame_timeout_seconds=3)
    backend.profile=p['map_memory']
    monkeypatch.setattr(worker,'MemoryWorkerClient',lambda *args:backend)
    hook=AwarePoseHook(tmp_path/'observations',p,adapter_factory=lambda *args:SimulatorAdapter(sim,rotation_matrix=lambda x:x))
    rgb=np.zeros((8,8,3),np.uint8);depth=np.ones((8,8),np.float32)
    try:
        hook.reset('ep',sensor_spec(),rgb,depth,1)
        hook.begin_macro(1,1);sim.position=np.array([0.,0.,-.25])
        hook.capture(rgb,depth,2,action_id=1,collision=False)
        hook.decision();hook.end_episode([])
        assert hook.native_initialization_attempts==0
        assert hook.memory_packet_count==hook.packet_count==2
        events=[json.loads(line)for line in (hook.coordinator.root/'flow_trace.jsonl').read_text().splitlines()]
        visible=[e for e in events if e['kind']=='MemoryVisibility']
        assert visible and visible[-1]['capture_lag']<=1
        assert not any(e['kind']=='MapCorrectionPublished' for e in events)
    finally:hook.close()


def test_pose_rpc_reuses_only_unchanged_validated_profile(tmp_path,monkeypatch):
    import os
    from types import SimpleNamespace
    import quaternion
    import SimulatorAdapter.host_bridge as bridge
    from case1_runtime.episode_scope import episode_scope
    monkeypatch.setenv("CASE2_DATASET_KEY","r2r")
    monkeypatch.setenv("CASE2_RUN_UID","fixture")
    path=tmp_path/'profile.json'
    p=profile()
    path.write_text(json.dumps(p))
    monkeypatch.setenv("CASE2_HOOK_MODE","on")
    monkeypatch.setenv("CASE2_POSE_PROFILE",str(path))
    ep=SimpleNamespace(scene_id="scene/test.glb",episode_id="member",instruction=SimpleNamespace(instruction_id=1))
    uid=episode_scope(ep)['episode_uid']
    state=SimpleNamespace(position=np.zeros(3),rotation=np.quaternion(1,0,0,0))
    reads=[]
    def get_state(agent):
        reads.append(agent)
        return state
    env=SimpleNamespace(_env=SimpleNamespace(current_episode=ep,sim=SimpleNamespace(get_agent_state=get_state)))
    original=bridge.profile_identity
    expected=original(p)
    checks=[]
    def counted(obj):
        checks.append(obj)
        return original(obj)
    monkeypatch.setattr(bridge,'profile_identity',counted)
    token=None
    def read(digest=expected,episode=uid):
        nonlocal token
        row=bridge.read_pose_state(env,expected_episode_uid=episode,profile_sha256=digest,pose_session=token)
        token=row.get('pose_session',token)
        return row
    first=read()
    state.position[0]=1
    np.testing.assert_array_equal(first['T_episode_base'],np.eye(4))
    np.testing.assert_allclose(np.asarray(read()['T_episode_base'])[:3,3],[0,-1,0],atol=1e-12)
    with pytest.raises(PermissionError):
        read('wrong-digest')
    with pytest.raises(ValueError,match='episode'):
        read(episode='wrong-episode')
    assert len(checks)==1 and reads==[0,0]
    # Same length, timestamp restored, same inode. ctime still reflects the real write.
    prev=path.stat()
    changed=dict(p,stage='002' if p['stage']!='002' else '001')
    path.write_text(json.dumps(changed))
    os.utime(path,ns=(prev.st_atime_ns,prev.st_mtime_ns))
    with pytest.raises(PermissionError):
        read()
    read(original(changed))
    assert len(checks)==2 and len(reads)==3
    replacement=tmp_path/'replacement'
    replacement.write_text(json.dumps(dict(changed,pose_provider='unauthorized')))
    os.replace(replacement,path)
    with pytest.raises(PermissionError):
        read(original(changed))
    path.unlink()
    with pytest.raises(FileNotFoundError):
        read()
    assert len(reads)==3

def test_unrequested_and_expired_history_return_native_while_mapping_continues(tmp_path,monkeypatch):
    import time
    from PIL import Image
    import graphAdapter.map_memory.worker as worker
    from graphAdapter.map_memory.retrieval.host_decision import HostInjection
    from graphAdapter.map_memory.retrieval.protocol import sample_native_rgb
    sim=PoseOnly();backend=Backend();backend.session=tmp_path/'memory-session'
    settings=profile();settings['stage']='002'
    settings['map_memory']=dict(enabled=True,stage='002',pose_provider='simulator_ground_truth',
        simulator_pose_diagnostic=True,pose_input_mode='provider_pose',async_admission=True,
        max_episode_observations=501,admission_capacity=2,decision_max_capture_lag=0,
        execution_mode='live',frame_timeout_seconds=3,
        retrieval=dict(enabled=True,evidence_policy='historical_approach',mode='facts_only',read_timeout_seconds=.05))
    backend.profile=settings['map_memory']
    monkeypatch.setattr(worker,'MemoryWorkerClient',lambda *args:backend)
    hook=AwarePoseHook(tmp_path/'archive',settings,adapter_factory=lambda *args:SimulatorAdapter(sim,rotation_matrix=lambda x:x))
    rgb=np.full((8,8,3),11,np.uint8);depth=np.ones((8,8),np.float32)
    images=[Image.fromarray(rgb)]
    def decide(reason,event):
        started=time.monotonic()
        inp=HostInjection.begin(hook,instruction='Exit the bedroom.',reasoning=reason,reasoning_event=event,
                                host_images=images,budget=8,sampler=sample_native_rgb)
        assert time.monotonic()-started<1
        assert inp.decision.history is None and len(inp.images)==8
        assert np.array_equal(np.asarray(inp.images[-1]),np.asarray(images[-1]))
        assert inp.compile('native text',str,None,None,None)=='native text'
        return inp
    try:
        hook.reset('ep',sensor_spec(),rgb,depth,1)
        hook.memory_stream.await_visible(1,max_capture_lag=0)
        backend.gate.clear();hook.begin_macro(1,1);rgb2=rgb+7;images.append(Image.fromarray(rgb2))
        hook.capture(rgb2,depth,2,action_id=1,collision=False)
        first=decide(None,None)
        assert first.decision.fallback=='no_explicit_return_need'
        reason='The next plan is to exit the bedroom.'
        event=first.record_reasoning(first.decision.event['decision_id'],reason)
        assert decide(reason,event).decision.fallback=='visibility_deadline'
        assert hook.memory_stream.last_publication['cutoff']['capture_seq']==1
        backend.gate.set();hook.end_episode([])
        events=[json.loads(l) for l in (hook.coordinator.root/'flow_trace.jsonl').read_text().splitlines()]
        visible=[v for v in events if v['kind']=='MemoryVisibility']
        assert [v['poll_only'] for v in visible]==[True,False]
        assert all(v['capture_lag']==1 and not v['fresh_enough'] for v in visible)
        assert not any(v['kind']=='MemoryReadRequested' for v in events)
        assert [v['capture_seq']for v in events if v['kind']=='PublishedSnapshot']==[1,2]
    finally:backend.gate.set();hook.close()


def test_final_running_read_timeout_emitted_before_terminal(tmp_path,monkeypatch):
    from threading import Event
    from PIL import Image
    import graphAdapter.map_memory.worker as worker
    from graphAdapter.map_memory.retrieval.host_decision import HostInjection
    from graphAdapter.map_memory.retrieval.protocol import sample_native_rgb
    entered=Event();release=Event()
    class SlowRead(Backend):
        def read_memory(self,req):
            entered.set()
            assert release.wait(3)
            query=req['query']
            return dict(request_id=req['request_id'],episode_uid=query['episode_uid'],
                episode_instance=req['episode_instance'],snapshot_id=query['snapshot_id'],mode=req['mode'],read_only=True,
                decision_id=query['decision_id'],decision_event_seq=query['decision_event_seq'],
                current_frame_uid=query['current_frame_uid'],current_capture_seq=query['current_capture_seq'])
    sim=PoseOnly();backend=SlowRead();backend.session=tmp_path/'session'
    settings=profile();settings['stage']='002'
    settings['map_memory']=dict(enabled=True,stage='002',pose_provider='simulator_ground_truth',
        simulator_pose_diagnostic=True,pose_input_mode='provider_pose',async_admission=True,max_episode_observations=501,
        admission_capacity=2,execution_mode='live',frame_timeout_seconds=3,
        retrieval=dict(enabled=True,evidence_policy='evo_topology',mode='native_plus_attachment',read_timeout_seconds=.15))
    backend.profile=settings['map_memory'];monkeypatch.setattr(worker,'MemoryWorkerClient',lambda *args:backend)
    hook=AwarePoseHook(tmp_path/'archive',settings,adapter_factory=lambda *args:SimulatorAdapter(sim,rotation_matrix=lambda x:x))
    rgb=np.zeros((8,8,3),np.uint8)
    try:
        hook.reset('ep',sensor_spec(),rgb,np.ones((8,8),np.float32),1)
        hook.memory_stream.await_visible(1,max_capture_lag=0)
        api=HostInjection.begin(hook,instruction='Move forward',reasoning=None,reasoning_event=None,
                                host_images=[Image.fromarray(rgb)],budget=8,sampler=sample_native_rgb)
        assert entered.is_set() and api.decision.history is None and api.compile('native',str,None,None,None)=='native'
        release.set();hook.end_episode([])
        log=list(map(json.loads,(hook.coordinator.root/'flow_trace.jsonl').read_text().splitlines()))
        req,=[e for e in log if e['kind']=='MemoryReadRequested'];end,=[e for e in log if e['kind']=='MemoryExpiredReadFinished']
        timed,=[e for e in log if e['kind']=='MemoryReadTiming']
        assert timed['expired_read'] and end['outcome']=='late_reply' and end['terminal_ns']>=timed['observed_ns']
        assert end['request_id']==req['request_id'] and end['decision_id']==req['decision_id'] and end['event_seq']<log[-1]['event_seq']
        assert log[-1]['kind']=='terminal' and not any(e['kind']=='EvoTopologyCompiled' for e in log)
    finally:release.set();hook.close()
