"""Single endpoint service and correction boundaries for stage001 shadow memory.

No navigation, goal verification, Frontier or policy input construction belongs here.
"""
from __future__ import annotations
from pathlib import Path
import hashlib,json
import numpy as np
from .geometry.core import Q,checked_transform
from .storage.store import IntegrityError,VersionUnavailable,canonical

def measured(pose):
    if pose.get('source')=='simulator_ground_truth':
        from ..observation_pose.provider_contract import validate_simulator_pose_record
        from ..observation_packet import thaw
        return validate_simulator_pose_record(thaw(pose)).valid
    support=(pose.get("diagnostics")or{}).get("measurement_support")or{}
    return (pose.get("valid")is True and pose.get("geometry_status")=="available"
        and pose.get("source")=="cuvslam_rtabmap_rgbd" and pose.get("tracking_state")=="tracking"
        and support.get("kind")==2 and type(support.get("used"))is int and support["used"]>0
        and support.get("prediction_used")is False)

class GraphMapCorrectionConsumer:
    """Resolve each historical contribution through its own public keyframe binding."""
    def __init__(self,episode_uid):
        self.episode_uid=episode_uid
    def resolve(self,capture,bindings,*,restore_estimate=None):
        raw=canonical(bindings)
        snapshot=freeze(json.loads(raw)) if bindings is not None else None
        return self._resolve(capture,snapshot,restore_estimate=restore_estimate,
            snapshot_digest=hashlib.sha256(raw).hexdigest())

    def _resolve(self,capture,bindings,*,restore_estimate=None,snapshot_digest):
        original=capture["pose_record"]
        if original.get('source')=='simulator_ground_truth':
            from ..observation_pose.provider_contract import validate_simulator_pose_record
            from ..observation_packet import thaw
            frame=validate_simulator_pose_record(thaw(original),capture['T_base_camera'])
            if not frame.valid:return None
            if canonical(thaw(bindings))!=canonical(thaw(original['spatial_bindings'])):raise VersionUnavailable('Simulator frame cannot use another provider bindings')
            return dict(T_G_base=(Q@np.asarray(frame.T_map_base)).tolist(),
                T_G_cv=(Q@np.asarray(original['T_map_camera_cv'])).tolist(),
                binding=dict(kind='simulator_pose_snapshot',pose_map_version=0,source_frame_uid=frame.frame_id,episode_instance=frame.episode_instance))
        # Never make an originally unavailable observation spatial after the fact.
        if not measured(original):return None
        if bindings is None or bindings.get("episode_id")!=self.episode_uid:
            raise VersionUnavailable("Matching published spatial bindings unavailable")
        version=bindings.get("map_version")
        if type(version)is not int or version<0:raise IntegrityError("Invalid map revision")
        if original["episode_id"]!=self.episode_uid or original["frame_id"]!=capture["frame_uid"]:
            raise IntegrityError("Historical pose/frame identity mismatch")
        pose=original
        if restore_estimate is not None:
            restored=restore_estimate(original)
            pose=restored.to_record()if hasattr(restored,"to_record")else restored
            if (not pose.get("valid") or pose.get("episode_id")!=self.episode_uid
                or pose.get("frame_id")!=capture["frame_uid"]
                or pose.get("timestamp_ns")!=original["timestamp_ns"]
                or pose.get("map_version")!=version):
                raise VersionUnavailable("Public historical restore is held or on another revision")
        key=pose.get("rtab_keyframe_id");relative=pose.get("T_keyframe_base")
        frames=bindings.get("optimized_keyframes",{})
        if type(key)is not int or key<=0 or relative is None or str(key)not in frames:
            raise VersionUnavailable("Historical keyframe binding is missing;no guessed global offset")
        base=checked_transform(frames[str(key)])@checked_transform(relative)
        if restore_estimate is not None and not np.allclose(base,pose["T_map_base"],atol=2e-5,rtol=2e-6):
            raise IntegrityError("Restored estimate disagrees with published keyframe snapshot")
        mount=checked_transform(capture["T_base_camera"])
        camera=Q@base@mount
        return dict(frame_uid=capture["frame_uid"],episode_uid=self.episode_uid,
            pose_map_version=version,T_G_cv=camera.tolist(),T_G_base=(Q@base).tolist(),
            binding=dict(keyframe_id=key,T_keyframe_base=np.asarray(relative).tolist(),
                snapshot_hash=snapshot_digest,pose_map_version=version))

    def prepare(self,captures,bindings,*,restore_estimate=None):
        raw=canonical(bindings)
        snapshot=freeze(json.loads(raw)) if bindings is not None else None
        snapshot_digest=hashlib.sha256(raw).hexdigest()
        result={}
        for capture in sorted(captures,key=lambda x:x["capture_seq"]):
            if capture["episode_uid"]!=self.episode_uid:raise IntegrityError("Cross-episode contribution")
            result[capture["frame_uid"]]=self._resolve(capture,snapshot,restore_estimate=restore_estimate,snapshot_digest=snapshot_digest)
        return result

def execution_relation(previous,current,*,minimum_translation_m=.03,maximum_translation_m=.5):
    """Actual directed traversal evidence uses base odometry, never camera/map correction."""
    if (previous["episode_uid"]!=current["episode_uid"]
        or current["capture_seq"]!=previous["capture_seq"]+1):
        raise IntegrityError("Temporal endpoints must be consecutive in one episode")
    src,dst=previous["frame_uid"],current["frame_uid"]
    def edge(kind):
        identity=hashlib.sha256((kind+"|"+src+"|"+dst).encode()).hexdigest()
        return dict(id=identity,type=kind,src=src,dst=dst,evidence="actual_consecutive_capture")
    result=dict(temporal=edge("temporal_next"),traversed=None,motion="motion_unknown",reason=None)
    action=current["action"]
    if action.get("action_id")!=1:
        result["reason"]="not_forward_translation";return result
    if action.get("collision")is not False:
        result["reason"]="collision_or_missing_collision_feedback";return result
    a,b=previous["pose_record"],current["pose_record"]
    if not (measured(a)and measured(b)):
        result["reason"]="measurement_gap";return result
    from graphAdapter.interfaces.pose.odometry import continuous_odometry_chart
    odom_epoch, reason = continuous_odometry_chart(a, b)
    if reason is not None:
        result["reason"] = reason; return result
    odom_a=checked_transform(a["T_odom_base"]);odom_b=checked_transform(b["T_odom_base"])
    distance=float(np.linalg.norm(odom_b[:3,3]-odom_a[:3,3]))
    result["measured_base_translation_m"]=distance
    if not minimum_translation_m<distance<=maximum_translation_m:
        result["reason"]="noisy_small_or_implausible_displacement";return result
    traversed=edge("traversed")
    traversed.update(evidence="executed_forward_and_current_measured_base_odometry",
        direction="recorded_only",current_passability="unknown",straight_shortcut=False,
        odom_epoch=odom_epoch,estimated_translation_m=distance)
    result.update(traversed=traversed,motion="measured_translation",reason=None)
    return result

def cross_revision_entities(previous,current):
    """Correspondence follows original detection membership, never coincident native numbers."""
    result=[]
    active=[x for x in current if x["status"]=="active"]
    for old in previous:
        if old["status"]!="active":continue
        members=set(old["members"])
        overlap=[x for x in active if members&set(x["members"])]
        if not overlap:
            result.append(dict(epoch=old["epoch"],src=old["id"],dst_epoch=None,dst=None,status="retired"))
        elif len(overlap)==1 and members<=set(overlap[0]["members"]):
            new=overlap[0]
            result.append(dict(epoch=old["epoch"],src=old["id"],dst_epoch=new["epoch"],dst=new["id"],status="alias"))
        else:
            result.append(dict(epoch=old["epoch"],src=old["id"],dst_epoch=None,dst=None,status="ambiguous",
                candidates=[dict(epoch=x["epoch"],id=x["id"],overlap=len(members&set(x["members"])))for x in overlap]))
    return result


from collections import OrderedDict
from collections.abc import MutableMapping,Mapping
from .storage.store import decode_arrays,_verify_ref,freeze,VersionUnavailable
from .geometry.core import TSDFSubmapManager,S,A

class HistoricalObservationArchive(Mapping):
    """Archive owns images; active Scene only gets an authorized byte-bounded mapping."""
    def __init__(self,store,allowed):
        self.store=store;self.allowed=set(allowed)
    def __getitem__(self,key):
        if key not in self.allowed:raise KeyError(key)
        value=self.store.read_rgb(key)
        if value is None:raise KeyError(key)
        return value
    def __len__(self):return len(self.allowed)
    def __iter__(self):return iter(self.allowed)

class CameraDetectionArchive(MutableMapping):
    """Per-episode immutable camera detections; eviction drops RAM, not source."""
    def __init__(self,store,model_identity,*,max_bytes=512*1024*1024):
        self.store=store;self.model_identity=model_identity
        self.model_hash=hashlib.sha256(canonical(model_identity)).hexdigest()
        self.max_bytes=max_bytes;self.bytes=0;self.cache=OrderedDict()
    def _path(self,key):
        from .storage.store import _safe_uid
        return self.store.root/"detections"/(_safe_uid(key)+".meta.json")
    def record(self,key):
        record=json.loads(self._path(key).read_bytes())
        raw=self.store.raw(key)
        metadata=record["metadata"]
        if (record["frame_uid"]!=key or metadata["raw_signature"]!=raw["raw_signature"]
            or metadata["model_identity_hash"]!=self.model_hash):
            raise IntegrityError("Cached detections have a different frame/model provenance")
        return record
    def __contains__(self,key):return self._path(key).is_file()
    def __getitem__(self,key):
        if key in self.cache:
            value,size=self.cache.pop(key);self.cache[key]=(value,size);return value
        from .perception.scene import unpack_camera
        record=self.record(key)
        arrays=self.store.get_arrays(record["blob"]);value=unpack_camera(arrays,record["metadata"])
        self._remember(key,value)
        return value
    def __setitem__(self,key,value):
        from .perception.scene import pack_camera
        arrays,meta=pack_camera(value);raw=self.store.raw(key)
        meta.update(raw_signature=raw["raw_signature"],model_identity_hash=self.model_hash)
        self.store.save_detections(key,arrays,meta);self._remember(key,value)
    def _remember(self,key,value):
        value=freeze(value)
        sizes=sum(np.asarray(v).nbytes for k,v in value.items()if isinstance(v,np.ndarray))
        sizes+=sum(np.asarray(x).nbytes for k in ("local_points","local_colors")for x in value[k])
        if key in self.cache:self.bytes-=self.cache.pop(key)[1]
        if sizes<=self.max_bytes:
            while self.cache and self.bytes+sizes>self.max_bytes:
                _,(_,n)=self.cache.popitem(last=False);self.bytes-=n
            self.cache[key]=(value,sizes);self.bytes+=sizes
    def __delitem__(self,key):
        if key in self.cache:self.bytes-=self.cache.pop(key)[1]
    def __iter__(self):
        return (x.stem.removesuffix(".meta")for x in (self.store.root/"detections").glob("*.meta.json"))
    def __len__(self):return sum(1 for _ in self)

def uses_filesystem_capacity(resources):
    """Apply fixed byte ceilings only to profiles that request them."""
    mode = resources.get("disk_budget_mode", "configured_limits")
    if mode not in ("configured_limits", "filesystem_capacity"):
        raise ValueError("Unknown map-memory disk budget mode")
    return mode == "filesystem_capacity"


class MapMemoryService:
    """Prepare immutable endpoint revisions, then publish only after a version grant."""
    def __init__(self,store,cfg,cg_cfg,*,models,model_identity,geometry_options=None,cpu_contract=False,resource_limits=None,correction_options=None):
        from .perception.scene import MemoryOnlyScene
        from threadpoolctl import ThreadpoolController
        self._threadpool_controller=ThreadpoolController()
        self.last_branch_failures=()
        self.store=store;self.cfg=cfg;self.cg_cfg=cg_cfg;self.models=models
        self.cpu_contract=cpu_contract;self.model_identity=model_identity
        self.correction_options=dict(correction_options or {})
        if type(self.correction_options.get("record_geometry_write_contracts",False)) is not bool:
            raise ValueError("record_geometry_write_contracts must be boolean")
        self.resource_limits=dict(resource_limits or {});self.resource_samples=[]
        self.denoise_cache_bytes=self.resource_limits.get('denoise_keep_all_bytes',0)
        if type(self.denoise_cache_bytes) is not int or self.denoise_cache_bytes<0:
            raise ValueError('Nonnegative denoise cache budget required')
        if type(self.resource_limits.get("parallel_geometry_scene",False)) is not bool:
            raise ValueError("parallel_geometry_scene must be boolean")
        self.geometry_options=dict(geometry_options or {})
        self.camera=CameraDetectionArchive(store,model_identity,max_bytes=self.resource_limits.get("camera_cache_bytes",512*1024*1024))
        self.mapping_chart = None
        self.frames={};self.bindings=None;self.version=None;self.pointer=store.current
        self.archive=HistoricalObservationArchive(store,[])
        self.epoch=hashlib.sha256((store.episode_uid+"|unbound").encode()).hexdigest()
        self.scene=MemoryOnlyScene(cfg,cg_cfg,models=models,camera_cache=self.camera,
            observations=self.archive,epoch=self.epoch,cache_only=cpu_contract)
        self.scene.denoise_cache_bytes=self.denoise_cache_bytes
        # Fixed estimated episode gauge; no simulator scene bounds or GT origin.
        self.geometry=TSDFSubmapManager([0.,0.,0.],backing=store,**self.geometry_options)
        self.graph=None;self.prepared=None;self.tail_journal=None
        if self.pointer is not None:self._reload()

    def attach_tail_journal(self,journal):
        if self.prepared is not None or self.tail_journal is not None:
            raise IntegrityError("Cannot replace an active publication journal")
        if Path(journal.job.record['source_root']).resolve()!=self.store.root.resolve():
            raise IntegrityError("Publication journal belongs to another source store")
        if self.mapping_chart is None or self.mapping_chart.episode_instance!=journal.job.record['episode_instance']:
            raise IntegrityError("Publication journal belongs to another mapping session")
        from .correction_workspace import validate_append_only_lineage
        reader=self.store.open_reader()
        try:
            journal.reconcile(reader)
            validate_append_only_lineage(journal.job,reader,journal.snapshot())
        finally:reader.close()
        self.tail_journal=journal
    def detach_tail_journal(self):
        if self.prepared is not None:raise IntegrityError("Prepared observation must finish before journal detach")
        journal=self.tail_journal;self.tail_journal=None
        return journal
    def _reconcile_tail_journal(self):
        if self.tail_journal is not None:
            reader=self.store.open_reader()
            try:self.tail_journal.reconcile(reader)
            finally:reader.close()

    def _reload(self):
        from .perception.scene import MemoryOnlyScene
        reader=self.store.open_reader()
        try:
            reader.verify();graph=reader._graph
            if graph["model_identity"]!=self.model_identity:raise IntegrityError("Reload model identity mismatch")
            self.frames={uid:self.store.raw(uid)for uid in graph["views"]}
            self.archive=HistoricalObservationArchive(self.store,self.frames)
            self.geometry=TSDFSubmapManager.restore(graph["geometry_state"],backing=self.store)
            self.scene=MemoryOnlyScene.restore(self.cfg,self.cg_cfg,models=self.models,camera_cache=self.camera,
                observations=self.archive,state=graph["scene_state"],store=self.store,cache_only=self.cpu_contract)
            self.scene.denoise_cache_bytes=self.denoise_cache_bytes
            self.epoch=self.scene.epoch;self.version=graph["versions"]["pose_map_version"]
            self.bindings=graph["pose_bindings"];self.graph=graph;self.pointer=self.store.current
            state = graph.get("mapping_state")
            if state is not None and state["chart"] is not None:
                from poseAdapter.interfaces.mapping import MappingChart
                self.mapping_chart = MappingChart(**state["chart"])
        finally:reader.close()

    def check_resources(self,stage):
        import os,resource
        from .geometry.core import CapacityError
        limits=self.resource_limits
        stat=os.statvfs(self.store.root);free=stat.f_bavail*stat.f_frsize
        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
        if free<limits.get("minimum_filesystem_free_bytes",0):raise CapacityError("Filesystem reserve exhausted;source/history preserved")
        if rss>limits.get("ram_peak_bytes",2**63):raise CapacityError("Worker RAM budget exceeded")
        disk=self.store.accounted_bytes()
        if not uses_filesystem_capacity(limits) and disk>limits.get("max_episode_bytes",2**63):
            raise CapacityError("Episode disk budget exceeded;history is not deleted")
        current_rss=int(Path("/proc/self/statm").read_text().split()[1])*os.sysconf("SC_PAGE_SIZE")
        sample=dict(stage=stage,filesystem_free_bytes=free,rss_peak_bytes=rss,
            rss_peak_scope="process_lifetime",rss_current_bytes=current_rss,episode_bytes=disk,
            camera_cache_bytes=self.camera.bytes,resident_geometry_tiles=len(self.geometry._cache))
        self.resource_samples.append(sample)
        return sample

    def _depth(self,meta):
        ref=meta["files"]["depth"]
        return {}if ref is None else decode_arrays(_verify_ref(self.store.root,ref),meta["arrays"])

    def source_radius(self, depth, mask, intrinsic):
        """Bound source points and half-pixel/surface support without world projection."""
        from .geometry.core import checked_intrinsic, unproject_cv
        k = checked_intrinsic(intrinsic)
        good = np.asarray(mask) & np.isfinite(depth) & (depth > 0)
        v,u = np.nonzero(good)
        if not len(u):return 0.0
        values = np.asarray(depth)[v,u]
        rays = unproject_cv(np.stack((u,v),axis=1),np.ones(len(u)),k)
        norms = np.linalg.norm(rays,axis=1)
        half_pixel = .5*np.sqrt(1/k[0,0]**2+1/k[1,1]**2)
        return float(np.max(norms*values)+np.max(values)*half_pixel+
                     self.geometry.voxel_size*.5*(np.max(norms)+half_pixel))

    def assess_mapping_correction(self, sample, *, max_difference_m, point_radius_m, T_base_camera,
                                  current_source_radius_m=0.0):
        """Check current and historical pose effects in the existing M/G chart.

        The radius is an explicit bound on source camera-local points. This
        calculation does not run projection, fusion, detection or clustering.
        """
        from poseAdapter.interfaces.mapping import MappingSample
        if not isinstance(sample, MappingSample) or sample.latest_frame is not True:
            raise IntegrityError("Current atomic mapping input required")
        if (not np.isfinite([max_difference_m, point_radius_m]).all()
                or max_difference_m <= 0 or point_radius_m < 0):
            raise ValueError("Finite positive error limit and nonnegative radius required")
        if self.mapping_chart is None:
            return dict(action="initialize", reasons=["initial"], max_displacement_m=0.0)
        if (sample.episode_id,sample.episode_instance) != (self.mapping_chart.episode_id,self.mapping_chart.episode_instance):
            raise IntegrityError("Correction assessment belongs to another episode instance")
        if sample.odometry_epoch != self.mapping_chart.odometry_epoch:
            return dict(action="correct", reasons=["odometry_epoch_changed"], max_displacement_m=None)
        projected = self.mapping_chart.project(sample)
        mount = checked_transform(T_base_camera)
        current = Q @ np.asarray(projected["T_map_base"]) @ mount
        target_current = Q @ np.asarray(sample.T_map_odom) @ np.asarray(sample.T_odom_base) @ mount
        def displacement(before, after, radius):
            before, after = np.asarray(before), np.asarray(after)
            return float(np.linalg.norm(after[:3,3]-before[:3,3])
                         + radius*np.linalg.norm(after[:3,:3]-before[:3,:3],ord=2))
        worst = displacement(current, target_current,max(point_radius_m,current_source_radius_m))
        worst_frame = sample.frame_id
        changed_frames = 0
        # Reuse each frame's original keyframe binding. Do not replace history
        # with the current map-to-odometry transform.
        resolved = GraphMapCorrectionConsumer(self.store.episode_uid).prepare(
            list(self.frames.values()), sample.bindings)
        for uid, pose in resolved.items():
            old = self.graph["views"][uid]
            if pose is None:
                continue
            if old["T_G_cv"] is None:
                raise IntegrityError("Measured history lacks its committed mapping pose")
            if old.get("source_radius_m") is None:
                raise IntegrityError("Continuous map lacks a source-support radius")
            effect = displacement(old["T_G_cv"], pose["T_G_cv"],max(point_radius_m,old["source_radius_m"]))
            if not np.array_equal(old["T_G_cv"],pose["T_G_cv"]):
                changed_frames += 1
            if effect > worst:
                worst, worst_frame = effect, uid
        return dict(action="correct" if worst>max_difference_m else "append",
                    reasons=["estimated_spatial_effect"] if worst>max_difference_m else [],
                    max_displacement_m=worst, worst_frame=worst_frame,
                    changed_frames=changed_frames, checked_frames=len(resolved),
                    radius_m=float(point_radius_m), difference_limit_m=float(max_difference_m),
                    reference="published_native_correction_target",
                    applied_map_version=self.mapping_chart.applied_map_version,
                    native_map_version=sample.native_map_version)

    def assess_terminal_correction(self,target,*,max_difference_m,point_radius_m):
        """Assess retained spatial evidence; no fusion, inference or publication."""
        from poseAdapter.interfaces.mapping import CorrectionSnapshot
        if not isinstance(target,CorrectionSnapshot):raise IntegrityError("Atomic correction target required")
        if not np.isfinite([max_difference_m,point_radius_m]).all() or max_difference_m<=0 or point_radius_m<0:
            raise ValueError("Finite positive threshold and nonnegative radius required")
        if self.mapping_chart is None:raise IntegrityError("No accepted continuous mapping chart")
        chart=self.mapping_chart
        if (target.episode_id,target.episode_instance)!=(chart.episode_id,chart.episode_instance):
            raise IntegrityError("Terminal correction session differs")
        latest=max(self.frames.values(),key=lambda row:row['capture_seq'])
        measured_time=max((row['sensor_timestamp_ns'] for row in self.frames.values() if measured(row['pose_record'])),default=0)
        if target.frame_id!=latest['frame_uid'] or not measured_time<=target.timestamp_ns<=latest['sensor_timestamp_ns']:
            raise IntegrityError("Terminal correction source is outside the committed frontier")
        if target.native_map_version<chart.applied_map_version:raise IntegrityError("Correction target version regressed")
        if target.odometry_epoch!=chart.odometry_epoch:
            return dict(action='correct',reason='odometry_epoch_changed',max_displacement_m=None)
        resolved=GraphMapCorrectionConsumer(self.store.episode_uid).prepare(list(self.frames.values()),target.bindings)
        worst=0.;affected=[];worst_frame=None
        for uid,pose in resolved.items():
            if pose is None:continue
            old=self.graph['views'][uid]
            if old['T_G_cv'] is None or old.get('source_radius_m') is None:raise IntegrityError('Missing committed spatial support')
            before=np.asarray(old['T_G_cv']);after=np.asarray(pose['T_G_cv'])
            radius=max(point_radius_m,old['source_radius_m'])
            effect=float(np.linalg.norm(after[:3,3]-before[:3,3])+radius*np.linalg.norm(after[:3,:3]-before[:3,:3],ord=2))
            if effect>worst:worst=effect;worst_frame=uid
            if effect>max_difference_m:affected.append(uid)
        return dict(action='correct' if affected else 'retain',reason='spatial_threshold_exceeded' if affected else 'below_spatial_threshold',
            max_displacement_m=worst,worst_frame=worst_frame,affected_frame_uids=affected,
            checked_frames=len(resolved),difference_limit_m=float(max_difference_m),
            applied_map_version=chart.applied_map_version,native_target_version=target.native_map_version,
            cutoff=dict(self.pointer['cutoff']),published=False)

    def prepare_endpoint(self,packet,rgb,raw_depth,aligned_depth,valid_mask,*,
                         bindings=None,cutoff=None,host_view=None,host_transform=None,committed_receipt=None,mapping_sample=None,apply_mapping_correction=False):
        from graphAdapter.observation_packet import ObservationPacket
        from graphAdapter.observation_pose.alignment import array_hash
        from .perception.scene import MemoryOnlyScene,VSMGraph
        if not isinstance(packet,ObservationPacket):packet=ObservationPacket(**packet)
        if type(apply_mapping_correction) is not bool:
            raise ValueError("Explicit correction decision required")
        capture=packet.to_record();uid=packet.frame_uid
        if self.graph is not None and self.graph.get('pose_provider','cuvslam_rtabmap_rgbd')!=packet.pose_provider:
            raise IntegrityError('Pose provider cannot change within a map episode')
        if packet.pose_provider=='simulator_ground_truth':
            if mapping_sample is not None or self.mapping_chart is not None or apply_mapping_correction:
                raise IntegrityError('Simulator pose cannot enter native SLAM correction channel')
            if self.frames:
                previous=next(iter(self.frames.values()))['pose_record']
                if previous.get('episode_instance')!=capture['pose_record']['episode_instance']:raise IntegrityError('Simulator pose session changed within map')
        continuous = self.mapping_chart is not None or mapping_sample is not None
        proposed_chart = self.mapping_chart
        if mapping_sample is not None:
            if self.mapping_chart is None and self.graph is not None and any(
                    view["T_G_cv"] is not None for view in self.graph["views"].values()):
                raise IntegrityError("Continuous mapping requires a fresh spatial episode")
            from poseAdapter.interfaces.mapping import MappingSample, MappingChart
            if not isinstance(mapping_sample, MappingSample):
                raise IntegrityError("Validated continuous mapping sample required")
            if (mapping_sample.episode_id != packet.episode_uid or mapping_sample.frame_id != uid
                    or mapping_sample.timestamp_ns != packet.sensor_timestamp_ns):
                raise IntegrityError("Mapping sample does not match the archived endpoint")
            if not np.array_equal(mapping_sample.T_odom_base, capture["pose_record"].get("T_odom_base")):
                raise IntegrityError("Mapping sample odometry differs from the source packet")
            proposed_chart = (MappingChart.from_sample(mapping_sample) if self.mapping_chart is None
                              else self.mapping_chart.propose_correction(mapping_sample) if apply_mapping_correction
                              else self.mapping_chart)
            proposed_chart.project(mapping_sample)
        elif apply_mapping_correction:
            raise IntegrityError("Correction requires an atomic measured target")
        elif continuous and measured(capture["pose_record"]):
            raise IntegrityError("Continuous mapping sample missing for a measured endpoint")
        if self.resource_limits:self.check_resources("before_archive")
        if packet.episode_uid!=self.store.episode_uid:raise IntegrityError("Endpoint from another episode")
        if (committed_receipt is None or committed_receipt.get("committed")is not True
            or committed_receipt.get("episode_uid")!=packet.episode_uid
            or committed_receipt.get("frame_uid")!=uid
            or committed_receipt.get("capture_seq")!=packet.capture_seq
            or committed_receipt.get("env_step")!=packet.env_step
            or committed_receipt.get("packet_event_seq")!=packet.event_seq
            or committed_receipt.get("calibration_hash")!=packet.calibration_hash
            or committed_receipt.get("packet_record_hash")!=hashlib.sha256(canonical(capture)).hexdigest()):
            raise IntegrityError("A matching successful000packet commit receipt is required")
        for value,key in ((rgb,"rgb_hash"),(raw_depth,"raw_depth_hash")):
            if (None if value is None else array_hash(value))!=committed_receipt.get(key):
                raise IntegrityError("000 archived sensor content differs: "+key)
        alignment=committed_receipt.get("alignment")
        if packet.aligned_ref is None:
            if aligned_depth is not None or valid_mask is not None:
                raise IntegrityError("Uncommitted aligned material supplied")
        elif (alignment is None or aligned_depth is None or valid_mask is None
              or array_hash(aligned_depth)!=alignment["aligned_depth_hash"]
              or hashlib.sha256(np.ascontiguousarray(valid_mask).tobytes()).hexdigest()!=alignment["valid_mask_hash"]):
            raise IntegrityError("000 aligned depth/mask content mismatch")
        cutoff=dict(cutoff or dict(capture_seq=packet.capture_seq,event_seq=packet.event_seq))
        if packet.capture_seq>cutoff["capture_seq"]or packet.event_seq>cutoff["event_seq"]:
            raise IntegrityError("Future endpoint")
        if uid not in self.frames and packet.capture_seq!=len(self.frames)+1:
            raise IntegrityError("Every actual primitive endpoint must be supplied in order")
        if uid in self.frames and packet.capture_seq!=len(self.frames):
            raise IntegrityError("Late endpoint behind CURRENT;pin its historical revision")
        if self.tail_journal is not None:
            if apply_mapping_correction:raise IntegrityError("Active detached job requires append-only observation publication")
            from .async_admission import FrozenObservation
            frozen=FrozenObservation.create(packet,committed_receipt,mapping_sample=mapping_sample,
                episode_instance=self.tail_journal.job.record['episode_instance'])
            self.tail_journal.prepare(frozen)
        raw=self.store.archive_frame(capture,rgb,raw_depth,aligned_depth,valid_mask,
            host_view=host_view,host_transform=host_transform)
        if uid in self.frames:
            if packet.capture_seq!=len(self.frames):raise IntegrityError("Late endpoint behind CURRENT;pin its historical revision")
            if self.frames[uid]["raw_signature"]!=raw["raw_signature"]:raise IntegrityError("Duplicate endpoint changed")
            if (not apply_mapping_correction or
                    (self.graph.get("mapping_state",{}).get("correction_applied") is True
                     and canonical(mapping_sample.bindings)==canonical(self.bindings))):
                self._reconcile_tail_journal()
                return dict(duplicate=True,snapshot_id=self.pointer["snapshot_id"]if self.pointer else None)
        frames=dict(self.frames);frames[uid]=raw
        return self._prepare_frames(frames,raw,capture,bindings,cutoff,mapping_sample,
            apply_mapping_correction,continuous,proposed_chart,rgb,aligned_depth)

    def prepare_correction(self,correction,*,derivation_source=None):
        if self.tail_journal is not None:raise IntegrityError("Detach active tail journal before a separate correction")
        from poseAdapter.interfaces.mapping import CorrectionSnapshot
        from graphAdapter.observation_packet import thaw
        if not isinstance(correction,CorrectionSnapshot):
            raise IntegrityError("Published correction snapshot required")
        if self.mapping_chart is None:
            return dict(duplicate=True,snapshot_id=self.pointer["snapshot_id"] if self.pointer else None)
        if derivation_source is not None:
            # Public provenance may differ from the private export's storage
            # parent. Accept it only from this frozen workspace's job contract.
            import re
            contract=json.loads((self.store.root/"CORRECTION_INPUT.json").read_bytes())
            job=contract["job"]
            if (not isinstance(derivation_source,str) or re.fullmatch("[0-9a-f]{64}",derivation_source) is None
                    or hashlib.sha256(canonical(job)).hexdigest()!=contract["job_sha256"]
                    or derivation_source!=job["base_snapshot_id"]
                    or canonical(correction.to_record())!=canonical(job["target_provenance"])
                    or self.pointer["cutoff"]!=job["base_cutoff"]):
                raise IntegrityError("Detached derivation source differs from frozen job")
        proposed=self.mapping_chart.propose_correction(correction)
        if (canonical(correction.bindings)==canonical(self.bindings)
                and self.graph.get("mapping_state",{}).get("correction_applied") is True):
            return dict(duplicate=True,snapshot_id=self.pointer["snapshot_id"])
        raw=max(self.frames.values(),key=lambda x:x["capture_seq"])
        latest_measured=max((meta["sensor_timestamp_ns"] for meta in self.frames.values()
                             if measured(meta["pose_record"])),default=0)
        if correction.timestamp_ns<latest_measured:
            raise VersionUnavailable("Correction target predates measured mapping contributions")
        capture=thaw(raw)
        cutoff=dict(capture_seq=raw["capture_seq"],event_seq=raw["event_seq"])
        return self._prepare_frames(dict(self.frames),raw,capture,correction.bindings,cutoff,
            correction,True,True,proposed,None,None,derivation_source=derivation_source)

    def _prepare_frames(self,frames,raw,capture,bindings,cutoff,mapping_sample,
                        apply_mapping_correction,continuous,proposed_chart,rgb,aligned_depth,*,derivation_source=None):
        from .perception.scene import MemoryOnlyScene,VSMGraph
        self.last_branch_failures=()
        base_snapshot_id=self.pointer["snapshot_id"] if self.pointer else None
        uid=raw["frame_uid"]
        archive=HistoricalObservationArchive(self.store,frames)
        target=bindings if bindings is not None else capture["pose_record"].get("spatial_bindings")
        if target is None:target=self.bindings
        if continuous:
            target = (mapping_sample.bindings if apply_mapping_correction or self.mapping_chart is None
                      else self.bindings)
        version=target["map_version"]if target is not None else None
        if version is not None and self.version is not None and version<self.version:
            raise IntegrityError("Pose map revision regressed")
        if self.bindings is not None and target is not None and version==self.version:
            previous=self.bindings.get("optimized_keyframes",{});now=target.get("optimized_keyframes",{})
            if any(k not in now or not np.array_equal(v,now[k])for k,v in previous.items()):
                raise IntegrityError("Existing keyframe changed without map version advance")
        if continuous and not apply_mapping_correction:
            corrected = {}
            for frame, meta in frames.items():
                if frame in self.frames:
                    old = self.graph["views"][frame]
                    corrected[frame] = None if old["T_G_cv"] is None else dict(
                        T_G_cv=old["T_G_cv"],T_G_base=old["T_G_base"],binding=old["pose_binding"])
                elif not measured(meta["pose_record"]):
                    corrected[frame] = None
                else:
                    projected = proposed_chart.project(mapping_sample)
                    base = np.asarray(projected["T_map_base"])
                    camera = Q @ base @ np.asarray(meta["T_base_camera"])
                    binding = dict(kind="episode_linked_odometry",pose_map_version=version,
                                   source_frame_uid=frame,source_native_map_version=mapping_sample.native_map_version,
                                   chart_reference_frame_id=proposed_chart.reference_frame_id)
                    corrected[frame] = dict(T_G_cv=camera.tolist(),T_G_base=(Q@base).tolist(),binding=binding)
        else:
            corrected=GraphMapCorrectionConsumer(self.store.episode_uid).prepare(list(frames.values()),target)
        changed=version!=self.version
        historical_pose_change = apply_mapping_correction and self.graph is not None and any(
            (corrected[frame] is None) != (old["T_G_cv"] is None) or
            (corrected[frame] is not None and any(
                not np.array_equal(corrected[frame][key], old[key]) for key in ("T_G_cv","T_G_base")))
            for frame, old in self.graph["views"].items())
        rebuild_needed = changed or historical_pose_change
        reuse=False
        historical_frames_compared = 0
        first_changed_frame = None
        if changed and self.graph is not None and self.correction_options.get("reuse_exact_unchanged_history",False):
            # Compare resolved full camera/base matrices for every committed
            # contribution. Version numbers,new-keyframe counts or tolerances
            # are insufficient proof of geometric equivalence.
            reuse=True
            for frame,old in self.graph["views"].items():
                historical_frames_compared += 1
                now=corrected[frame]
                if (now is None)!=(old["T_G_cv"]is None):
                    first_changed_frame = frame
                    reuse=False;break
                if now is not None and any(not np.array_equal(now[k],old[k])for k in ("T_G_cv","T_G_base")):
                    first_changed_frame = frame
                    reuse=False;break
        if rebuild_needed:
            parent=derivation_source or (self.pointer["snapshot_id"]if self.pointer else"initial")
            epoch=hashlib.sha256((self.store.episode_uid+"|"+parent+"|"+str(version)).encode()).hexdigest()
        else:epoch=self.epoch
        full_rebuild=rebuild_needed and not reuse
        from contextlib import nullcontext,ExitStack
        from concurrent.futures import ThreadPoolExecutor
        from collections import deque
        from time import perf_counter
        parallel=self.resource_limits.get("parallel_geometry_scene",False)
        if type(parallel) is not bool:raise ValueError("parallel_geometry_scene must be boolean")
        from .storage.replay import WriteBackReplayTileBacking
        replay_storage = None
        reserve = self.resource_limits.get("minimum_filesystem_free_bytes", 0)
        backing = WriteBackReplayTileBacking(self.store, minimum_free_bytes=reserve,
            max_buffer_bytes=self.resource_limits.get("replay_writeback_bytes",64*1024*1024),
            max_pending_tiles=self.geometry.max_candidate_tiles) if full_rebuild else nullcontext()
        with backing as replay_backing,ExitStack() as work_scope:
            if full_rebuild:
                scene=MemoryOnlyScene(self.cfg,self.cg_cfg,models=self.models,camera_cache=self.camera,
                    observations=archive,epoch=epoch,cache_only=self.cpu_contract,
                    clustering_cache=self.scene.clustering.split_cache)
                scene.denoise_cache_bytes=self.denoise_cache_bytes
                geometry=TSDFSubmapManager(self.geometry.origin_G,backing=replay_backing,**self.geometry_options)
                replay=list(frames.values())
            else:
                scene=self.scene.fork(copy_on_write=continuous);scene.observations=archive;scene.epoch=epoch
                geometry=self.geometry.fork();replay=[] if uid in self.frames else [raw]
            # Camera data are immutable source facts, retained even if derived preparation fails.
            if rgb is not None:
                k=np.asarray(capture["K"],float).copy()if capture["K"] is not None else None
                if k is not None:k[1,2]=rgb.shape[0]-1-k[1,2]
                scene.prepare_camera(rgb,aligned_depth,k,uid)
            results={}if full_rebuild or self.graph is None else dict(self.graph["geometry_results"])
            # sklearn's BLAS limiter is process-global. Pin the entire shared
            # numerical scope, so nested Scene KMeans restores 1 rather than
            # changing the geometry thread's BLAS policy mid-projection.
            work_scope.enter_context(self._threadpool_controller.limit(limits=1,user_api="blas"))
            blas_info=[x for x in self._threadpool_controller.info() if x["user_api"]=="blas"]
            if any(x["num_threads"]!=1 for x in blas_info):
                raise RuntimeError("Parallel mapping requires stable single-thread BLAS")
            geometry_jobs=deque();submitted_jobs=[]
            geometry_worker=(work_scope.enter_context(ThreadPoolExecutor(max_workers=1,
                thread_name_prefix="graph-geometry")) if parallel and replay else None)
            processing_metrics=dict(parallel_geometry_scene=geometry_worker is not None,
                geometry_seconds=0.,scene_seconds=0.,geometry_queue_peak=0,
                geometry_frame_uids=[],scene_frame_uids=[],
                blas_thread_counts={x["prefix"]:x["num_threads"] for x in blas_info})
            def integrate_geometry(frame,image,aligned,mask,intrinsic,transform,source_hash):
                started=perf_counter()
                extra={"collect_write_contracts":True} if self.correction_options.get("record_geometry_write_contracts",False) else {}
                value=geometry.integrate(frame,image,aligned,mask,intrinsic,transform,source_hash=source_hash,**extra)
                if replay_backing is not None:replay_backing.prune(geometry.records.values())
                receipt=dict(frame_uid=frame,source_signature=source_hash,geometry_signature=geometry.frames.get(frame))
                if not isinstance(receipt["geometry_signature"],str):
                    raise IntegrityError("Geometry branch did not commit its frame contribution")
                return value,perf_counter()-started,receipt
            def collect_geometry():
                frame,future=geometry_jobs.popleft()
                try:
                    result,seconds,receipt=future.result()
                    if receipt["frame_uid"]!=frame or receipt["source_signature"]!=frames[frame]["raw_signature"]:
                        raise IntegrityError("Geometry receipt disagrees with the submitted observation")
                except BaseException as error:
                    error._graph_branch="geometry";error._graph_frame_uid=frame
                    raise
                results[frame]=result
                processing_metrics["geometry_seconds"]+=seconds
                processing_metrics["geometry_frame_uids"].append(receipt["frame_uid"])
            try:
                for meta in sorted(replay,key=lambda x:x["capture_seq"]):
                    frame=meta["frame_uid"];pose=corrected[frame]
                    if pose is None:results[frame]=dict(has_evidence=False,reason="visual_only_pose");continue
                    # Apply backpressure before decoding a third replay payload.
                    if geometry_worker is not None and len(geometry_jobs)==2:collect_geometry()
                    image=archive[frame];depth=self._depth(meta);aligned=depth.get("aligned_depth");mask=depth.get("valid_mask")
                    if aligned is None or mask is None:raise IntegrityError("Spatial endpoint has no aligned depth/mask")
                    k=np.asarray(meta["K"],float);up=k.copy();up[1,2]=image.shape[0]-1-k[1,2]
                    t=np.asarray(pose["T_G_cv"]);base=np.asarray(pose["T_G_base"])[:3,3]
                    index=np.rint(A[:3,:3]@(base-geometry.origin_G)/geometry.voxel_size)
                    if geometry_worker is not None:
                        # One geometry owner preserves source frame order. There
                        # are at most two immutable RGB-D payloads in flight.
                        future=geometry_worker.submit(integrate_geometry,frame,image,aligned,mask,k,t,meta["raw_signature"])
                        geometry_jobs.append((frame,future));submitted_jobs.append((frame,future))
                        processing_metrics["geometry_queue_peak"]=max(processing_metrics["geometry_queue_peak"],len(geometry_jobs))
                    started=perf_counter()
                    try:scene.fuse(image,np.array(aligned,copy=True),up,t@S,base,index,frame,frame_idx=meta["capture_seq"]-1)
                    except BaseException as error:
                        error._graph_branch="scene";error._graph_frame_uid=frame
                        raise
                    processing_metrics["scene_seconds"]+=perf_counter()-started
                    if scene.cleanup_metrics:
                        processing_metrics.setdefault("periodic_denoise",[]).append(dict(frame_uid=frame,**scene.cleanup_metrics))
                    processing_metrics["scene_frame_uids"].append(frame)
                    if geometry_worker is None:
                        try:result,seconds,receipt=integrate_geometry(frame,image,aligned,mask,k,t,meta["raw_signature"])
                        except BaseException as error:
                            error._graph_branch="geometry";error._graph_frame_uid=frame
                            raise
                        results[frame]=result
                        processing_metrics["geometry_seconds"]+=seconds
                        processing_metrics["geometry_frame_uids"].append(frame)
                while geometry_jobs:collect_geometry()
                if processing_metrics["geometry_frame_uids"]!=processing_metrics["scene_frame_uids"]:
                    raise IntegrityError("Geometry and object branches consumed different observations")
            except BaseException as primary:
                # A Future's exception is not raised by executor.shutdown.
                # Cancel unused queued work, join every submitted task, and
                # retain both branches' failures without replacing the primary.
                from concurrent.futures import CancelledError
                failures=[]
                def failure_record(branch,frame,error):
                    return dict(branch=branch,frame_uid=frame,error_type=type(error).__name__,message=str(error),
                        status="cancelled" if isinstance(error,CancelledError) else "failed")
                failures.append(failure_record(getattr(primary,"_graph_branch","input_or_join"),
                    getattr(primary,"_graph_frame_uid",locals().get("frame")),primary))
                for failed_frame,future in submitted_jobs:
                    if not future.done():future.cancel()
                for failed_frame,future in submitted_jobs:
                    try:future.result()
                    except BaseException as secondary:
                        if secondary is not primary:
                            failures.append(failure_record("geometry",failed_frame,secondary))
                self.last_branch_failures=tuple(failures);self.prepared=None
                try:self.store._append("errors.jsonl",dict(kind="mapping_branch_failures",failures=failures))
                except BaseException as log_error:
                    primary._graph_failure_log_error=str(log_error)
                raise
            if replay_backing is not None:
                replay_storage = replay_backing.promote(geometry.records.values())
                geometry.backing = self.store
        scene_state,entities,aliases=scene.snapshot(self.store,version)
        if rebuild_needed and self.graph is not None:
            old=[x for x in self.graph["entities"]if x["epoch"]==self.epoch]
            transitions=cross_revision_entities(old,entities)
            # Earlier transitions already belong to immutable ancestors. Keep
            # only this epoch's transition stubs in CURRENT;do not recopy the
            # whole history (and every historical view membership) each frame.
            old_rows={ (x["epoch"],x["id"]):dict(x,attributes=None,pose_map_version=None,
                           members=[],view_uids=[],source_revision=derivation_source or self.pointer["snapshot_id"],
                           status="historical"if x["status"]=="active"else x["status"])
                       for x in old }
            for relation in transitions:
                old_rows[(relation["epoch"],relation["src"])]["status"]=relation["status"]
            entities=list(old_rows.values())+entities
            aliases=aliases+transitions
        elif self.graph is not None:
            entities=[x for x in self.graph["entities"]if x["epoch"]!=epoch]+entities
            aliases=[x for x in self.graph["aliases"]if x["epoch"]!=epoch]+aliases
        # Collapse only identical alias keys; correspondence never follows equal native numbers.
        aliases=list({(x["epoch"],x["src"]):x for x in aliases}.values())
        views={};edges=list(self.graph["edges"])if self.graph is not None else[];previous=None
        vsm=VSMGraph(room_labeler=self.models.room_labeler if self.models else None)
        for meta in sorted(frames.values(),key=lambda x:x["capture_seq"]):
            frame=meta["frame_uid"];pose=corrected[frame]
            old_view=self.graph["views"].get(frame)if self.graph is not None else None
            det=old_view["detection_record"]if old_view is not None else(self.camera.record(frame)if frame in self.camera else None)
            views[frame]=dict(frame_uid=frame,capture_seq=meta["capture_seq"],env_step=meta["env_step"],
                source_event_seq=meta["event_seq"],sensor_timestamp_ns=meta["sensor_timestamp_ns"],
                position_G=np.asarray(pose["T_G_cv"])[:3,3].tolist()if pose else None,
                T_G_cv=pose["T_G_cv"]if pose else None,T_G_base=pose["T_G_base"]if pose else None,pose_binding=pose["binding"]if pose else None,
                pose_map_version=version if pose else None,geometry_status="available"if pose else"visual_only",
                geometry_fused=bool(results[frame].get("has_evidence")),
                detection_record=det,perception_complete=bool(det and det["metadata"].get("has_full_clip")),
                room_type_hint=det["metadata"].get("room_hint")if det else None,floor_id=None)
            if continuous:
                if old_view is not None:
                    views[frame]["source_radius_m"] = old_view.get("source_radius_m")
                elif meta["K"] is not None and meta["files"]["depth"] is not None:
                    source_depth = self._depth(meta)
                    views[frame]["source_radius_m"] = (self.source_radius(
                        source_depth["aligned_depth"], source_depth["valid_mask"], meta["K"])
                        if "aligned_depth" in source_depth and "valid_mask" in source_depth else None)
                else:
                    views[frame]["source_radius_m"] = None
            if pose is not None:vsm.add_visited_view(meta["capture_seq"],np.asarray(pose["T_G_cv"])[:3,3],frame)
            if det is not None and det["metadata"].get("room_hint")is not None:
                vsm._room_cache[("anchor",frame)]=det["metadata"]["room_hint"]
            if previous is not None and frame not in self.frames:
                relation=execution_relation(previous,meta);edges.append(relation["temporal"])
                if relation["traversed"]is not None:edges.append(relation["traversed"])
                execution=dict(pre=previous["frame_uid"],post=frame,macro=meta["action"].get("macro_id"),
                    primitive=meta["action"].get("primitive_index"),action=meta["action"],motion=relation)
                self.store.add_execution(execution)
            previous=meta
        vsm.sync_anchor_views(scene,lambda frame:np.asarray(corrected[frame]["T_G_cv"]))
        tiles={geometry.identifier(key):dict(pose_map_version=version,record=record)for key,record in geometry.records.items()}
        contributions=[]
        for key,record in geometry.records.items():
            for frame in record["meta"]["frames"]:
                contributions.append(dict(frame_uid=frame,tile_id=geometry.identifier(key),pose_binding=corrected[frame]["binding"]))
        graph=dict(episode_uid=self.store.episode_uid,versions=dict(pose_map_version=version),
            correction=dict(pose_revision_changed=changed,strategy="full_rebuild"if full_rebuild else"exact_unchanged_history_reuse"if reuse else"append",
                replayed_frames=len(replay),historical_frames_compared=historical_frames_compared,
                first_changed_frame=first_changed_frame),
            model_identity=self.model_identity,pose_bindings=target,views=views,entities=entities,
            aliases=aliases,edges=edges,tiles=tiles,contributions=contributions,
            geometry_state=geometry.export(),scene_state=scene_state,geometry_results=results,
            vsm=dict(visited=[dict(id=x.id,image_key=x.image_key,position=x.position.tolist())for x in vsm.visited],
                anchors={k:dict(position=n.position.tolist(),room_type_hint=n.room,objects=n.objects)for k,n in vsm.anchors.items()},
                visibility_edges=vsm.visibility_edges(),room_type_index=vsm.room_type_index()),
            scope="estimated3D_memory,height_slice_only,noFloorConfirmation,noNavigation")
        if capture['pose_record'].get('source')=='simulator_ground_truth':graph['pose_provider']='simulator_ground_truth'
        if continuous:
            graph["mapping_state"] = dict(mode="continuous_then_explicit_correction",
                chart=proposed_chart.to_record() if proposed_chart is not None else None,
                latest_native_map_version=mapping_sample.native_map_version if mapping_sample is not None else capture["pose_record"].get("map_version"),
                spatial_source="accepted_chart",correction_applied=apply_mapping_correction)
        self.prepared=dict(graph=graph,scene=scene,geometry=geometry,frames=frames,bindings=target,
            base_snapshot_id=base_snapshot_id,
            mapping_chart=proposed_chart,mapping_sample=mapping_sample,apply_mapping_correction=apply_mapping_correction,
            version=version,epoch=epoch,archive=archive,cutoff=cutoff,frame_uid=uid)
        return dict(duplicate=False,frame_uid=uid,target_pose_map_version=version,
            candidate_hash=hashlib.sha256(canonical(graph)).hexdigest(),rebuild=full_rebuild,correction_strategy=graph["correction"]["strategy"],replayed_frames=len(replay),replay_storage=replay_storage,object_reuse=dict(scene.copy_metrics),processing_metrics=processing_metrics)

    def publish_prepared(self,*,frame_uid,target_pose_map_version,version_check=None,fault=None):
        value=self.prepared
        if value is None or value["frame_uid"]!=frame_uid:raise IntegrityError("No matching prepared endpoint")
        if value["version"]!=target_pose_map_version:raise VersionUnavailable("Prepared target changed;rebuild latest")
        if version_check is not None and not version_check():
            self.store._append("updates.jsonl",dict(kind="rebuild_interrupted",frame_uid=frame_uid,
                target_pose_map_version=value["version"],reason="public target advanced before visibility commit"))
            self.prepared=None;raise VersionUnavailable("Target revision advanced before commit")
        if self.resource_limits:self.check_resources("before_current")
        previous=self.store.current
        try:
            pointer=self.store.publish(value["graph"],dict(pose_map_version=value["version"]),
                                       value["cutoff"],fault=fault,expected_parent_id=value["base_snapshot_id"])
        except BaseException as publication_error:
            actual=self.store._pointer()
            self.prepared=None
            if actual!=previous or actual!=self.pointer:
                # Another accepted base or this publication already linearized: recover its committed state,never
                # roll it back or apply the same frame again on old mutable data.
                self.store.current=actual;self._reload()
            try:self._reconcile_tail_journal()
            except BaseException as binding_error:
                publication_error.journal_binding_error=repr(binding_error)
            raise
        if value.get("apply_mapping_correction") and self.mapping_chart is not None:
            sample = value["mapping_sample"]
            receipt = dict(committed=True,snapshot_id=pointer["snapshot_id"],
                episode_id=sample.episode_id,episode_instance=sample.episode_instance,
                frame_id=sample.frame_id,timestamp_ns=sample.timestamp_ns,
                target_map_version=value["version"],bindings_sha256=sample.binding_digest)
            self.mapping_chart = self.mapping_chart.after_committed_correction(sample,receipt)
        else:
            self.mapping_chart = value.get("mapping_chart")
        self.scene=value["scene"];self.geometry=value["geometry"];self.frames=value["frames"]
        self.bindings=value["bindings"];self.version=value["version"];self.epoch=value["epoch"]
        self.archive=value["archive"];self.graph=value["graph"];self.pointer=pointer;self.prepared=None
        self._reconcile_tail_journal()
        return pointer

    def ingest(self,*args,**kwargs):
        ready=self.prepare_endpoint(*args,**kwargs)
        if ready["duplicate"]:return ready
        pointer=self.publish_prepared(frame_uid=ready["frame_uid"],target_pose_map_version=ready["target_pose_map_version"])
        return dict(ready,snapshot_id=pointer["snapshot_id"])
