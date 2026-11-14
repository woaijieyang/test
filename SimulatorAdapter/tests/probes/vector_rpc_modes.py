"""Exercise receiver-side denial before any Habitat property can be observed."""
import json
import pytest

@pytest.mark.parametrize('case', ['off_with_profile','unset_with_profile','simulator_endpoint','inconsistent_release4'])
def test_native_sampler_denies_without_reading_or_mutating_simulator(tmp_path, monkeypatch, case):
    from vlnce_baselines.common.environments import VLNCEDaggerEnv
    cfg={'stage':'002','pose_provider':'simulator_ground_truth','simulator_pose_diagnostic':True,
         'pose_sampling':'release4_12' if case=='inconsistent_release4' else 'primitive_endpoints'}
    path=tmp_path/'profile.json';path.write_text(json.dumps(cfg))
    monkeypatch.setenv('CASE2_POSE_PROFILE',str(path))
    if case=='unset_with_profile':monkeypatch.delenv('CASE2_HOOK_MODE',raising=False)
    else:monkeypatch.setenv('CASE2_HOOK_MODE','off' if case=='off_with_profile' else 'on')
    class Trap:
        @property
        def _env(self):pytest.fail('Receiver accessed environment before checking pose source')
    reply=VLNCEDaggerEnv.graph_pose_subframes(Trap(),1,12)
    assert reply==dict(sampling_error='native_subframes_disabled')

@pytest.mark.parametrize('mode',['off',None])
def test_stale_simulator_profile_does_not_authorize_pose_rpc(monkeypatch,tmp_path,mode):
    from SimulatorAdapter.host_bridge import pose_rpc_reply,profile_identity
    cfg={'stage':'002','pose_provider':'simulator_ground_truth','simulator_pose_diagnostic':True}
    path=tmp_path/'profile.json';path.write_text(json.dumps(cfg))
    monkeypatch.setenv('CASE2_POSE_PROFILE',str(path))
    if mode is None:monkeypatch.delenv('CASE2_HOOK_MODE',raising=False)
    else:monkeypatch.setenv('CASE2_HOOK_MODE',mode)
    class Trap:
        @property
        def _env(self):pytest.fail('Disabled pose RPC entered Habitat')
    assert pose_rpc_reply(Trap(),expected_episode_uid='ep',profile_sha256=profile_identity(cfg),
                          pose_session=None)==dict(episode_uid='ep',pose_error='profile_rejected')


def test_off_dispatch_does_not_import_optional_adapters_or_read_scene(monkeypatch,tmp_path):
    import builtins
    from habitat.core.vector_env import VectorEnv,CALL_COMMAND,CLOSE_COMMAND
    from vlnce_baselines.common.environments import VLNCEDaggerEnv
    monkeypatch.setenv('CASE2_HOOK_MODE','off')
    monkeypatch.setenv('CASE2_POSE_PROFILE',str(tmp_path/'stale.json'))
    class EmptyScene:
        graph_pose_state=VLNCEDaggerEnv.graph_pose_state
        graph_pose_subframes=VLNCEDaggerEnv.graph_pose_subframes
        graph_raw_depth_endpoint=VLNCEDaggerEnv.graph_raw_depth_endpoint
        graph_static_sensor_spec=VLNCEDaggerEnv.graph_static_sensor_spec
        def close(self):pass
        @property
        def _env(self):pytest.fail('Disabled RPC reached scene')
    cmds=[('graph_pose_state',dict(expected_episode_uid='ep',profile_sha256='x',pose_session=None)),
          ('graph_pose_subframes',dict(action_id=1,samples=12)),('graph_raw_depth_endpoint',{}),('graph_static_sensor_spec',{})]
    commands=iter([(CALL_COMMAND,c) for c in cmds]+[(CLOSE_COMMAND,None)])
    imports=builtins.__import__
    def guarded(name,*args,**kwargs):
        if name.split('.')[0] in ('SimulatorAdapter','graphAdapter','poseAdapter'):
            pytest.fail('Hook-off attempted optional import '+name)
        return imports(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',guarded)
    replies=[]
    VectorEnv._worker_env(lambda:next(commands),replies.append,EmptyScene,(),False,False)
    assert replies==[dict(episode_uid='ep',pose_error='profile_rejected'),dict(sampling_error='native_subframes_disabled'),
                     dict(observation_error='hook_disabled'),dict(observation_error='hook_disabled')]


def test_only_explicit_native_sampling_contract_opens_receiver(monkeypatch,tmp_path):
    from case1_runtime.observations import native_subframes_enabled
    from vlnce_baselines.common.environments import VLNCEDaggerEnv
    path=tmp_path/'native.json'
    env={'CASE2_HOOK_MODE':'on','CASE2_POSE_PROFILE':str(path)}
    monkeypatch.setenv('CASE2_HOOK_MODE','on');monkeypatch.setenv('CASE2_POSE_PROFILE',str(path))
    for cfg in ({'pose_sampling':'release4_12'},{'pose_sampling':'release4_12','pose_provider':'cuvslam_rtabmap_rgbd'}):
        path.write_text(json.dumps(cfg));assert native_subframes_enabled(env)
        with pytest.raises(ValueError,match='Fixed release4'):
            VLNCEDaggerEnv.graph_pose_subframes(object(),True,12)
    for text in ('bad','[]','{}','{"pose_sampling":"primitive_endpoints"}',
                 '{"pose_sampling":"release4_12","simulator_pose_diagnostic":true}'):
        path.write_text(text);assert not native_subframes_enabled(env)


@pytest.mark.parametrize('inner',[
    {'pose_provider':'simulator_ground_truth'},{'pose_input_mode':'provider_pose'},{'simulator_pose_diagnostic':True}])
def test_contradictory_native_outer_simulator_inner_cannot_sample(tmp_path,monkeypatch,inner):
    from vlnce_baselines.common.environments import VLNCEDaggerEnv
    cfg=dict(pose_sampling='release4_12',map_memory=dict(inner,enabled=True))
    path=tmp_path/'mix.json';path.write_text(json.dumps(cfg))
    monkeypatch.setenv('CASE2_HOOK_MODE','on');monkeypatch.setenv('CASE2_POSE_PROFILE',str(path))
    assert VLNCEDaggerEnv.graph_pose_subframes(object(),1,12)==dict(sampling_error='native_subframes_disabled')


def test_invalid_pose_config_stops_trainer_before_checkpoint_or_environment(tmp_path,monkeypatch):
    from vlnce_baselines import awarevln_trainer as trainer
    cfg={'stage':'001','pose_provider':'simulator_ground_truth','simulator_pose_diagnostic':True,
         'map_memory':{'enabled':True,'stage':'002','pose_provider':'simulator_ground_truth',
                       'pose_input_mode':'provider_pose','simulator_pose_diagnostic':True}}
    path=tmp_path/'mismatch.json';path.write_text(json.dumps(cfg))
    monkeypatch.setenv('CASE2_HOOK_MODE','on');monkeypatch.setenv('CASE2_POSE_PROFILE',str(path))
    def unexpected(*args,**kwargs):pytest.fail('Startup attempted before rejecting a stage mismatch')
    monkeypatch.setattr(trainer,'load_pretrained_model',unexpected)
    monkeypatch.setattr(trainer,'construct_envs_auto_reset_false',unexpected)
    with pytest.raises(ValueError,match='stages differ'):
        trainer.AwareVLNTrainer._eval_checkpoint(object(),'unused-checkpoint',None)
