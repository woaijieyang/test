"""Continuous odometry identity; no provider APIs or simulator access."""
import numpy as np
from poseAdapter.coordinate.transforms import checked_transform


def continuous_odometry_chart(previous, current):
    """Return a chart identity or a reason to withhold traversal evidence.

    Callers validate the measured pose records before calling. Native charts
    retain the original verified epoch and odometry-link requirements. Exact
    pose providers use their explicit episode session, never fabricated native
    SLAM diagnostics, map coordinates, or scene navigability.
    """
    source = previous.get('source')
    if source != current.get('source'):
        return None, 'pose_provider_changed'
    if previous.get('episode_id') != current.get('episode_id') or not previous.get('episode_id'):
        return None, 'odom_episode_changed'
    if source == 'simulator_ground_truth':
        instance = previous.get('episode_instance')
        if not isinstance(instance, str) or not instance or instance != current.get('episode_instance'):
            return None, 'odom_session_unknown_or_changed'
        if previous.get('map_version') != 0 or current.get('map_version') != 0:
            return None, 'odom_chart_unknown_or_changed'
        return instance, None
    if source != 'cuvslam_rtabmap_rgbd':
        return None, 'unsupported_pose_provider'
    a = (previous.get('diagnostics') or {}).get('global_frame_link') or {}
    b = (current.get('diagnostics') or {}).get('global_frame_link') or {}
    if a.get('verified') is not True or b.get('verified') is not True or a.get('epoch') is None or a.get('epoch') != b.get('epoch'):
        return None, 'odom_chart_unknown_or_changed'
    link_a = (previous.get('diagnostics') or {}).get('odometry_frame_link')
    link_b = (current.get('diagnostics') or {}).get('odometry_frame_link')
    if link_a is None or link_b is None or not np.array_equal(checked_transform(link_a), checked_transform(link_b)):
        return None, 'native_odometry_link_unknown_or_changed'
    return a['epoch'], None
