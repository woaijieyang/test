"""Pose-only traversal regression; no simulator truth beyond position/rotation."""
import copy
import numpy as np
import pytest
from SimulatorAdapter import SimulatorAdapter
from graphAdapter.interfaces.pose import PoseReader
from graphAdapter.interfaces.pose.odometry import continuous_odometry_chart
from graphAdapter.observation_pose.provider_contract import simulator_pose_record
from graphAdapter.map_memory.service import execution_relation
from SimulatorAdapter.tests.test_pose import PoseOnly


def captures():
    sim = PoseOnly()
    adapter = SimulatorAdapter(sim, rotation_matrix=lambda value: value)
    adapter.reset_episode('ep')
    reader = PoseReader(adapter, source='simulator_ground_truth')
    result = []
    mount = np.eye(4)
    for seq, distance in [(1, 0.), (2, .25)]:
        sim.position = np.array([0., 0., -distance])
        frame = reader.capture(episode_id='ep', frame_id=f'ep:f{seq}', timestamp_ns=seq)
        result.append(dict(episode_uid='ep', frame_uid=frame.frame_id, capture_seq=seq,
            pose_record=simulator_pose_record(frame, mount), T_base_camera=mount.tolist(),
            action=dict(action_id=1, collision=False, terminal=False)))
    adapter.shutdown()
    return result


def test_forward_is_recorded_without_native_diagnostics():
    a, b = captures()
    before = copy.deepcopy([a, b])
    assert 'diagnostics' not in a['pose_record']
    result = execution_relation(a, b)
    edge = result['traversed']
    assert edge and edge['src'] == a['frame_uid'] and edge['dst'] == b['frame_uid']
    assert edge['estimated_translation_m'] == pytest.approx(.25)
    assert edge['odom_epoch'] == a['pose_record']['episode_instance']
    assert edge['direction'] == 'recorded_only' and edge['current_passability'] == 'unknown'
    assert edge['straight_shortcut'] is False and [a, b] == before


@pytest.mark.parametrize('kind', ['turn', 'collision', 'missing_collision', 'reset', 'missing_session', 'no_motion', 'teleport'])
def test_no_fabricated_traversal(kind):
    a, b = captures()
    if kind == 'turn': b['action']['action_id'] = 2
    elif kind == 'collision': b['action']['collision'] = True
    elif kind == 'missing_collision': b['action']['collision'] = None
    elif kind == 'reset': b['pose_record']['episode_instance'] = 'another-session'
    elif kind == 'missing_session':
        # Invalid identity must fail the strict shared DTO rather than silently accept.
        b['pose_record']['episode_instance'] = ''
        with pytest.raises(ValueError): execution_relation(a, b)
        return
    else:
        distance = 0. if kind == 'no_motion' else 2.
        b['pose_record']['T_map_base'][0][3] = distance
        b['pose_record']['T_odom_base'][0][3] = distance
        b['pose_record']['T_map_camera_cv'][0][3] = distance
    result = execution_relation(a, b)
    assert result['temporal']['type'] == 'temporal_next' and result['traversed'] is None


def test_provider_change_and_unknown_chart_rejected():
    a, b = captures()
    changed = copy.deepcopy(b['pose_record']); changed['source'] = 'cuvslam_rtabmap_rgbd'
    assert continuous_odometry_chart(a['pose_record'], changed)[1] == 'pose_provider_changed'
    changed = copy.deepcopy(b['pose_record']); changed['map_version'] = 1
    assert continuous_odometry_chart(a['pose_record'], changed)[1] == 'odom_chart_unknown_or_changed'
