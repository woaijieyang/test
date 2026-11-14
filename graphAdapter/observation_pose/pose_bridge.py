"""Frame-exact pose ingestion and validated pose/spatial-snapshot publication."""
from dataclasses import asdict
import hashlib,json
import numpy as np
from poseAdapter.pose_adapter import PoseAdapter
from poseAdapter.coordinate.calibration import Calibration,DepthSpec
from .alignment import array_hash

def record_estimate(estimate):
    return estimate.to_record()

def calibration_record(calibration):
    value=asdict(calibration);value["T_base_camera"]=calibration.T_base_camera.tolist()
    return value

class PoseExecutionBridge:
    """Authorize only an existing exact 30 degree host macro."""
    def __init__(self,adapter):
        self.adapter=adapter;self.authorized=None
    def begin_macro(self,action_id,count):
        self.authorized=None
        if self.adapter.recovery_status().get("active") and action_id in (2,3) and count==2:
            self.adapter.authorize_tracking_recovery("left" if action_id==2 else "right")
            self.authorized=action_id
    def pose_action(self,action_id,index,count):
        if self.adapter.recovery_status().get("active"):
            if action_id==self.authorized and count==2 and index==count:
                return "turn_left" if action_id==2 else "turn_right"
            return None
        return {1:"move_forward",2:"turn_left",3:"turn_right"}.get(action_id)
    def end_macro(self):
        try:
            if self.authorized is not None:self.adapter.end_tracking_recovery_attempt()
        finally:self.authorized=None

class PoseBridge:
    def __init__(self,input_config,profile,calibration,*,aligned_depth_spec:DepthSpec,adapter=None,alignment_hash=None,stream_mode=False,pose_provider="cuvslam_rtabmap_rgbd"):
        if pose_provider not in ('cuvslam_rtabmap_rgbd','simulator_ground_truth'):raise ValueError('Unknown pose provider')
        if pose_provider=='simulator_ground_truth' and (adapter is None or stream_mode):raise ValueError('Simulator pose requires an explicit adapter and endpoint capture')
        self.pose_provider=pose_provider
        self.adapter=adapter if adapter is not None else PoseAdapter(input_config,profile)
        self.stream_mode=stream_mode;self.sequence=0
        if stream_mode:
            from poseAdapter import EndpointPoseStream
            self.stream=EndpointPoseStream(self.adapter)
        self.calibration=calibration
        if (aligned_depth_spec.units,aligned_depth_spec.definition,aligned_depth_spec.source_dtype)!=("meters","z","float32"):
            raise ValueError("Pose input must declare aligned float32 metric z-depth")
        self.aligned_depth_spec=aligned_depth_spec
        self.expected_alignment_hash=alignment_hash
        self.execution=PoseExecutionBridge(self.adapter)
        self.pose_session=None
        self.pose_reader=None
        if pose_provider=='simulator_ground_truth':
            from graphAdapter.interfaces.pose import PoseReader
            self.pose_reader=PoseReader(self.adapter,source=pose_provider)
        self.frames={};self.latest_timestamp=-1;self.episode_uid=None;self._session_alignment_hash=alignment_hash

    def reset(self,episode_uid):
        if self.stream_mode:self.stream.reset(episode_uid,calibration=self.calibration,depth_spec=self.aligned_depth_spec)
        else:self.adapter.reset_episode(episode_uid,calibration=self.calibration,depth_spec=self.aligned_depth_spec)
        if self.pose_reader is not None:
            self.pose_session=self.adapter.get_mapping_session_identity()
            if self.pose_session.episode_id!=episode_uid:
                raise ValueError('Pose reset returned a different episode')
        self.frames.clear();self.latest_timestamp=-1;self.episode_uid=episode_uid;self._session_alignment_hash=self.expected_alignment_hash
        self.sequence=0

    def _product_signature(self,aligned):
        c=self.calibration;shape=(c.height,c.width)
        if not isinstance(aligned.calibration,Calibration) or calibration_record(aligned.calibration)!=calibration_record(c):
            raise ValueError("Aligned product/calibration mismatch")
        if (aligned.rgb.shape!=shape+(3,) or aligned.rgb.dtype!=np.uint8 or
            aligned.depth.shape!=shape or aligned.depth.dtype!=np.float32 or
            aligned.valid_mask.shape!=shape or aligned.valid_mask.dtype!=np.bool_ or
            aligned.source_pixel_map.shape!=shape+(2,) or aligned.source_pixel_map.dtype.kind not in "iu"):
            raise ValueError("Aligned product shape/dtype mismatch")
        if (not np.isfinite(aligned.depth).all() or np.any(aligned.depth<0) or
            not np.array_equal(aligned.valid_mask,aligned.depth>0) or
            np.any(aligned.source_pixel_map[~aligned.valid_mask]!=-1) or
            np.any(aligned.source_pixel_map[aligned.valid_mask]<0)):
            raise ValueError("Aligned depth/mask/source registration mismatch")
        if array_hash(aligned.rgb)!=aligned.raw_rgb_hash or array_hash(aligned.depth)!=aligned.aligned_depth_hash:
            raise ValueError("Aligned product content/hash mismatch")
        if not aligned.calibration_hash or (self._session_alignment_hash is not None and aligned.calibration_hash!=self._session_alignment_hash):
            raise ValueError("Aligned registration identity mismatch")
        declared={"camera":calibration_record(c),"depth_spec":asdict(self.aligned_depth_spec)}
        camera_hash=hashlib.sha256(json.dumps(declared,sort_keys=True,allow_nan=False).encode()).hexdigest()
        return (aligned.raw_rgb_hash,aligned.raw_depth_hash,aligned.aligned_depth_hash,
                array_hash(aligned.valid_mask),array_hash(aligned.source_pixel_map),
                aligned.calibration_hash,camera_hash,aligned.alignment_method)

    def next_timestamp(self):
        return PoseAdapter.logical_sensor_timestamp(self.sequence+1,120)

    def ingest_subframe(self,frame_uid,aligned,*,action,sample_index):
        if not self.stream_mode:raise RuntimeError('Subframes require the release4 stream')
        self._product_signature(aligned)
        stamp=self.next_timestamp()
        result=self.stream.push(episode_id=self.episode_uid,endpoint_id=frame_uid,sequence=self.sequence+1,
            timestamp_ns=stamp,sample_index=sample_index,action=action,rgb=aligned.rgb,depth=aligned.depth,collided=None)
        if result is not None:raise RuntimeError('Intermediate sample became a host endpoint')
        self.sequence+=1
        return None

    def ingest(self,frame_uid,timestamp_ns,aligned,*,action=None,collided=None):
        signature=(timestamp_ns,*self._product_signature(aligned))
        if frame_uid in self.frames:
            if self.frames[frame_uid]!=signature or action is not None:
                raise ValueError("Conflicting duplicate acquisition/product/calibration")
            return self.get_mapping_pose(frame_uid,timestamp_ns)
        if not frame_uid.startswith(self.episode_uid+":") or timestamp_ns<=self.latest_timestamp:
            raise ValueError("Wrong episode or unordered acquisition")
        if self.pose_reader is not None:
            from .provider_contract import simulator_pose_record
            frame=self.pose_reader.capture(episode_id=self.episode_uid,frame_id=frame_uid,timestamp_ns=timestamp_ns,
                expected_instance=self.pose_session.episode_instance)
            result=simulator_pose_record(frame,self.calibration.T_base_camera)
        elif self.stream_mode:
            if timestamp_ns!=self.next_timestamp():raise ValueError('Endpoint clock differs from sensor sequence')
            stream_action=action if self.sequence else None
            if self.sequence and action is None:stream_action='stop'
            index=12 if stream_action in ('move_forward','turn_left','turn_right')else 1
            result=self.stream.push(episode_id=self.episode_uid,endpoint_id=frame_uid,sequence=self.sequence+1,
                timestamp_ns=timestamp_ns,sample_index=index,action=stream_action,rgb=aligned.rgb,depth=aligned.depth,
                collided=(collided is True)if stream_action is not None else None)
            if result is None:raise RuntimeError('Canonical endpoint did not finish its pose group')
            self.sequence+=1
        else:
            self.adapter.push_observation(frame_id=frame_uid,timestamp_ns=timestamp_ns,
                rgb=aligned.rgb,depth=aligned.depth,action=action,collided=collided is True)
        self._session_alignment_hash=aligned.calibration_hash
        self.frames[frame_uid]=signature;self.latest_timestamp=timestamp_ns
        return result if self.pose_reader is not None else self.get_mapping_pose(frame_uid,timestamp_ns)

    def get_mapping_pose(self,frame_uid,timestamp_ns):
        if self.pose_provider=='simulator_ground_truth':
            from .provider_contract import simulator_pose_record
            frame=self.pose_reader.read(episode_id=self.episode_uid,frame_id=frame_uid,timestamp_ns=timestamp_ns,
                                        expected_instance=self.pose_session.episode_instance)
            return simulator_pose_record(frame,self.calibration.T_base_camera)
        atomic=getattr(self.adapter,"get_frame_snapshot",None)
        if callable(atomic):
            estimate,bindings=atomic(frame_uid,timestamp_ns=timestamp_ns,episode_id=self.episode_uid)
        else:
            # Compatibility/test adapters are still checked at this boundary.
            estimate=self.adapter.get_pose_for_frame(frame_uid,timestamp_ns=timestamp_ns,episode_id=self.episode_uid)
            bindings=self.adapter.spatial_bindings()
        if (estimate.episode_id,estimate.frame_id,estimate.timestamp_ns)!=(self.episode_uid,frame_uid,timestamp_ns):
            raise ValueError("Pose frame binding mismatch")
        if bindings is not None and (bindings.get("episode_id"),bindings.get("map_version"))!=(estimate.episode_id,estimate.map_version):
            raise ValueError("Pose/spatial snapshot episode/version mismatch")
        row=record_estimate(estimate)
        row["T_map_camera_cv"]=None;row["spatial_bindings"]=bindings;row["geometry_status"]="unavailable"
        if estimate.valid and estimate.source=="cuvslam_rtabmap_rgbd" and estimate.tracking_state=="tracking":
            support=(estimate.diagnostics or {}).get("measurement_support") or {}
            if support.get("kind")!=2 or type(support.get("used"))is not int or support["used"]<=0 or support.get("prediction_used")is not False:
                raise ValueError("Geometry requires current native measurement support")
            if bindings is None:raise ValueError("Measured combined pose has no matching spatial snapshot")
            key=estimate.rtab_keyframe_id
            frames=bindings.get("optimized_keyframes",{})
            if type(key)is not int or key<=0 or estimate.T_keyframe_base is None or str(key) not in frames:
                raise ValueError("Measured pose lacks an actual snapshot keyframe binding")
            from poseAdapter.coordinate.transforms import checked_transform
            reconstructed=checked_transform(frames[str(key)])@estimate.T_keyframe_base
            if not np.allclose(reconstructed,estimate.T_map_base,atol=2e-5,rtol=2e-6):
                raise ValueError("Pose disagrees with published snapshot keyframe geometry")
            row["T_map_camera_cv"]=(estimate.T_map_base@self.calibration.T_base_camera).tolist()
            row["geometry_status"]="available"
        return row

    def shutdown(self):
        if self.stream_mode:self.stream.close()
        else:self.adapter.shutdown()
