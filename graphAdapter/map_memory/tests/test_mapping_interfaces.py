"""Public CLI regressions for the continuous mapping configuration boundary."""
import copy,json
from pathlib import Path
import pytest
from graphAdapter.observation_pose.production import verify_pose_configuration,verify_package
from poseAdapter.interfaces.mapping import mapping_contract_identity,require_mapping_contract
ROOT=Path(__file__).resolve().parents[4]


def test_public_continuous_profile_matches_pose_release_and_package_closure():
    profile=json.loads((ROOT/'src/graphAdapter/map_memory/profiles/000_geometry_shadow.json').read_text())
    assert verify_pose_configuration(profile)['sampling']=='release4_12'
    package=verify_package(profile['pose_package'])
    assert package['python_files']==49
    identity=mapping_contract_identity()
    expected={entry['relative']:entry['sha256'] for entry in profile['pose_package']['files']}
    assert all(expected['poseAdapter/'+name]==sha for name,sha in identity['files'].items())
    require_mapping_contract(identity,copy.deepcopy(identity))
    bad=copy.deepcopy(identity);bad['files']['interfaces/mapping/channel.py']='0'*64
    with pytest.raises(RuntimeError,match='differs'):require_mapping_contract(identity,bad)


def test_public_continuous_profile_cannot_silently_fall_back_to_single_sample():
    profile=json.loads((ROOT/'src/graphAdapter/map_memory/profiles/000_geometry_shadow.json').read_text())
    profile.pop('pose_sampling')
    with pytest.raises(RuntimeError,match='configuration differs'):verify_pose_configuration(profile)
