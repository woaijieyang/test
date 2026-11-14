"""Pose-only Habitat adapter. Never reads goals, navmesh or semantic annotations."""
from dataclasses import dataclass
import math,threading,uuid
import numpy as np
from poseAdapter.coordinate.transforms import checked_transform
from poseAdapter.interfaces.mapping import MappingSessionIdentity
from poseAdapter.pose_sync import logical_sensor_timestamp as sensor_timestamp

# Habitat local axes: right/up/back. API output: forward/left/up.
HABITAT_FROM_FLU=np.array([[0.,-1.,0.],[0.,0.,1.],[-1.,0.,0.]])
HABITAT_FROM_FLU.setflags(write=False)

class InvalidSimulatorMeasurement(ValueError):
    """The current simulator measurement cannot supply geometry."""


def checked_position(value):
    try:
        position=np.array(value,dtype=np.float64,copy=True)
    except (TypeError,ValueError,OverflowError) as error:
        raise InvalidSimulatorMeasurement('Invalid simulator base position') from error
    if position.shape!=(3,) or not np.isfinite(position).all():
        raise InvalidSimulatorMeasurement('Invalid simulator base position')
    return position


def checked_quaternion(rotation):
    import quaternion
    if not isinstance(rotation,np.quaternion):
        raise InvalidSimulatorMeasurement('Expected one simulator rotation quaternion')
    values=quaternion.as_float_array(rotation)
    # Habitat exposes a unit rotation. hypot avoids overflow and underflow in the norm.
    if not math.isclose(math.hypot(*values),1.0,rel_tol=0.0,abs_tol=1e-5):
        raise InvalidSimulatorMeasurement('Invalid simulator rotation quaternion')
    return values


@dataclass(frozen=True)
class SimulatorPoseEstimate:
    episode_id:str
    frame_id:str
    timestamp_ns:int
    pose_rows:tuple
    anchor_id:int
    map_version:int=0
    source:str='simulator_ground_truth'
    valid:bool=True
    tracking_state:str='tracking'
    @property
    def T_map_base(self):return np.array(self.pose_rows,dtype=np.float64)
    @property
    def T_odom_base(self):return self.T_map_base
    @property
    def diagnostics(self):return dict(pose_provider='SimulatorAdapter',pose_only=True,coordinate_frame='episode_initial_FLU',native_slam_used=False)
    def to_record(self):
        return dict(episode_id=self.episode_id,frame_id=self.frame_id,timestamp_ns=self.timestamp_ns,
            T_map_base=self.T_map_base.tolist(),T_odom_base=self.T_odom_base.tolist(),map_version=0,
            source=self.source,valid=True,tracking_state='tracking',pose_anchor_id=self.anchor_id,
            T_anchor_base=np.eye(4).tolist(),diagnostics=self.diagnostics,
            covariance=None,covariance_source='not_estimated_ground_truth')

def simulator_base_transform(state,rotation_matrix=None):
    position=checked_position(state.position)
    if rotation_matrix is None:
        import quaternion
        measured=state.rotation
        checked_quaternion(measured)
        rotation=quaternion.as_rotation_matrix(measured)
    else:rotation=rotation_matrix(state.rotation)
    rotation=np.asarray(rotation,dtype=np.float64)
    if rotation.shape!=(3,3):raise InvalidSimulatorMeasurement('Expected one simulator rotation matrix')
    matrix=np.eye(4);matrix[:3,:3]=rotation@HABITAT_FROM_FLU;matrix[:3,3]=position
    return checked_transform(matrix)


class SimulatorAdapter:
    """Host-owned pose provider with frame-exact caching and no simulator control."""
    def __init__(self,simulator,*,agent_id=0,rotation_matrix=None,api='habitat_lab'):
        if api=='habitat_lab':
            get_state=simulator.get_agent_state
            read=lambda:simulator_base_transform(get_state(agent_id),rotation_matrix)
        elif api=='habitat_sim':
            get_state=simulator.get_agent(agent_id).get_state
            read=lambda:simulator_base_transform(get_state(),rotation_matrix)
        else:raise ValueError('Explicit supported simulator pose API required')
        self.agent_id=agent_id
        self._init_pose_reader(read)

    def _init_pose_reader(self,read_pose):
        self._read_pose=read_pose
        self._lock=threading.RLock();self.closed=False;self.episode_id=None
        self._origin=None;self._frames={};self._latest=None;self._timestamp=-1
    def reset_episode(self,episode_id,*,calibration=None,depth_spec=None):
        with self._lock:
            if self.closed:raise RuntimeError('SimulatorAdapter is closed')
            if not isinstance(episode_id,str) or not episode_id:raise ValueError('Episode identity required')
            origin=self._read_pose()
            self.episode_id=episode_id;self.episode_instance=uuid.uuid4().hex
            self._origin=np.linalg.inv(origin);self._frames={};self._latest=None;self._timestamp=-1
    @staticmethod
    def logical_sensor_timestamp(sequence,rate_hz=120):
        return sensor_timestamp(sequence,rate_hz)
    def push_observation(self,*,frame_id,timestamp_ns,rgb=None,depth=None,action=None,collided=False):
        with self._lock:
            if self.closed or self.episode_id is None:raise RuntimeError('Active simulator pose session required')
            if not isinstance(frame_id,str) or not frame_id.startswith(self.episode_id+':'):raise ValueError('Wrong frame episode')
            if type(timestamp_ns)is not int or timestamp_ns<0:raise ValueError('Invalid pose timestamp')
            if frame_id in self._frames:
                estimate=self._frames[frame_id]
                if timestamp_ns!=estimate.timestamp_ns:raise ValueError('Conflicting duplicate pose request')
                return estimate
            if timestamp_ns<=self._timestamp:raise ValueError('Unordered pose acquisition')
            pose=checked_transform(self._origin@self._read_pose())
            estimate=SimulatorPoseEstimate(self.episode_id,frame_id,timestamp_ns,tuple(map(tuple,pose)),len(self._frames)+1)
            self._frames[frame_id]=estimate;self._latest=estimate;self._timestamp=timestamp_ns
            return estimate
    def push_observation_if_current(self,session,**observation):
        """Validate the caller's session and insert the frame under one provider lock."""
        with self._lock:
            if self.get_mapping_session_identity()!=session:
                raise ValueError('Pose capture belongs to a different session')
            return self.push_observation(**observation)

    def get_pose(self):
        with self._lock:return self._latest
    def get_pose_for_frame(self,frame_id,*,timestamp_ns=None,episode_id=None):
        with self._lock:
            if self.closed:raise RuntimeError('SimulatorAdapter is closed')
            if episode_id is not None and episode_id!=self.episode_id:raise ValueError('Wrong pose episode')
            if timestamp_ns is not None and (type(timestamp_ns)is not int or timestamp_ns<0):raise ValueError('Invalid pose timestamp')
            estimate=self._frames[frame_id]
            if timestamp_ns is not None and timestamp_ns!=estimate.timestamp_ns:raise ValueError('Wrong pose timestamp')
            return estimate
    def _pose_bindings(self):
        return dict(episode_id=self.episode_id,map_version=0,pose_source='simulator_ground_truth',
                    T_map_odom=np.eye(4).tolist())

    def get_pose_only_snapshot(self,frame_id,*,timestamp_ns=None,episode_id=None):
        """Atomic frame and chart binding for callers that do not consume mapping anchors."""
        with self._lock:
            estimate=self.get_pose_for_frame(frame_id,timestamp_ns=timestamp_ns,episode_id=episode_id)
            return estimate,self._pose_bindings()

    def spatial_bindings(self):
        with self._lock:
            return dict(self._pose_bindings(),pose_anchors={str(p.anchor_id):p.T_map_base.tolist() for p in self._frames.values()})
    def get_frame_snapshot(self,frame_id,*,timestamp_ns=None,episode_id=None):
        with self._lock:return self.get_pose_for_frame(frame_id,timestamp_ns=timestamp_ns,episode_id=episode_id),self.spatial_bindings()
    def get_mapping_session_identity(self):
        with self._lock:
            if self.closed or self.episode_id is None:raise RuntimeError('No active pose session')
            return MappingSessionIdentity(self.episode_id,self.episode_instance)
    def get_status(self):return dict(closed=self.closed,episode_id=self.episode_id,source='simulator_ground_truth',runtime=dict(active=not self.closed),frames=len(self._frames))
    def recovery_status(self):return dict(active=False,reason='simulator_ground_truth')
    def release_audit(self):
        with self._lock:
            return dict(source='simulator_ground_truth',closed=self.closed,buffered_frames=len(self._frames),
                latest_cleared=self._latest is None,origin_cleared=self._origin is None,
                reader_released=self._read_pose is None,episode_cleared=self.episode_id is None,
                simulator_owned=False)
    def shutdown(self):
        with self._lock:
            self.closed=True;self._frames.clear();self._latest=None;self._origin=None
            self._read_pose=None;self.episode_id=None
