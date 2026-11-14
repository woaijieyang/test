"""Explicit pose-provider wire boundary; never imports a simulator implementation."""
from dataclasses import fields
from graphAdapter.interfaces.pose import PoseFrame
from poseAdapter.coordinate.transforms import checked_transform
import numpy as np

SIMULATOR_SOURCE='simulator_ground_truth'
FRAME_FIELDS=frozenset(f.name for f in fields(PoseFrame))
DERIVED_FIELDS=frozenset(('geometry_status','tracking_state','T_map_camera_cv','spatial_bindings'))

def simulator_pose_record(frame,T_base_camera):
    if not isinstance(frame,PoseFrame) or frame.source!=SIMULATOR_SOURCE:raise ValueError('Explicit simulator pose DTO required')
    mount=checked_transform(T_base_camera) if frame.valid else None
    row=frame.to_record();row.update(geometry_status='available' if frame.valid else 'unavailable',
        tracking_state='tracking' if frame.valid else 'unavailable',
        T_map_camera_cv=(np.asarray(frame.T_map_base)@mount).tolist() if frame.valid else None,
        spatial_bindings=dict(episode_id=frame.episode_id,map_version=0,pose_source=SIMULATOR_SOURCE))
    validate_simulator_pose_record(row,T_base_camera)
    return row

def validate_simulator_pose_record(row,T_base_camera=None):
    if set(row)!=FRAME_FIELDS|DERIVED_FIELDS:raise ValueError('Simulator pose record contains missing or unauthorized fields')
    frame=PoseFrame.from_record({key:row[key] for key in FRAME_FIELDS})
    if frame.source!=SIMULATOR_SOURCE or frame.map_version!=0:raise ValueError('Simulator source/version differs')
    expected=dict(episode_id=frame.episode_id,map_version=0,pose_source=SIMULATOR_SOURCE)
    if dict(row['spatial_bindings'])!=expected:raise ValueError('Simulator binding contains unauthorized information')
    if row['geometry_status']!=('available' if frame.valid else 'unavailable'):raise ValueError('Pose validity differs from geometry availability')
    if frame.valid:
        if row['tracking_state']!='tracking' or not np.array_equal(frame.T_map_base,frame.T_odom_base) or not np.array_equal(frame.T_map_odom,np.eye(4)):
            raise ValueError('Simulator pose gauge/state differs')
        camera=checked_transform(row['T_map_camera_cv'])
        if T_base_camera is not None and not np.allclose(camera,np.asarray(frame.T_map_base)@checked_transform(T_base_camera),atol=1e-9,rtol=0):
            raise ValueError('Simulator camera pose differs from calibrated mount')
    elif row['T_map_camera_cv'] is not None or row['tracking_state']!='unavailable':
        raise ValueError('Unavailable simulator pose carries inconsistent state or geometry')
    return frame


def audit_simulator_endpoints(packets,events):
    """Audit pose-only endpoint publications, never reinterpret them as native SLAM samples."""
    from graphAdapter.observation_packet import ObservationPacket,thaw
    outcomes={}
    for event in events:
        kind=event.get('kind')
        if kind=='pose_sample':
            raise ValueError('Simulator pose run contains native subframe samples')
        if kind not in ('pose','geometry_unavailable'):
            continue
        uid=event.get('frame_uid')
        if not isinstance(uid,str) or not uid:
            raise ValueError('Pose outcome lacks a frame identity')
        if uid in outcomes:
            raise ValueError('Duplicate or contradictory simulator pose outcome')
        if kind=='pose' and (event.get('sampling_contract') is not None or event.get('runtime_artifacts') is not None):
            raise ValueError('Simulator pose event claims native artifacts or sampling')
        outcomes[uid]=event
    count=0
    valid=0
    session=None
    previous_stamp=-1
    for sequence,record in enumerate(packets,1):
        packet=ObservationPacket(**record)
        if packet.pose_provider!=SIMULATOR_SOURCE:
            raise ValueError('Mixed pose providers in simulator audit')
        # ObservationPacket checks the DTO, calibrated mount, frame and acquisition clock.
        row=packet.pose_record
        current_session=(packet.episode_uid,row['episode_instance'])
        if session is None:
            session=current_session
        if session!=current_session or packet.capture_seq!=sequence or packet.sensor_timestamp_ns<=previous_stamp:
            raise ValueError('Simulator endpoint session, sequence or acquisition clock differs')
        event=outcomes.pop(packet.frame_uid,None)
        if event is None:
            raise ValueError('Simulator endpoint has no matching pose outcome')
        if event.get('episode_uid',packet.episode_uid)!=packet.episode_uid:
            raise ValueError('Simulator event belongs to a different episode')
        if row['valid']:
            if (event['kind']!='pose' or event.get('canonical') is not True
                    or type(event.get('sensor_sequence')) is not int or event['sensor_sequence']!=sequence):
                raise ValueError('Simulator endpoint has no matching canonical pose event')
            if event.get('pose')!=thaw(row):
                raise ValueError('Simulator pose event and packet differ')
            valid+=1
        elif event['kind']!='geometry_unavailable':
            raise ValueError('Unavailable simulator pose lacks failure evidence')
        previous_stamp=packet.sensor_timestamp_ns
        count=sequence
    if outcomes or not count:
        raise ValueError('Unbound simulator pose outcomes or empty observation stream')
    return dict(mode='simulator_endpoint_pose',status='VERIFIED',host_endpoints=count,
                valid_pose_endpoints=valid,extra_pose_views=0,native_slam_used=False)
