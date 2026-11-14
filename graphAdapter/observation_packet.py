"""Validated immutable stage000 observation products and two independent input ports."""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Optional,Tuple,Mapping,Any
import copy,math
import numpy as np

def freeze(value):
    if isinstance(value,Mapping):
        return MappingProxyType({str(k):freeze(v) for k,v in value.items()})
    if isinstance(value,(list,tuple)):
        return tuple(freeze(v) for v in value)
    if isinstance(value,np.ndarray):return freeze(value.tolist())
    if isinstance(value,np.generic):return value.item()
    return value

def thaw(value):
    if isinstance(value,Mapping):return {k:thaw(v) for k,v in value.items()}
    if isinstance(value,tuple):return [thaw(v) for v in value]
    return value

@dataclass(frozen=True)
class ObservationPacket:
    episode_uid:str
    frame_uid:str
    env_step:int
    decision_id:Optional[int]
    event_seq:int
    capture_seq:int
    sensor_timestamp_ns:int
    raw_rgb_ref:Optional[str]
    raw_depth_ref:Optional[str]
    aligned_ref:Optional[str]
    calibration_hash:Optional[str]
    K:Optional[Tuple[Tuple[float,...],...]]
    T_base_camera:Optional[Tuple[Tuple[float,...],...]]
    action:Mapping[str,Any]
    pose_record:Mapping[str,Any]
    capture_monotonic_ns:Optional[int]=None
    failure_reason:Optional[str]=None
    identity:Optional[Mapping[str,Any]]=None
    capture_clock_source:str="endpoint"
    received_monotonic_ns:Optional[int]=None
    pose_provider:str="cuvslam_rtabmap_rgbd"

    def __post_init__(self):
        if not self.episode_uid or not self.frame_uid.startswith(self.episode_uid+":"):
            raise ValueError("Packet episode/frame identity mismatch")
        for name in ("env_step","event_seq","capture_seq","sensor_timestamp_ns"):
            value=getattr(self,name)
            if type(value)is not int or value<0:raise ValueError("Invalid packet counter: "+name)
        if self.event_seq<1 or self.capture_seq<1:raise ValueError("Packet capture/event sequence required")
        if self.decision_id is not None and (type(self.decision_id)is not int or self.decision_id<1):
            raise ValueError("Invalid packet decision")
        for name in ("K","T_base_camera","action","pose_record","identity"):
            object.__setattr__(self,name,freeze(getattr(self,name)))
        pose=self.pose_record
        if self.pose_provider not in ('cuvslam_rtabmap_rgbd','simulator_ground_truth'):raise ValueError('Unknown pose provider')
        if self.pose_provider=='simulator_ground_truth':
            from .observation_pose.provider_contract import validate_simulator_pose_record
            validate_simulator_pose_record(thaw(pose),self.T_base_camera)
        elif pose.get('source')=='simulator_ground_truth':raise ValueError('Simulator pose requires explicit provider selection')
        if (pose.get("episode_id"),pose.get("frame_id"),pose.get("timestamp_ns")) != (
                self.episode_uid,self.frame_uid,self.sensor_timestamp_ns):
            raise ValueError("Packet pose/frame identity mismatch")
        if pose.get("geometry_status") not in ("available","unavailable"):
            raise ValueError("Packet requires explicit geometry availability")
        if self.K is not None:
            k=np.asarray(self.K,float)
            if k.shape!=(3,3) or not np.isfinite(k).all() or min(k[0,0],k[1,1])<=0:
                raise ValueError("Invalid packet intrinsics")
        if self.T_base_camera is not None:
            from poseAdapter.coordinate.transforms import checked_transform
            checked_transform(self.T_base_camera)
        if pose["geometry_status"]=="available":
            from poseAdapter.coordinate.transforms import checked_transform
            if not (self.raw_rgb_ref and self.raw_depth_ref and self.aligned_ref and self.calibration_hash and
                    self.K is not None and self.T_base_camera is not None):
                raise ValueError("Available geometry lacks sensor/calibration provenance")
            if self.pose_provider=='cuvslam_rtabmap_rgbd':
                if pose.get("valid")is not True or pose.get("source")!="cuvslam_rtabmap_rgbd" or pose.get("tracking_state")!="tracking":
                    raise ValueError("Available geometry requires measured combined-backend pose")
                support=(pose.get("diagnostics") or {}).get("measurement_support") or {}
                if support.get("kind")!=2 or type(support.get("used"))is not int or support["used"]<=0 or support.get("prediction_used")is not False:
                    raise ValueError("Packet geometry lacks current measured native constraints")
                bindings=pose.get("spatial_bindings")
                if not isinstance(bindings,Mapping) or (bindings.get("episode_id"),bindings.get("map_version"))!=(
                        self.episode_uid,pose.get("map_version")):
                    raise ValueError("Packet spatial bindings mismatch")
                key=pose.get("rtab_keyframe_id")
                frames=bindings.get("optimized_keyframes",{})
                if type(key)is not int or key<=0 or str(key) not in frames or pose.get("T_keyframe_base") is None:
                    raise ValueError("Packet lacks actual keyframe-relative provenance")
                expected=checked_transform(frames[str(key)])@checked_transform(pose["T_keyframe_base"])
                if not np.allclose(expected,pose["T_map_base"],atol=2e-5,rtol=2e-6):
                    raise ValueError("Packet pose disagrees with spatial keyframe snapshot")
            camera=checked_transform(pose.get("T_map_camera_cv"))
            base=checked_transform(pose.get("T_map_base"))
            if not np.allclose(camera,base@np.asarray(self.T_base_camera),atol=1e-9):
                raise ValueError("Packet camera matrix disagrees with base/mount")
        elif pose.get("T_map_camera_cv") is not None:
            raise ValueError("Unavailable geometry must not carry a camera transform")
        if self.raw_rgb_ref is None and not self.failure_reason:
            raise ValueError("Missing raw RGB needs an explicit failure reason")

    def to_record(self):
        return {name:thaw(getattr(self,name)) for name in self.__dataclass_fields__
                if name!='pose_provider' or self.pose_provider!='cuvslam_rtabmap_rgbd'}

@dataclass(frozen=True)
class GeometryInput:
    frame_key:tuple
    rgb_ref:Optional[str]
    depth_ref:Optional[str]
    K:object
    T_base_camera:object
    pose_map_version:object
    T_map_camera_cv:object
    geometry_status:str
    pose_provider:str="cuvslam_rtabmap_rgbd"

@dataclass(frozen=True)
class PerceptionInput:
    frame_key:tuple
    rgb_ref:Optional[str]
    K:object
    T_base_camera:object
    pose_map_version:object
    T_map_camera_cv:object
    geometry_status:str
    pose_provider:str="cuvslam_rtabmap_rgbd"

def _key(packet):
    if not isinstance(packet,ObservationPacket):raise TypeError("Validated ObservationPacket required")
    return (packet.episode_uid,packet.frame_uid,packet.capture_seq,packet.sensor_timestamp_ns,packet.calibration_hash)

def geometry_input(packet):
    """Stage000 geometry input port; no map integration is performed."""
    return GeometryInput(_key(packet),packet.raw_rgb_ref,packet.aligned_ref,packet.K,packet.T_base_camera,
        packet.pose_record.get("map_version"),packet.pose_record.get("T_map_camera_cv"),packet.pose_record["geometry_status"],packet.pose_provider)

def perception_input(packet):
    """Stage000 perception input port; no perception model is called."""
    return PerceptionInput(_key(packet),packet.raw_rgb_ref,packet.K,packet.T_base_camera,
        packet.pose_record.get("map_version"),packet.pose_record.get("T_map_camera_cv"),packet.pose_record["geometry_status"],packet.pose_provider)

def require_same_frame(geometry,perception):
    if not isinstance(geometry,GeometryInput) or not isinstance(perception,PerceptionInput):
        raise TypeError("Independent geometry/perception input ports required")
    for name in ("frame_key","rgb_ref","K","T_base_camera","pose_map_version","T_map_camera_cv","geometry_status","pose_provider"):
        if getattr(geometry,name)!=getattr(perception,name):
            raise ValueError("Consumer input mismatch: "+name)
    return geometry.frame_key
