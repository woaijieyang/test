import copy,json
from pathlib import Path
import pytest
from graphAdapter.observation_pose.production import verify_pose_configuration,verify_package


def profile():
    return json.loads((Path(__file__).parents[3]/'src/graphAdapter/map_memory/profiles/000_geometry_shadow.json').read_text())


def test_restored_effective_pose_and_independent_package_are_pinned():
    value=profile();assert verify_pose_configuration(value)['logical_rate_hz']==120
    result=verify_package(value['pose_package'])
    assert result['python_files']==49
    assert value['storage_lifecycle']=={'retain_source_pixel_map':False,'subframe_debug_arrays':False}
    assert value['map_memory']['resources']['parallel_geometry_scene'] is False
    assert value['memory_injection'] is False


@pytest.mark.parametrize('change',['sampling','clock','registration','proximity','estimation','wait'])
def test_stale_or_mixed_pose_config_is_rejected_before_output_or_worker(tmp_path,change):
    from graphAdapter.observation_pose.aware_hook import AwarePoseHook
    value=profile()
    if change=='sampling':value.pop('pose_sampling')
    elif change=='clock':value['sensor_clock']['rate_hz']=60
    elif change=='registration':value['pose_options']['rtab_registration_profile']='rgbd_icp_reference_v2'
    elif change=='proximity':value['pose_options']['rtab_proximity_by_space']=True
    elif change=='estimation':value['pose_options']['rtab_visual_estimation_type']=1
    else:value['pose_options']['frame_wait_seconds']=60.
    target=tmp_path/'must-not-create'
    with pytest.raises(RuntimeError,match='configuration differs'):
        AwarePoseHook(target,value)
    assert not target.exists()
