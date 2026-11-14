"""Raw-first endpoint capture with validated immutable packets and explicit failure states."""
import json,time,hashlib
from dataclasses import asdict
from pathlib import Path
import numpy as np
from poseAdapter import PoseAdapter,PoseInputConfig
from poseAdapter.coordinate.calibration import Calibration,DepthSpec
from poseAdapter.coordinate.frames import OPTICAL_TO_FLU
from poseAdapter.coordinate.transforms import transform
from .alignment import RGBDAlignmentBridge,intrinsic,archive_aligned_product
from .coordinator import Coordinator
from .pose_bridge import PoseBridge
from graphAdapter.interfaces.pose import PoseSessionChanged
from graphAdapter.observation_packet import ObservationPacket,geometry_input,perception_input,require_same_frame,freeze

class PoseInitializationFailed(RuntimeError):
    def __init__(self,cause,stage="native_reset"):
        self.cause=cause;self.stage=stage
        super().__init__(str(cause))

class CaptureAttemptAborted(RuntimeError):
    def __init__(self,reason,endpoint):
        self.endpoint=endpoint
        super().__init__(reason)

def camera_calibration(spec):
    p=np.asarray(spec["projection"],float);w,h=spec["width"],spec["height"]
    fx,fy=w*p[0,0]/2,h*p[1,1]/2
    cx,cy=(w-1)/2-w*p[0,2]/2,(h-1)/2+h*p[1,2]/2
    if not np.allclose(spec["orientation"],[0,0,0]):
        raise ValueError("Unsupported static camera rotation: explicit calibration required")
    mount=np.asarray(spec["position"])
    cal=Calibration(w,h,fx,fy,cx,cy,transform(OPTICAL_TO_FLU,[-mount[2],-mount[0],mount[1]]))
    pixels=np.array([[0.,w-1,cx],[0.,h-1,cy],[1.,1.,1.]])
    rays=np.linalg.inv(intrinsic(cal))@pixels
    projected=p@np.vstack([rays[0],-rays[1],-rays[2],np.ones(3)])
    ndc=projected[:2]/projected[3]
    checked=np.vstack([(ndc[0]+1)*w/2-.5,(1-ndc[1])*h/2-.5])
    error=float(np.abs(checked-pixels[:2]).max())
    if error>1e-5:raise ValueError("Projection pixel-center verification failed")
    return cal,error

def static_manifest(spec):
    """Archive only static sensor/execution fields, never an arbitrary observation."""
    if not isinstance(spec,dict):return None
    allowed=("width","height","hfov","projection","position","orientation","near","far","normalize_depth",
             "raw_units","raw_definition","raw_invalid_value","projection_source","projection_source_sha256")
    result={}
    for key in ("rgb","depth"):
        value=spec.get(key,{})
        result[key]={name:value[name] for name in allowed if name in value} if isinstance(value,dict) else None
    execution=spec.get("execution",{})
    if not isinstance(execution,dict):execution={}
    result["execution"]={name:execution[name] for name in ("forward_step_m","turn_degrees","max_episode_steps") if name in execution}
    return result

class AwarePoseHook:
    def __init__(self,output,profile,*,adapter_factory=None):
        self.pose_provider=profile.get('pose_provider','cuvslam_rtabmap_rgbd')
        if self.pose_provider not in ('cuvslam_rtabmap_rgbd','simulator_ground_truth'):raise ValueError('Unknown pose provider')
        self.simulator_pose=self.pose_provider=='simulator_ground_truth'
        if self.simulator_pose:
            from graphAdapter.interfaces.pose.policy import require_simulator_profile
            require_simulator_profile(profile)
            if adapter_factory is None:raise ValueError('Simulator pose requires an explicit isolated factory')
            if profile.get('map_memory',{}).get('enabled'):
                from graphAdapter.map_memory.worker import validate_mapping_profile
                validate_mapping_profile(profile['map_memory'])
        memory_options=profile.get("map_memory")
        if memory_options and memory_options.get("enabled") and memory_options.get("pose_input_mode")=="continuous":
            from .production import verify_pose_configuration,verify_package
            verify_pose_configuration(profile)
            verify_package(profile["pose_package"],actual_import=True)
        asynchronous=False
        if memory_options and memory_options.get("enabled"):
            asynchronous=memory_options.get("async_admission",False)
            if type(asynchronous)is not bool:raise ValueError("async_admission must be boolean")
            if asynchronous and (memory_options.get("pose_input_mode") not in ("continuous","provider_pose") or memory_options.get("execution_mode","live")!="live"):
                raise ValueError("Async admission requires explicit continuous/provider live memory")
            if asynchronous:
                budget=memory_options.get("max_episode_observations")
                capacity=memory_options.get("admission_capacity",2)
                if type(budget)is not int or budget<1 or type(capacity)is not int or capacity<1:
                    raise ValueError("Declare positive existing episode budget and admission capacity")
                lag=memory_options.get('decision_max_capture_lag',1)
                if type(lag)is not int or lag<0 or lag>capacity:raise ValueError('Decision lag must fit bounded admission capacity')
        from graphAdapter.map_memory.storage.routing import from_environment
        self.storage=from_environment();self.storage_episode=None
        if self.simulator_pose and self.storage is not None and self.storage.plan['owner_components'].get('pose')!='pose_provider':raise ValueError('Simulator pose requires a separately typed pose-provider lifecycle owner')
        self.coordinator=Coordinator(output,storage=self.storage)
        self.packet_stream=None if self.storage is not None else(self.coordinator.root/"observation-packets.jsonl").open("x")
        self.profile=profile;self.adapter_factory=adapter_factory
        self.release4=profile.get("pose_sampling")=="release4_12"
        self.pose=None;self.align=None;self.disabled_error=None;self.macro=None;self.macro_counter=0
        self.latest_packet=None;self.latest_geometry_input=None;self.latest_perception_input=None
        self.identity=None;self.calibration=None;self.calibration_hash=None
        self.reset_attempts=0;self.native_initialization_attempts=0;self.provider_initialization_attempts=0;self.packet_count=0
        self._aborted=False;self.abort_receipt=None
        self.latest_commit_receipt=None;self._aligned_receipt=None
        self.memory=None;self.memory_last=None;self.memory_started=False;self.memory_packet_count=0;self.memory_session=None
        self.memory_stream=None;self.memory_admitted_count=0
        memory_options=self.profile.get("map_memory")
        if memory_options and memory_options.get("enabled"):
            from graphAdapter.map_memory.worker import MemoryWorkerClient
            self.memory=MemoryWorkerClient(self.coordinator.root,self.coordinator.root.parent/"map_memory",memory_options)
            self.memory_started=True;self.memory_session=str(self.memory.session)
            if asynchronous:
                from .streaming_memory import StreamingMemoryBridge
                self.memory_stream=StreamingMemoryBridge(self.memory,self.coordinator,max_episode_observations=budget,
                    capacity=memory_options.get("admission_capacity",2),timeout=memory_options.get("frame_timeout_seconds",1200))

    def _release_retrieval_caches(self):
        cache=getattr(self,'retrieval_image_cache',None)
        if cache is not None:cache.close()
        self.retrieval_image_cache=None
        pages=getattr(self,'retrieval_page_cache',None)
        if pages is not None:pages.close()
        self.retrieval_page_cache=None
        features=getattr(self,'attachment_feature_cache',None)
        if features is not None:features.clear()
        self.attachment_feature_cache=None
        self.global_map_tile_cache=None

    def _clear_latest(self):
        self.latest_packet=self.latest_geometry_input=self.latest_perception_input=None
        self.latest_commit_receipt=None;self._aligned_receipt=None

    def active_pose_adapter(self):
        if self.pose is None:return None
        status=self.pose.adapter.get_status()
        if status.get('closed')or status.get('episode_id')!=self.coordinator.episode_uid:return None
        runtime=status.get('runtime')
        if isinstance(runtime,dict)and runtime.get('active')is False:return None
        return self.pose.adapter

    def committed_endpoint(self):
        if self._aborted or self.latest_packet is None or self.latest_commit_receipt is None:
            raise CaptureAttemptAborted("No current committed endpoint",self.coordinator.pending_endpoint)
        if self.latest_packet.frame_uid!=self.coordinator.frame_uid:
            raise RuntimeError("Committed endpoint identity is stale")
        return self.latest_packet,self.latest_commit_receipt

    def _error(self,stage,error,*,frame_uid=None,kind="pose_runtime_error"):
        reason=type(error).__name__+": "+str(error)
        self.coordinator.emit(kind,stage=stage,frame_uid=frame_uid or self.coordinator.frame_uid,error=reason)
        return reason

    def reset(self,episode_uid,sensor_spec,rgb,raw_depth,capture_monotonic_ns,*,identity=None,sensor_errors=(),capture_clock_source="endpoint",received_monotonic_ns=None):
        if self._aborted:raise CaptureAttemptAborted("Aborted attempt requires a fresh hook/output",self.coordinator.pending_endpoint)
        self._release_retrieval_caches()
        self.reset_attempts+=1
        import uuid
        self._pose_attempt_instance='uninitialized-'+uuid.uuid4().hex
        self.coordinator.reset(episode_uid,identity=identity)
        if self.storage is not None:
            self.storage_episode=self.coordinator.storage_episode
            self.packet_stream=(self.coordinator.root/episode_uid/'observation-packets.jsonl').open('x')
            if self.memory is not None:self.memory.begin_episode(episode_uid,identity)
        self.pose=None;self.align=None;self.disabled_error=None;self.macro=None
        self.identity=identity;self.calibration=None;self.calibration_hash=None
        self._clear_latest()
        self._pending_spec=static_manifest(sensor_spec)
        self._pending_sensor_errors=tuple(sensor_errors);self._needs_configuration=True
        return self.capture(rgb,raw_depth,capture_monotonic_ns,action_id=None,acquisition_errors=sensor_errors,capture_clock_source=capture_clock_source,received_monotonic_ns=received_monotonic_ns)

    @staticmethod
    def _archive_json(path,record):
        import os
        encoded=json.dumps(record,indent=2,allow_nan=False)
        with path.open("x") as stream:
            stream.write(encoded)
            stream.flush();os.fsync(stream.fileno())

    def _configure(self,folder):
        self._needs_configuration=False
        configuration_stage='calibration'
        try:
            # Raw acquisition has already been archived before any metadata work.
            self._archive_json(folder/"sensor_spec.json",self._pending_spec)
            if self._pending_sensor_errors:raise ValueError("; ".join(self._pending_sensor_errors))
            spec=self._pending_spec
            rgb_cal,rgb_error=camera_calibration(spec["rgb"])
            depth_cal,depth_error=camera_calibration(spec["depth"])
            depth_spec=DepthSpec("meters","z","float32",spec["depth"]["near"],spec["depth"]["far"])
            self.align=RGBDAlignmentBridge(rgb_cal,depth_cal,depth_spec,
                np.linalg.inv(rgb_cal.T_base_camera)@depth_cal.T_base_camera,invalid_values=(0.,))
            self.calibration=rgb_cal;self.calibration_hash=self.align.calibration_hash
            record=dict(rgb=asdict(rgb_cal),depth=asdict(depth_cal),depth_spec=asdict(depth_spec),
                rgb_projection_error_pixels=rgb_error,depth_projection_error_pixels=depth_error,
                sensor_clock=self.profile["sensor_clock"],timestamp_kind=self.profile["sensor_clock"]["kind"],
                calibration_hash=self.calibration_hash,depth_source="same-frame HabitatSim raw depth before HabitatLab transforms")
            for key in ("rgb","depth"):record[key]["T_base_camera"]=record[key]["T_base_camera"].tolist()
            self._archive_json(folder/"calibration.json",record)
            execution=spec["execution"]
            if self.simulator_pose:
                from types import SimpleNamespace
                navigation=SimpleNamespace(pose_backend='simulator_ground_truth',pose_calibration=rgb_cal,
                    turn_degrees=execution['turn_degrees'],forward_step=execution['forward_step_m'],pose_options={})
                options={}
            else:
                if self.release4:
                    from poseAdapter import release4_input
                    from .production import verify_package
                    configuration_stage='pose_package'
                    self._archive_json(folder/'pose-package.json',verify_package(self.profile['pose_package'],actual_import=True))
                    configuration_stage='pose_configuration'
                    navigation=release4_input(rgb_cal,forward_step=execution['forward_step_m'],turn_degrees=execution['turn_degrees'],
                        turn_samples=12,forward_samples=12,sensor_rate_hz=120)
                else:
                    navigation=PoseInputConfig(pose_tracking_recovery=True,pose_backend="cuvslam_rtabmap",
                        pose_calibration=rgb_cal,hfov=float(np.degrees(2*np.arctan(rgb_cal.width/(2*rgb_cal.fx)))),
                        sensor_height=float(rgb_cal.T_base_camera[2,3]),turn_degrees=execution["turn_degrees"],
                        forward_step=execution["forward_step_m"],pose_turn_sensor_substeps=1,pose_forward_sensor_substeps=1,
                        pose_sampling_strategy="primitive_endpoints",pose_sensor_rate_hz=self.profile["sensor_clock"]["rate_hz"])
                if navigation.turn_degrees!=15. or navigation.forward_step!=.25:raise ValueError("Host action calibration differs")
                options=dict(self.profile["pose_options"])
                if options["pose_backend"]!="cuvslam_rtabmap" or options.get("worker_command"):
                    raise ValueError("Production requires the actual isolated combined worker")
                if any(options[key]!=self.profile[key] for key in ("pose_backend","frontend_profile","rtab_registration_profile")):
                    raise ValueError("Conflicting pose profile fields")
                if self.release4:
                    expected=dict(navigation.pose_options,pose_backend=navigation.pose_backend)
                    if any(options.get(k)!=v for k,v in expected.items()):raise ValueError('Production pose options differ from release4 factory')
            aligned_spec=DepthSpec("meters","z","float32",depth_spec.near_m,depth_spec.far_m)
            if self.storage is not None:
                if not self.simulator_pose:options=dict(options,artifact_namespace=self.storage.native_namespace(self.storage_episode,self.coordinator.episode_uid))
                self.storage.session(self.storage_episode,'pose')
            adapter=self.adapter_factory(navigation,options) if self.adapter_factory else None
            self.pose=PoseBridge(navigation,options,rgb_cal,aligned_depth_spec=aligned_spec,
                adapter=adapter,alignment_hash=self.calibration_hash,stream_mode=self.release4,pose_provider=self.pose_provider)
            nav={key:value for key,value in vars(navigation).items() if key!="pose_calibration"}
            nav["pose_options"]=dict(navigation.pose_options)if navigation.pose_options is not None else None
            nav["pose_calibration"]={"file":str(folder/"calibration.json"),"camera":"rgb"}
            configuration_stage="configuration_archive"
            self._archive_json(folder/"effective-pose-config.json",
                dict(navigation=nav,pose_options=options,aligned_depth_spec=asdict(aligned_spec)))
        except OSError as error:
            if self.release4:raise PoseInitializationFailed(error,configuration_stage)from error
            raise
        except Exception as error:
            if self.release4:raise PoseInitializationFailed(error,configuration_stage)from error
            self.disabled_error=self._error("calibration",error);return
        try:
            self.provider_initialization_attempts+=1
            if not self.simulator_pose:self.native_initialization_attempts+=1
            self.pose.reset(self.coordinator.episode_uid)
            if not self.simulator_pose:self.pose.adapter.bind_recording(folder)
        except Exception as error:
            self.disabled_error=self._error('native_reset',error)
            raise PoseInitializationFailed(error)from error

    def _abort_capture(self,stage,error,rgb,depth):
        """Fail this attempt closed; preserve endpoint facts independently of live logs."""
        import copy,os,sys,uuid
        self._aborted=True
        self._release_retrieval_caches()
        self._clear_latest()
        record=copy.deepcopy(self.coordinator.pending_endpoint or {})
        record.update(kind="attempt_aborted",episode_uid=self.coordinator.episode_uid,
                      stage=stage,error=type(error).__name__+": "+str(error),committed=False)
        index=record.get("primitive_index");count=record.get("primitive_count")
        record["cancelled_macro_actions"]=([record["action_id"]]*(count-index)
            if type(index)is int and type(count)is int and 1<=index<=count else None)
        if getattr(self,"memory_stream",None) is not None:
            record["memory_async"]=self.memory_stream.failure_snapshot()
        backup={}
        try:
            base=self.coordinator.root/self.coordinator.episode_uid if self.storage is not None else self.coordinator.root
            folder=base/"aborted-endpoints"/uuid.uuid4().hex
            folder.mkdir(parents=True,exist_ok=False)
            for name,value in (("rgb",rgb),("depth",depth)):
                if value is None:continue
                try:
                    array=np.asarray(value)
                    if array.dtype.hasobject:raise TypeError("Object sensor array")
                    path=folder/(name+".npy")
                    with path.open("xb") as stream:
                        np.save(stream,array,allow_pickle=False);stream.flush();os.fsync(stream.fileno())
                    backup[name]=str(path)
                except Exception as detail:backup[name+"_error"]=type(detail).__name__+": "+str(detail)
            record["abort_raw_backup"]=backup
            receipt=folder/"attempt-abort.json"
            with receipt.open("x") as stream:
                json.dump(record,stream,allow_nan=False);stream.flush();os.fsync(stream.fileno())
            self.abort_receipt=str(receipt)
        except Exception as detail:
            record["abort_receipt_error"]=type(detail).__name__+": "+str(detail)
        try:self.coordinator.emit("attempt_aborted",frame_uid=record.get("frame_uid"),stage=stage,reason=record["error"])
        except Exception:pass
        try:
            if self.memory is not None:
                stream=getattr(self,"memory_stream",None)
                if stream is not None:
                    try:stream.close()
                    finally:
                        record["memory_async_after_close"]=stream.failure_snapshot()
                        self.memory_stream=None;self.memory=None
                else:self.memory.close(abort_reason=record["error"]);self.memory=None
        except Exception as detail:record["memory_shutdown_error"]=type(detail).__name__+": "+str(detail)
        try:
            if self.pose is not None:
                if self.storage is not None:self.storage.close_pose(self.storage_episode,self.pose)
                else:self.pose.shutdown()
        except Exception as detail:record["shutdown_error"]=type(detail).__name__+": "+str(detail)
        self.pose=None
        if self.abort_receipt is not None:
            try:
                detail_path=Path(self.abort_receipt).with_name("attempt-abort-cleanup.json")
                with detail_path.open("x") as stream:
                    json.dump(record,stream,allow_nan=False);stream.flush();os.fsync(stream.fileno())
            except Exception as detail:record["cleanup_receipt_error"]=str(detail)
        print("STAGE000_ATTEMPT_ABORTED "+json.dumps(record,allow_nan=False),file=sys.stderr,flush=True)
        raise CaptureAttemptAborted(record["error"],record)

    def pose_subframes(self,action_id,rows):
        if not self.release4 or self.pose is None or self.disabled_error:raise RuntimeError('Release4 pose stream not ready')
        if self._aborted:raise CaptureAttemptAborted('Aborted sample stream',self.coordinator.pending_endpoint)
        uid=f"{self.coordinator.episode_uid}:f{self.coordinator.capture_seq+1:06d}"
        action={1:'move_forward',2:'turn_left',3:'turn_right'}[action_id]
        for index,row in enumerate(rows,1):
            if row['sample_index']!=index:raise ValueError('Private subframe index mismatch')
            aligned=self.align.align(row['rgb'],row['depth'])
            self.pose.ingest_subframe(uid,aligned,action=action,sample_index=index)
            self.coordinator.emit('pose_sample',target_frame_uid=uid,sequence=self.pose.sequence,
                timestamp_ns=PoseAdapter.logical_sensor_timestamp(self.pose.sequence,120),sample_index=index,
                rgb_hash=aligned.raw_rgb_hash,raw_depth_hash=aligned.raw_depth_hash,aligned_depth_hash=aligned.aligned_depth_hash,
                canonical=False,debug_arrays_persisted=False)

    def abort_before_step(self,action_id,error):
        m=self.macro or{}
        self.coordinator.pending_endpoint=dict(frame_uid=f"{self.coordinator.episode_uid}:f{self.coordinator.capture_seq+1:06d}",
            action_id=action_id,primitive_executed=False,macro_id=m.get('macro_id'),
            primitive_index=m.get('index',0)+1,primitive_count=m.get('count'))
        self._abort_capture('pose_subframes_before_step',error,None,None)

    def begin_macro(self,action_id,count):
        if self._aborted:raise CaptureAttemptAborted("Attempt already aborted",self.coordinator.pending_endpoint)
        self.macro_counter+=1
        self.macro=dict(macro_id=self.macro_counter,action_id=action_id,count=count,index=0)
        if self.disabled_error is None and self.pose is not None:
            try:self.pose.execution.begin_macro(action_id,count)
            except Exception as error:self._error("begin_macro",error,kind="recovery_authorization_error")
            if self.pose.adapter.recovery_status()["active"] and self.pose.execution.authorized is None:
                self.coordinator.emit("WAITING_HOST_ACTION",action_id=action_id,primitive_count=count,required_turn_degrees=30)

    def _unavailable(self,archive,reason):
        if getattr(self,'simulator_pose',False):
            from graphAdapter.interfaces.pose import PoseFrame
            from .provider_contract import simulator_pose_record
            instance=self._pose_attempt_instance
            if self.pose is not None and self.pose.pose_session is not None:
                instance=self.pose.pose_session.episode_instance
            frame=PoseFrame('simulator_ground_truth',self.coordinator.episode_uid,instance,archive['frame_uid'],archive['sensor_timestamp_ns'],0,False,None,None,None)
            return simulator_pose_record(frame,None)
        return dict(episode_id=self.coordinator.episode_uid,frame_id=archive["frame_uid"],
            timestamp_ns=archive["sensor_timestamp_ns"],valid=False,tracking_state="unavailable",reason=reason,
            source=self.profile["pose_backend"],map_version=0,T_map_base=None,T_odom_base=None,
            T_map_camera_cv=None,geometry_status="unavailable",spatial_bindings=None)

    def capture(self,rgb,raw_depth,capture_monotonic_ns,*,action_id,terminal=False,collision=None,acquisition_errors=(),capture_clock_source="endpoint",received_monotonic_ns=None):
        try:
            return self._capture(rgb,raw_depth,capture_monotonic_ns,action_id=action_id,terminal=terminal,
                collision=collision,acquisition_errors=acquisition_errors,capture_clock_source=capture_clock_source,
                received_monotonic_ns=received_monotonic_ns)
        except CaptureAttemptAborted:
            raise
        except Exception as error:
            self._abort_capture("capture",error,rgb,raw_depth)

    def _capture(self,rgb,raw_depth,capture_monotonic_ns,*,action_id,terminal=False,collision=None,acquisition_errors=(),capture_clock_source="endpoint",received_monotonic_ns=None):
        if self._aborted:raise CaptureAttemptAborted("Attempt already aborted",self.coordinator.pending_endpoint)
        # Revoke the previous endpoint before doing any work that may fail.
        # Only this capture's own validated product may become latest again.
        self._clear_latest()
        clock=self.profile["sensor_clock"]
        if clock["kind"]!="static_simulator_sequence":raise ValueError("Declared simulator sequence clock required")
        stamp=(self.pose.next_timestamp()if self.release4 and self.pose is not None else
            PoseAdapter.logical_sensor_timestamp(1 if self.release4 else self.coordinator.capture_seq+1,clock["rate_hz"]))
        m=self.macro
        if action_id is not None and m is not None:m["index"]+=1
        archive=None;aligned_ref=None;pose=None;failure=None;stage="archive"
        try:
            archive=self.coordinator.capture(rgb,raw_depth,stamp,action_id=action_id,terminal=terminal,collision=collision,
                capture_monotonic_ns=capture_monotonic_ns,macro_id=m["macro_id"] if m else None,
                primitive_index=m["index"] if m else None,primitive_count=m["count"] if m else None,
                capture_clock_source=capture_clock_source,received_monotonic_ns=received_monotonic_ns)
            if archive["archive_failed"]:
                self._abort_capture("archive",RuntimeError(json.dumps(archive["archive_errors"])),rgb,raw_depth)
            for reason in acquisition_errors:
                self.coordinator.emit("sensor_endpoint_error",frame_uid=archive["frame_uid"],stage="endpoint",error=reason)
            folder=self.coordinator.root/self.coordinator.episode_uid
            stage="configuration_archive"
            if self._needs_configuration:self._configure(folder)
            stage="clock"
            if archive["clock_errors"]:
                raise ValueError("Endpoint clock invalid: "+json.dumps(archive["clock_errors"])+"; "+"; ".join(acquisition_errors))
            stage="alignment"
            if archive["archive_errors"]:
                causes="; ".join(acquisition_errors) or self.disabled_error or ""
                raise ValueError("Raw archive unavailable: "+json.dumps(archive["archive_errors"])+"; "+causes)
            if self.align is None:raise ValueError(self.disabled_error or "Calibration unavailable")
            aligned=self.align.align(rgb,raw_depth)
            if (aligned.raw_rgb_hash,aligned.raw_depth_hash)!=(archive["rgb_hash"],archive["depth_hash"]):
                raise ValueError("Alignment source hashes disagree with raw acquisition")
            frame_folder=Path(archive["raw_rgb_ref"]).parent
            stage="aligned_archive"
            retain_source_map=self.profile.get('storage_lifecycle',{}).get('retain_source_pixel_map',True)
            aligned_ref,self._aligned_receipt=archive_aligned_product(frame_folder,aligned,
                retain_source_pixel_map=retain_source_map)
            stage="alignment"
            self.coordinator.emit("alignment",frame_uid=archive["frame_uid"],method=aligned.alignment_method,
                raw_rgb_hash=aligned.raw_rgb_hash,raw_depth_hash=aligned.raw_depth_hash,
                aligned_depth_hash=aligned.aligned_depth_hash,calibration_hash=aligned.calibration_hash,
                valid_mask_typed_hash=self._aligned_receipt['valid_mask_typed_hash'],
                source_pixel_map_hash=self._aligned_receipt['source_pixel_map_hash'],
                source_pixel_map_storage=self._aligned_receipt['source_pixel_map_storage'])
            stage="pose"
            if self.disabled_error is not None:raise RuntimeError(self.disabled_error)
            action=self.pose.execution.pose_action(action_id,m["index"] if m else 0,m["count"] if m else 0)
            pose=self.pose.ingest(archive["frame_uid"],stamp,aligned,action=action,collided=collision)
            self.coordinator.emit("pose",frame_uid=archive["frame_uid"],pose=pose,
                sensor_sequence=self.pose.sequence if self.release4 else archive["capture_seq"],
                sampling_contract="release4_12"if self.release4 else None,canonical=True,
                runtime_artifacts=None if self.simulator_pose else self.pose.adapter.artifact_identity(),recovery=self.pose.adapter.recovery_status())
            if not self.simulator_pose and not self.release4 and self.pose.adapter.is_measurement_gap(self.pose.adapter.get_pose()) and not self.pose.adapter.recovery_status()["active"]:
                self.pose.adapter.begin_tracking_recovery()
        except CaptureAttemptAborted:
            raise
        except PoseSessionChanged as error:
            self._abort_capture('pose_session',error,rgb,raw_depth)
        except PoseInitializationFailed as error:
            self._abort_capture(error.stage,error.cause,rgb,raw_depth)
        except Exception as error:
            if self.release4 or (self.simulator_pose and stage=='pose' and isinstance(error,PermissionError)):
                self._abort_capture(stage,error,rgb,raw_depth)
            if archive is None or stage in {"aligned_archive","configuration_archive"}:self._abort_capture(stage,error,rgb,raw_depth)
            try:failure=self._error(stage,error)
            except Exception as logging_error:self._abort_capture("flow_log",logging_error,rgb,raw_depth)
            if archive is not None:
                pose=self._unavailable(archive,failure)
                self.coordinator.emit("geometry_unavailable",frame_uid=archive["frame_uid"],stage=stage,reason=failure)
        finally:
            if m and m["index"]==m["count"]:
                try:
                    if self.pose is not None:self.pose.execution.end_macro()
                except Exception as error:self._error("end_macro",error,kind="recovery_end_error")
                finally:self.macro=None
        if archive is None:self._abort_capture("archive",RuntimeError("Endpoint was not archived"),rgb,raw_depth)
        if pose is None:pose=self._unavailable(archive,failure or "Pose unavailable")
        k=tuple(tuple(float(v)for v in row)for row in intrinsic(self.calibration)) if self.calibration is not None else None
        mount=tuple(tuple(float(v)for v in row)for row in self.calibration.T_base_camera) if self.calibration is not None else None
        action_evidence=dict(action_id=action_id,terminal=terminal,collision=collision,macro_id=archive["macro_id"],
                             primitive_index=archive["primitive_index"],primitive_count=archive["primitive_count"])
        try:
            try:
                packet=ObservationPacket(self.coordinator.episode_uid,archive["frame_uid"],archive["env_step"],
                    archive["decision_id"],self.coordinator.event_seq+1,archive["capture_seq"],stamp,
                    archive["raw_rgb_ref"],archive["raw_depth_ref"],aligned_ref,self.calibration_hash,k,mount,
                    action_evidence,pose,capture_monotonic_ns,failure,self.identity,capture_clock_source,received_monotonic_ns,pose_provider=self.pose_provider)
                geometry=geometry_input(packet);perception=perception_input(packet);require_same_frame(geometry,perception)
            except Exception as error:
                try:failure=self._error("packet_validation",error)
                except Exception as logging_error:self._abort_capture("flow_log",logging_error,rgb,raw_depth)
                pose=self._unavailable(archive,failure)
                packet=ObservationPacket(self.coordinator.episode_uid,archive["frame_uid"],archive["env_step"],
                    archive["decision_id"],self.coordinator.event_seq+1,archive["capture_seq"],stamp,
                    archive["raw_rgb_ref"],archive["raw_depth_ref"],aligned_ref,self.calibration_hash,k,mount,
                    action_evidence,pose,capture_monotonic_ns,failure,self.identity,capture_clock_source,received_monotonic_ns,pose_provider=self.pose_provider)
                geometry=geometry_input(packet);perception=perception_input(packet);require_same_frame(geometry,perception)
            receipt=freeze(dict(episode_uid=packet.episode_uid,frame_uid=packet.frame_uid,
                capture_seq=packet.capture_seq,env_step=packet.env_step,packet_event_seq=packet.event_seq,
                packet_record_hash=hashlib.sha256(json.dumps(packet.to_record(),sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest(),
                rgb_hash=archive["rgb_hash"],raw_depth_hash=archive["depth_hash"],
                calibration_hash=packet.calibration_hash,alignment=self._aligned_receipt,committed=True))
            try:
                self.packet_stream.write(json.dumps(packet.to_record(),allow_nan=False)+"\n");self.packet_stream.flush()
                self.coordinator.emit("observation_packet",frame_uid=packet.frame_uid,packet=packet.to_record())
            except Exception as error:self._abort_capture("packet_commit",error,rgb,raw_depth)
            # Sole readable commit point, after both logs have completed their flush.
            self.packet_count+=1
            self.latest_packet=packet;self.latest_geometry_input=geometry;self.latest_perception_input=perception
            self.latest_commit_receipt=receipt
            if self.memory is not None:
                if self.memory.profile.get('execution_mode')=='archive_only':
                    self.memory_last=self.memory.record_source(packet,receipt)
                elif self.memory_stream is not None:
                    self.memory_stream.submit(packet,receipt,self.active_pose_adapter())
                    self.memory_admitted_count+=1
                    self.memory_packet_count=self.memory_stream.published_observations
                    self.memory_last=self.memory_stream.last_publication
                else:self.memory_last=self.memory.consume(packet,receipt,pose_adapter=None if self.simulator_pose else self.active_pose_adapter())
                if self.memory_stream is None:
                    self.memory_packet_count+=1
                    self.coordinator.emit("PublishedSnapshot",frame_uid=packet.frame_uid,
                        snapshot_id=self.memory_last["snapshot_id"],versions=self.memory_last.get("versions"),
                        source_packet_event_seq=packet.event_seq,cutoff_event_seq=packet.event_seq,shadow=True)
            return packet
        except CaptureAttemptAborted:
            raise
        except Exception as error:
            self._abort_capture("packet_validation_or_commit",error,rgb,raw_depth)

    def prepare_memory_read(self,*,read_deadline=None,poll_only=False):
        """Return one immutable host-visible handle; availability is not model use."""
        if self._aborted:raise CaptureAttemptAborted("Decision on aborted attempt",self.coordinator.pending_endpoint)
        if self.latest_packet is None or self.latest_packet.frame_uid!=self.coordinator.frame_uid:
            raise RuntimeError("Decision has no committed current endpoint")
        fresh=True
        if self.memory_stream is not None:
            limit=self.profile['map_memory'].get('decision_max_capture_lag',1)
            visibility=self.memory_stream.await_visible(self.latest_packet.capture_seq,max_capture_lag=limit,
                                                      read_deadline=read_deadline,poll_only=poll_only)
            fresh=visibility['fresh_enough']
            self.memory_packet_count=self.memory_stream.published_observations
            self.memory_last=self.memory_stream.last_publication
            self.coordinator.emit('MemoryVisibility',frame_uid=self.latest_packet.frame_uid,
                max_capture_lag=limit,**visibility)
        current=self.memory_last if fresh else None
        return freeze(dict(fresh_enough=fresh,episode_uid=self.latest_packet.episode_uid,current_frame_uid=self.latest_packet.frame_uid,
            current_capture_seq=self.latest_packet.capture_seq,pose_provider=self.pose_provider,
            snapshot_id=None if current is None else current['snapshot_id'],
            cutoff=None if current is None else current['cutoff'],versions=None if current is None else current['versions']))

    def decision(self):
        self.prepare_memory_read()
        return self.coordinator.decision()

    def record_model_interval(self,call_id,started_ns,ended_ns):
        if self.memory_stream is None:return
        if type(started_ns)is not int or type(ended_ns)is not int or ended_ns<started_ns:
            raise ValueError('Ordered model timing required')
        self.coordinator.emit('HostModelInterval',frame_uid=self.latest_packet.frame_uid,call_id=call_id,
            started_monotonic_ns=started_ns,ended_monotonic_ns=ended_ns,scope='generation_and_decode_wall_time')

    def end_episode(self,cancelled_actions):
        memory_error=None
        try:
            if self.macro is not None and self.pose is not None:
                try:self.pose.execution.end_macro()
                except Exception as error:self._error("end_episode_macro",error,kind="recovery_end_error")
            try:
                if self.memory is not None:
                    result=(self.memory_stream.end_episode(self.active_pose_adapter(),cancelled_actions)
                            if self.memory_stream is not None else self.memory.end_episode(cancelled_actions))
                    if self.memory_stream is not None:
                        self.memory_packet_count=self.memory_stream.published_observations
                        self.memory_last=self.memory_stream.last_publication
                    final=result.get("final_publication") if result else None
                    if final and not final.get("duplicate"):
                        self.coordinator.emit("MapCorrectionPublished",frame_uid=final["frame_uid"],
                            snapshot_id=final["snapshot_id"],versions=final["versions"],
                            source_packet_event_seq=final["source_packet_event_seq"],
                            cutoff_event_seq=final["cutoff"]["event_seq"],shadow=True)
            except Exception as error:memory_error=error
            finally:
                if self.pose is not None:
                    try:
                        if self.storage is not None:self.storage.close_pose(self.storage_episode,self.pose)
                        else:self.pose.shutdown()
                    except Exception as error:self._error("shutdown",error,kind="pose_shutdown_error")
                self.pose=None
            if memory_error is not None:
                self._abort_capture("memory_end_episode",memory_error,None,None)
        finally:
            self._release_retrieval_caches()
            self.pose=None;self.macro=None;self._clear_latest()
            if not self._aborted:
                try:self.coordinator.end_episode(cancelled_actions)
                except Exception as error:self._abort_capture("terminal_log",error,None,None)
            if self.storage is not None:
                self.storage.close_files(self.storage_episode,'source000',[self.packet_stream,self.coordinator.stream])
                self.packet_stream=None;self.coordinator.stream=None

    def close(self):
        try:
            if self.coordinator.episode_uid is not None:self.end_episode(())
        except Exception:
            if not self._aborted:raise
        finally:
            try:
                if self.memory is not None:
                    if self.memory_stream is not None:
                        self.memory_stream.close();self.memory_stream=None
                    else:self.memory.close(abort_reason="source attempt aborted"if self._aborted else None)
                    self.memory=None
            finally:
                try:
                    if self.packet_stream is not None:self.packet_stream.close()
                finally:
                    if self._aborted:
                        self.coordinator.episode_uid=None
                        if self.coordinator.stream is not None:self.coordinator.stream.close()
                    else:self.coordinator.close()
