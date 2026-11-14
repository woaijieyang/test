import json
import pytest
import numpy as np

def test_reset_with_recycled_episode_rejects_old_vector_session(tmp_path,monkeypatch):
    from types import SimpleNamespace as NS
    import habitat
    import quaternion
    from case1_runtime.episode_scope import episode_scope
    from SimulatorAdapter.host_bridge import make_vector_factory
    from graphAdapter.interfaces.pose import PoseSessionChanged
    from vlnce_baselines.common.environments import VLNCEDaggerEnv

    cfg=dict(stage='002',pose_provider='simulator_ground_truth',simulator_pose_diagnostic=True)
    path=tmp_path/'profile.json'
    path.write_text(json.dumps(cfg))
    monkeypatch.setenv('CASE2_HOOK_MODE','on')
    monkeypatch.setenv('CASE2_POSE_PROFILE',str(path))
    monkeypatch.setenv('CASE2_DATASET_KEY','r2r')
    monkeypatch.setenv('CASE2_RUN_UID','fixture')
    entry=NS(scene_id='fixture/test.glb',episode_id='member',instruction=NS(instruction_id=1))
    uid=episode_scope(entry)['episode_uid']
    reads=[]
    race=[False]
    def read(agent_id):
        reads.append(agent_id)
        if race[0]:
            race[0]=False
            env.reset()
        return NS(position=[0,0,0],rotation=np.quaternion(1,0,0,0))
    monkeypatch.setattr(habitat.RLEnv,'reset',lambda self: sentinel)
    sentinel=object()
    env=object.__new__(VLNCEDaggerEnv)
    env._env=NS(current_episode=entry,sim=NS(get_agent_state=read))
    assert env.reset() is sentinel and not hasattr(env,'_graph_pose_generation')
    class Vector:
        def call_at(self,index,method,args):
            return getattr(env,method)(**args)
    factory=make_vector_factory(Vector(),cfg)
    first=factory(None,None)
    second=factory(None,None)
    race[0]=True
    with pytest.raises(PoseSessionChanged):
        first.reset_episode(uid)
    first.reset_episode(uid)
    first.push_observation(frame_id=uid+':f000001',timestamp_ns=1)
    assert env.reset() is sentinel and env._env.current_episode is entry
    before=len(reads)
    with pytest.raises(PoseSessionChanged):
        first.push_observation(frame_id=uid+':f000002',timestamp_ns=2)
    assert len(reads)==before and first.get_status()['frames']==1
    second.reset_episode(uid)
    with pytest.raises(PoseSessionChanged):
        first.push_observation(frame_id=uid+':f000002',timestamp_ns=2)
    assert len(reads)==before+1
    second.push_observation(frame_id=uid+':f000001',timestamp_ns=1)
    assert second.get_status()['frames']==1
