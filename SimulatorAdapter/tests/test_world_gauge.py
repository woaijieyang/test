"""World gauge must disappear before the VectorEnv reply is serialized."""
from types import SimpleNamespace as NS
import json
import numpy as np
import pytest
import quaternion
from case1_runtime.episode_scope import episode_scope
from SimulatorAdapter.host_bridge import make_vector_factory,pose_rpc_reply
from graphAdapter.interfaces.pose import PoseReader,PoseSessionChanged
from SimulatorAdapter.tests.test_simulator_hook import profile

def test_world_rigid_motion_cancels_at_wire_and_public_boundaries(tmp_path,monkeypatch):
    cfg=profile()
    path=tmp_path/'profile.json';path.write_text(json.dumps(cfg))
    monkeypatch.setenv('CASE2_HOOK_MODE','on')
    monkeypatch.setenv('CASE2_POSE_PROFILE',str(path));monkeypatch.setenv('CASE2_RUN_UID','rigid-frame-test')
    monkeypatch.setenv('CASE2_DATASET_KEY','r2r')
    ep=NS(instruction=NS(instruction_id=1),episode_id='1',scene_id='fixture/scene.glb')
    uid=episode_scope(ep)['episode_uid']
    rot=lambda v:quaternion.as_rotation_matrix(quaternion.from_rotation_vector(v))
    base_axes=np.array([[0.,-1.,0.],[0.,0.,1.],[-1.,0.,0.]])
    poses=[(np.array([4.,-.5,2.]),rot([.17,-.3,.4])),
           (np.array([4.3,.6,1.2]),rot([-.35,.3,.1])),
           (np.array([4.,-.5,2.]),rot([.17,-.3,.4]))]
    for G,t in [(np.eye(3),np.zeros(3)),(rot([.47,-.56,.29]),np.array([-12.,4.,7.]))]:
        responses=[]
        def state(_):
            p,R=poses[0 if not responses else len(responses)-1]
            return NS(position=G@p+t,rotation=quaternion.from_rotation_matrix(G@R))
        env=NS(_env=NS(current_episode=ep,sim=NS(get_agent_state=state)))
        class RPC:
            def call_at(self,index,method,args):
                assert index==0 and method=='graph_pose_state'
                row=pose_rpc_reply(env,**args)
                responses.append(row)
                return json.loads(json.dumps(row))
        provider=make_vector_factory(RPC(),cfg)(None,None)
        try:
            provider.reset_episode(uid)
            reader=PoseReader(provider,source='simulator_ground_truth')
            for i,(p,R) in enumerate(poses):
                frame=reader.capture(episode_id=uid,frame_id=f'{uid}:f{i}',timestamp_ns=i)
                expected=np.eye(4)
                p0,R0=poses[0]
                expected[:3,:3]=base_axes.T@R0.T@R@base_axes
                expected[:3,3]=base_axes.T@R0.T@(p-p0)
                np.testing.assert_allclose(frame.T_map_base,expected,rtol=0,atol=1e-12)
                row=responses[-1]
                assert set(row)=={'episode_uid','T_episode_base'}
                np.testing.assert_allclose(row['T_episode_base'],expected,rtol=0,atol=1e-12)
            assert set(responses[0])=={'episode_uid','T_episode_base','pose_session'}
            np.testing.assert_array_equal(responses[0]['T_episode_base'],np.eye(4))
            assert len(responses)==4
        finally:provider.shutdown()


@pytest.mark.parametrize('payload', [
    {'position':[10,20,30],'rotation_wxyz':[1,0,0,0]},
    {'T_episode_base':np.eye(4).astype(str).tolist()},
    {'T_episode_base':np.eye(4,dtype=bool).tolist()},
    {'T_episode_base':np.diag([-1.,1.,1.,1.]).tolist()},
    {'T_episode_base':np.eye(4).tolist(),'goal':[0,0,0]},
])
def test_vector_reader_rejects_invalid_reply_before_binding_session(payload):
    from SimulatorAdapter.host_bridge import _VectorPoseSource
    src=_VectorPoseSource(NS(call_at=lambda *args:dict(payload,episode_uid='ep',pose_session='a'*32)),0,'profile')
    src.episode='ep'
    with pytest.raises(PoseSessionChanged):src.read_pose()
    assert src.session is None
