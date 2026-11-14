"""Shared pose-only boundary. Provider implementations and simulator handles stay outside DTOs."""
from dataclasses import dataclass
from typing import Protocol,runtime_checkable
import numpy as np
from poseAdapter.coordinate.transforms import checked_transform

SOURCES=frozenset(('cuvslam_rtabmap_rgbd','simulator_ground_truth'))
class PoseSessionChanged(ValueError):
    """A read or capture no longer belongs to its bound provider session."""


@runtime_checkable
class PoseProvider(Protocol):
    def reset_episode(self,episode_id,*,calibration=None,depth_spec=None):...
    def push_observation(self,*,frame_id,timestamp_ns,rgb=None,depth=None,action=None,collided=False):...
    def get_frame_snapshot(self,frame_id,*,timestamp_ns=None,episode_id=None):...
    def get_mapping_session_identity(self):...
    def shutdown(self):...

@dataclass(frozen=True)
class PoseFrame:
    source:str
    episode_id:str
    episode_instance:str
    frame_id:str
    timestamp_ns:int
    map_version:int
    valid:bool
    T_map_base:object
    T_odom_base:object
    T_map_odom:object
    schema_version:int=1
    def __post_init__(self):
        if self.source not in SOURCES or type(self.schema_version)is not int or self.schema_version!=1:raise ValueError('Unsupported pose source/schema')
        if any(not isinstance(x,str) or not x for x in (self.episode_id,self.episode_instance,self.frame_id)):raise ValueError('Pose identities required')
        if not self.frame_id.startswith(self.episode_id+':'):raise ValueError('Pose frame is outside episode')
        if any(type(x)is not int or x<0 for x in (self.timestamp_ns,self.map_version)):raise ValueError('Invalid pose timestamp/version')
        if type(self.valid)is not bool:raise ValueError('Explicit validity required')
        for key in ('T_map_base','T_odom_base','T_map_odom'):
            value=getattr(self,key)
            if self.valid:object.__setattr__(self,key,tuple(map(tuple,checked_transform(value))))
            elif value is not None:raise ValueError('Unavailable pose cannot carry geometry')
    def to_record(self):
        return dict(schema_version=1,source=self.source,episode_id=self.episode_id,episode_instance=self.episode_instance,
            frame_id=self.frame_id,timestamp_ns=self.timestamp_ns,map_version=self.map_version,valid=self.valid,
            **{k:None if getattr(self,k) is None else [list(row) for row in getattr(self,k)] for k in ('T_map_base','T_odom_base','T_map_odom')})
    @classmethod
    def from_record(cls,record):return cls(**record)

class PoseReader:
    """Same caller API for both providers, with explicit source and session checks."""
    def __init__(self,provider,*,source):
        if source not in SOURCES:raise ValueError('Explicit pose source selection required')
        if not isinstance(provider,PoseProvider):raise TypeError('Provider does not implement the shared pose protocol')
        self._provider=provider;self.source=source
        self._frame_snapshot = (getattr(provider, "get_pose_only_snapshot", provider.get_frame_snapshot)
                                if source == "simulator_ground_truth" else provider.get_frame_snapshot)
    def _session(self, episode_id, expected_instance):
        try:
            session=self._provider.get_mapping_session_identity()
        except RuntimeError as error:
            if expected_instance is None:raise
            raise PoseSessionChanged('Bound pose session is no longer active') from error
        if session.episode_id!=episode_id or (expected_instance is not None and session.episode_instance!=expected_instance):
            raise PoseSessionChanged('Pose session differs from bound observation')
        return session

    def capture(self,*,episode_id,frame_id,timestamp_ns,expected_instance=None,**inputs):
        # Endpoint simulator poses depend only on their bound frame and clock.
        if self.source == 'simulator_ground_truth':
            inputs = {}
        before=self._session(episode_id,expected_instance)
        guarded=getattr(self._provider,'push_observation_if_current',None) if self.source=='simulator_ground_truth' else None
        if guarded is None:
            self._provider.push_observation(frame_id=frame_id,timestamp_ns=timestamp_ns,**inputs)
        else:
            try:
                guarded(before,frame_id=frame_id,timestamp_ns=timestamp_ns,**inputs)
            except (ValueError,RuntimeError,KeyError):
                self._session(episode_id,before.episode_instance)
                raise
        return self.read(episode_id=episode_id,frame_id=frame_id,timestamp_ns=timestamp_ns,expected_instance=before.episode_instance)

    def read(self,*,episode_id,frame_id,timestamp_ns,expected_instance=None):
        if type(timestamp_ns)is not int or timestamp_ns<0:raise ValueError('Invalid pose timestamp')
        before=self._session(episode_id,expected_instance)
        try:
            estimate,bindings=self._frame_snapshot(frame_id,timestamp_ns=timestamp_ns,episode_id=episode_id)
        finally:
            self._session(episode_id,before.episode_instance)
        row=estimate.to_record()
        if (row.get('episode_id'),row.get('frame_id'),row.get('timestamp_ns'))!=(episode_id,frame_id,timestamp_ns):raise ValueError('Pose source identity differs')
        if row.get('source')!=self.source:raise ValueError('Pose provider source differs from selected backend')
        if type(row.get('timestamp_ns'))is not int or type(row.get('valid'))is not bool:
            raise ValueError('Provider returned malformed timestamp or validity')
        valid=row['valid']
        if valid:
            if row.get('tracking_state')!='tracking':raise ValueError('Valid pose has inconsistent state')
            if bindings is None or bindings.get('episode_id')!=episode_id or bindings.get('map_version')!=row['map_version']:
                raise ValueError('Pose and bindings are not one snapshot')
            if self.source=='simulator_ground_truth':
                if bindings.get('pose_source')!=self.source or row['map_version']!=0:raise ValueError('Simulator source/version differs')
                if not np.array_equal(row['T_map_base'],row['T_odom_base']) or not np.array_equal(bindings['T_map_odom'],np.eye(4)):
                    raise ValueError('Simulator provider changed the episode coordinate frame')
            else:
                support=row.get('diagnostics',{}).get('measurement_support',{})
                if support.get('kind')!=2 or type(support.get('used'))is not int or support['used']<=0 or support.get('prediction_used')is not False:
                    raise ValueError('Native provider lacks measured support')
        return PoseFrame(self.source,episode_id,before.episode_instance,frame_id,timestamp_ns,row.get('map_version',0),valid,
            row['T_map_base'] if valid else None,row['T_odom_base'] if valid else None,bindings['T_map_odom'] if valid else None)
