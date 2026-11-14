"""Active host and mapping layers must agree before pose RPC admission."""
import json
import pytest
from SimulatorAdapter.host_bridge import profile_identity,pose_rpc_reply
from graphAdapter.interfaces.pose.policy import require_simulator_profile
from graphAdapter.map_memory.worker import validate_mapping_profile


def base():
    return dict(stage='001',pose_provider='simulator_ground_truth',pose_sampling='primitive_endpoints',
                simulator_pose_diagnostic=True,map_memory=dict(enabled=True,stage='001',
                pose_provider='simulator_ground_truth',simulator_pose_diagnostic=True,pose_input_mode='provider_pose'))

@pytest.mark.parametrize('layer,changes',[
    ('outer',{'pose_sampling':'release4_8'}),('outer',{'pose_sampling':None}),
    ('inner',{'pose_sampling':'native_subframes'}),('inner',{'stage':'002'}),
    ('inner',{'pose_provider':'cuvslam_rtabmap_rgbd'}),('inner',{'simulator_pose_diagnostic':False}),
    ('inner',{'pose_input_mode':'continuous'}),('inner',{'background_correction':{'enabled':True}}),
    ('inner',{'enabled':'yes'})])
def test_conflict_refused_at_profile_and_at_environment_before_read(layer,changes,tmp_path,monkeypatch):
    cfg=base();(cfg if layer=='outer' else cfg['map_memory']).update(changes)
    with pytest.raises(ValueError):require_simulator_profile(cfg)
    with pytest.raises(PermissionError):profile_identity(cfg)
    path=tmp_path/'settings.json';path.write_text(json.dumps(cfg))
    monkeypatch.setenv('CASE2_POSE_PROFILE',str(path));monkeypatch.setenv('CASE2_HOOK_MODE','on')
    import hashlib
    raw_digest=hashlib.sha256(json.dumps(cfg,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    class Env:
        @property
        def _env(self):pytest.fail('Conflicting profile reached Habitat')
    assert pose_rpc_reply(Env(),expected_episode_uid='ep',profile_sha256=raw_digest,pose_session=None)==dict(episode_uid='ep',pose_error='profile_rejected')

def test_missing_optional_sampling_is_endpoint_default_and_disabled_child_is_inert():
    cfg=base();cfg.pop('pose_sampling');assert require_simulator_profile(cfg)=='simulator_ground_truth'
    assert validate_mapping_profile(cfg['map_memory'])=='provider_pose'
    cfg['map_memory'].update(enabled=False,stage='other',pose_input_mode='native_corrected')
    assert require_simulator_profile(cfg)=='simulator_ground_truth'

def test_worker_checks_its_own_sampling_contract():
    p=base()['map_memory'];p['pose_sampling']='release4_8'
    with pytest.raises(ValueError):validate_mapping_profile(p)


def test_inactive_native_worker_options_do_not_initialize_native_package(tmp_path,monkeypatch):
    from graphAdapter.observation_pose import production
    from graphAdapter.observation_pose.aware_hook import AwarePoseHook
    from SimulatorAdapter.tests.test_simulator_hook import profile
    cfg=profile()
    cfg['map_memory']=dict(enabled=False,pose_input_mode='continuous',pose_provider='cuvslam_rtabmap_rgbd')
    def unexpected(*args,**kwargs):pytest.fail('Inactive component attempted native setup')
    monkeypatch.setattr(production,'verify_pose_configuration',unexpected)
    monkeypatch.setattr(production,'verify_package',unexpected)
    hook=AwarePoseHook(tmp_path/'pose-only',cfg,adapter_factory=unexpected)
    try:assert hook.simulator_pose and hook.memory is None and hook.native_initialization_attempts==0
    finally:hook.close()
