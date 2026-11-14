# Adapted from pinned EvoMemNav5770e8cc and ConceptGraphs, MIT License.
# Upstream copyrights retained in vendor_sources/EvoMemNav. No simulator or policy loop.
import copy
import logging
import os
import hashlib
from collections import Counter
from typing import Dict, List, Optional, Tuple
import numpy as np
import supervision as sv
import torch
from .reusable_clustering import ReusableSceneClustering
from evomemnav.memory.views import ViewRecord
from evomemnav.third_party.conceptgraph.slam.mapping import (
    aggregate_similarities,
    compute_spatial_similarities,
    compute_visual_similarities,
    match_detections_to_objects,
)
from evomemnav.third_party.conceptgraph.slam.slam_classes import DetectionDict, MapObjectDict, to_tensor
from evomemnav.third_party.conceptgraph.slam.utils import (
    denoise_objects,
    detections_to_obj_pcd_and_bbox,
    filter_gobs,
    filter_objects,
    get_bounding_box,
    init_process_pcd,
    merge_obj2_into_obj1,
    merge_objects,
    processing_needed,
    resize_gobs,
)
from evomemnav.third_party.conceptgraph.utils.general_utils import ObjectClasses, filter_detections, measure_time
from evomemnav.third_party.conceptgraph.utils.ious import mask_subtract_contained
from evomemnav.third_party.conceptgraph.utils.model_utils import compute_clip_features_batched
import open3d as o3d
from pathlib import Path
from contextvars import ContextVar
from PIL import Image
from evomemnav.third_party.conceptgraph.slam import utils as cg_utils


class RealPerceptionModels:
    """Original three-model pipeline and its original YOLO text encoder, offline."""
    def __init__(self,root,device="cuda:0"):
        import open_clip,clip
        from ultralytics import YOLOWorld,SAM
        self.root=Path(root);self.device=torch.device(device)
        assets=self.root/"models/graph001"
        self.text_encoder,_=clip.load(str(assets/"ViT-B-32.pt"),device=device)
        self.detection_model=YOLOWorld(str(assets/"yolov8x-world.pt"))
        self.detection_model.model.clip_model=self.text_encoder
        self.sam_predictor=SAM(str(assets/"sam_l.pt"))
        self.clip_model,_,self.clip_preprocess=open_clip.create_model_and_transforms(
            "ViT-B-32","laion2b_s34b_b79k",cache_dir=str(self.root/"runtime/graph_memory/model-cache/hf"))
        self.clip_model=self.clip_model.to(device).eval()
        self.clip_tokenizer=open_clip.get_tokenizer("ViT-B-32")
        from omegaconf import OmegaConf
        from ..storage.store import ByteLRU
        source_cfg=OmegaConf.load(self.root/"vendor_sources/EvoMemNav/cfg/evomemnav_goatbench.yaml")
        self.room_labeler=RoomLabeler(self.clip_model,self.clip_preprocess,self.clip_tokenizer,
            source_cfg.vsmgraph.room_vocab,source_cfg.observation.vlm_image_size)
        self.image_features=ByteLRU(128*1024*1024)
        import importlib.metadata,inspect
        from ..storage.store import file_hash,canonical,digest
        transforms=self.clip_preprocess.transforms
        import ultralytics.data.loaders,ultralytics.engine.predictor,ultralytics.models.sam.predict
        descriptor=dict(ultralytics_input="PIL_RGB_uint8;raw_grid_unchanged",
            ultralytics=importlib.metadata.version("ultralytics"),
            detector_loader_sha256=file_hash(Path(inspect.getsourcefile(ultralytics.data.loaders.LoadPilAndNumpy))),
            detector_preprocess_sha256=file_hash(Path(inspect.getsourcefile(ultralytics.engine.predictor.BasePredictor))),
            sam_preprocess_sha256=file_hash(Path(inspect.getsourcefile(ultralytics.models.sam.predict.Predictor))),
            source_scene_config_sha256=file_hash(self.root/"vendor_sources/EvoMemNav/cfg/evomemnav_goatbench.yaml"),
            source_cg_config_sha256=file_hash(self.root/"vendor_sources/EvoMemNav/cfg/concept_graph.yaml"),
            resize_size=transforms[0].size,interpolation=str(transforms[0].interpolation),
            antialias=transforms[0].antialias,crop_size=list(transforms[1].size),
            mean=list(transforms[-1].mean),std=list(transforms[-1].std),
            openclip=importlib.metadata.version("open-clip-torch"),
            torchvision=importlib.metadata.version("torchvision"),
            rgb_converter_sha256=file_hash(Path(inspect.getsourcefile(transforms[2]))),
            output_normalization="L2plus1e-6")
        self.preprocess_hash=digest(canonical(descriptor))
        self.clip_model_hash=file_hash(assets/"open_clip_pytorch_model.bin")

    def full_image_clip(self,image):
        import hashlib
        from ..storage.store import freeze
        key=hashlib.sha256((self.clip_model_hash+"|"+self.preprocess_hash+"|"+str(image.shape)).encode()
                           +np.ascontiguousarray(image).tobytes()).hexdigest()
        def compute():
            with torch.inference_mode():
                value=self.clip_model.encode_image(self.clip_preprocess(Image.fromarray(image)).unsqueeze(0).to(self.device))
                value=value/(value.norm(dim=-1,keepdim=True)+1e-6)
            return freeze(value[0].cpu().numpy())
        return self.image_features.get(key,compute)

_ACTIVE_SCENE=ContextVar("graph001_active_scene",default=None)
_ORIGINAL_MERGE=cg_utils.merge_obj2_into_obj1
def merge_obj2_into_obj1(*args,**kwargs):
    a=kwargs.get("obj1",args[0]if args else None)
    b=kwargs.get("obj2",args[1]if len(args)>1 else None)
    src,dst=int(b["id"]),int(a["id"])
    scene=_ACTIVE_SCENE.get()
    if scene is not None:scene._own_merge_cloud(a)
    result=_ORIGINAL_MERGE(*args,**kwargs)
    if scene is not None:scene.on_merge(src,dst)
    return result
# Original cleanup helpers resolve this global at call-time; no source algorithm changes.
cg_utils.merge_obj2_into_obj1=merge_obj2_into_obj1

def resize_image(image,target_h,target_w):
    return np.asarray(Image.fromarray(image).resize((target_w,target_h)))

def separate_same_frame_claims(match_indices, detections, existing, scores, masks):
    """Keep conflicting, disjoint proposals from the same frame distinct at association time."""
    claims = {}
    for source, target in match_indices:
        if target is not None:
            claims.setdefault(target, []).append(source)
    row = {oid: i for i,oid in enumerate(detections)}
    col = {oid: i for i,oid in enumerate(existing)}
    rejected = set()
    for target, sources in claims.items():
        if len(sources)<2 or len({detections[s]["class_name"] for s in sources})==1:
            continue
        if not any(detections[s]["class_name"]==existing[target]["class_name"] for s in sources):
            # Conflicting observations cannot determine which one should inherit this ID.
            for i,first in enumerate(sources):
                for second in sources[i+1:]:
                    if (detections[first]["class_name"]!=detections[second]["class_name"]
                            and not np.any(masks[first] & masks[second])):
                        rejected.update((first,second))
            sources=[s for s in sources if s not in rejected]
        def priority(source):
            return (detections[source]["class_name"]==existing[target]["class_name"],
                    float(scores[row[source],col[target]]),-row[source])
        kept=[]
        for source in sorted(sources,key=priority,reverse=True):
            if any(detections[source]["class_name"]!=detections[other]["class_name"]
                   and not np.any(masks[source] & masks[other]) for other in kept):
                rejected.add(source)
            else:
                kept.append(source)
    return [(s,None if s in rejected else t) for s,t in match_indices]


class MemoryOnlyScene:
    """Source object/anchor algorithms with explicit archive ownership and merge notices."""
    def __init__(self,cfg,cg_cfg,*,models,camera_cache,observations,epoch,cache_only=False,clustering_cache=None):
        self.cfg=cfg;self.cfg_cg=cg_cfg;self.epoch=str(epoch)
        self.device=models.device if models is not None else torch.device("cpu")
        if models is None and not cache_only:raise RuntimeError("Actual perception models are required")
        self.cache_only=cache_only;self.camera_cache=camera_cache;self.observations=observations
        self.obj_classes=ObjectClasses(classes_file_path=cfg.data.object_classes_path,bg_classes=cg_cfg["bg_classes"])
        self.objects=MapObjectDict();self.object_id_counter=1;self.views={};self.anchor_views={}
        self.clustering=ReusableSceneClustering(min_sample_split=0,random_state=66,split_cache=clustering_cache)
        self.models=models
        if models is not None:
            self.detection_model=models.detection_model
            import hashlib,json
            vocabulary=hashlib.sha256(json.dumps(self.obj_classes.get_classes_arr(),ensure_ascii=False).encode()).hexdigest()
            if getattr(models,"class_vocabulary_hash",None)is None:
                self.detection_model.set_classes(self.obj_classes.get_classes_arr())
                models.class_vocabulary_hash=vocabulary
            elif models.class_vocabulary_hash!=vocabulary:
                raise RuntimeError("A worker cannot silently change its frozen detector vocabulary")
            self.sam_predictor=models.sam_predictor;self.clip_model=models.clip_model
            self.clip_preprocess=models.clip_preprocess;self.clip_tokenizer=models.clip_tokenizer
        self.members={};self.history={};self.aliases={};self.retired=set();self.view_poses={}
        self._frame_key=None;self._visible_detection_indices=[]
        self.model_frames=0;self.replay_frames=0
        self._shared_pointclouds={}
        self._geometry_snapshots={}
        from .denoise_reuse import KeepAllClouds
        self.keep_all_clouds=KeepAllClouds()
        self.denoise_cache_bytes=0
        self.cleanup_metrics={}
        self.copy_metrics=dict(shared_clouds=0,cloned_clouds=0,blob_hits=0,blob_misses=0)

    def close(self):
        # Resource lifetime belongs to the worker, not an environment/simulator.
        self.objects.clear();self.views.clear();self.anchor_views.clear()
        self._shared_pointclouds.clear()
        self._geometry_snapshots.clear()
        self.keep_all_clouds.entries.clear();self.keep_all_clouds.bytes=0

    def _own_merge_cloud(self,obj):
        shared = self._shared_pointclouds.pop(int(obj["id"]),None)
        if shared is not None and obj["pcd"] is shared:
            obj["pcd"] = copy.deepcopy(shared)
            self.copy_metrics["cloned_clouds"] += 1

    def fork(self,*,copy_on_write=False):
        result=copy.copy(self)
        result.keep_all_clouds=self.keep_all_clouds.fork()
        result.cleanup_metrics={}
        data=copy.deepcopy(dict(views=self.views,anchors=self.anchor_views,
            members=self.members,history=self.history,aliases=self.aliases,retired=self.retired,
            poses=self.view_poses,clustering=self.clustering))
        if copy_on_write:
            # Object dictionaries and class histories are private; immutable
            # geometry stays shared until the original merge mutates its target.
            result.objects=MapObjectDict({oid:dict(obj,class_id=list(obj["class_id"]))
                                         for oid,obj in self.objects.items()})
            result._shared_pointclouds={oid:obj["pcd"]for oid,obj in result.objects.items()}
            result.copy_metrics=dict(shared_clouds=len(result.objects),cloned_clouds=0,blob_hits=0,blob_misses=0)
        else:
            result.objects=copy.deepcopy(self.objects)
            result._shared_pointclouds={}
            result.copy_metrics=dict(shared_clouds=0,cloned_clouds=len(result.objects),blob_hits=0,blob_misses=0)
        result._geometry_snapshots=self._geometry_snapshots.copy()
        result.views=data["views"];result.anchor_views=data["anchors"]
        result.members=data["members"];result.history=data["history"];result.aliases=data["aliases"]
        result.retired=data["retired"];result.view_poses=data["poses"];result.clustering=data["clustering"]
        return result

    def _empty_camera(self,image_rgb):
        h,w=image_rgb.shape[:2]
        return dict(xyxy=np.empty((0,4),np.float32),confidence=np.empty(0,np.float32),
            class_id=np.empty(0,np.int64),mask=np.empty((0,h,w),bool),
            image_feats=np.empty((0,512),np.float32),local_points=[],local_colors=[])

    def _local_payload(self,gobs,depth,intrinsics,image_rgb):
        n=len(gobs["mask"])
        payload={name:np.array(gobs[name],copy=True)for name in ("xyxy","confidence","class_id","mask","image_feats")}
        payload["mask"]=payload["mask"].astype(bool)
        payload["local_points"]=[np.empty((0,3),np.float32)for _ in range(n)]
        payload["local_colors"]=[np.empty((0,3),np.float32)for _ in range(n)]
        if depth is None or intrinsics is None:return payload
        d=torch.from_numpy(np.array(depth,copy=True)).to(self.device).float()
        masks=torch.from_numpy(payload["mask"]).to(self.device).float()
        k=torch.from_numpy(np.array(intrinsics,copy=True)).to(self.device).float()
        rgb=torch.from_numpy(image_rgb).to(self.device).float()/255.
        points,colors=cg_utils.batch_mask_depth_to_points_colors(d,masks,k,rgb,self.device)
        for index in range(n):
            valid=points[index,:,:,2]<0
            if int(valid.sum())<self.cfg_cg.min_points_threshold:continue
            local,colour=cg_utils.dynamic_downsample(points[index][valid],colors[index][valid],
                                                    target=self.cfg_cg.obj_pcd_max_points)
            payload["local_points"][index]=local.cpu().numpy().copy()
            payload["local_colors"][index]=colour.cpu().numpy().copy()
        return payload

    def _world_gobs(self,payload,image_rgb,cam_pos):
        n=len(payload["mask"])
        gobs={name:np.array(payload[name],copy=True)for name in ("xyxy","confidence","class_id","mask","image_feats")}
        gobs["classes"]=self.obj_classes.get_classes_arr();gobs["text_feats"]=[]
        gobs["image_crops"]=[Image.fromarray(image_rgb).crop(tuple(b))for b in gobs["xyxy"]]
        gobs["detection_class_labels"]=[self.obj_classes.get_classes_arr()[int(x)]for x in gobs["class_id"]]
        objects=[None]*n
        pose=torch.tensor(cam_pos,device=self.device,dtype=torch.float)
        for index,(points,colors)in enumerate(zip(payload["local_points"],payload["local_colors"])):
            if len(points)<self.cfg_cg.min_points_threshold:continue
            p=torch.tensor(points,device=self.device,dtype=torch.float)
            p=pose@torch.cat((p,torch.ones_like(p[:,:1])),dim=1).T
            p=p[:3].T.cpu().numpy()
            pcd=o3d.geometry.PointCloud();pcd.points=o3d.utility.Vector3dVector(p)
            pcd.colors=o3d.utility.Vector3dVector(np.array(colors,copy=True))
            bbox=get_bounding_box(self.cfg_cg.spatial_sim_type,pcd)
            if bbox.volume()<1e-6:continue
            pcd=init_process_pcd(pcd=pcd,downsample_voxel_size=self.cfg_cg.downsample_voxel_size,
                dbscan_remove_noise=self.cfg_cg.dbscan_remove_noise,dbscan_eps=self.cfg_cg.dbscan_eps,
                dbscan_min_points=self.cfg_cg.dbscan_min_points)
            objects[index]=dict(pcd=pcd,bbox=get_bounding_box(self.cfg_cg.spatial_sim_type,pcd))
        gobs["pcd"]=[x["pcd"]if x is not None else None for x in objects]
        gobs["bbox"]=[x["bbox"]if x is not None else None for x in objects]
        return gobs

    def prepare_camera(self,image_rgb,depth,intrinsics,frame_key):
        if frame_key in self.camera_cache:
            self.replay_frames+=1;return self.camera_cache[frame_key]
        if self.cache_only:raise RuntimeError("No cached real or explicit CPU fixture detections for frame")
        payload=self._detect_camera(image_rgb,depth,intrinsics)
        payload["full_clip"]=self.models.full_image_clip(image_rgb)
        payload["room_hint"]=self.models.room_labeler(image_rgb)
        self.camera_cache[frame_key]=payload;self.model_frames+=1
        return payload

    def _prepared_gobs(self,image_rgb,depth,intrinsics,cam_pos,frame_key):
        payload=self.prepare_camera(image_rgb,depth,intrinsics,frame_key)
        if not len(payload["mask"]):return None
        self._frame_key=frame_key
        self._frame_detection_indices=list(range(len(payload["mask"])))
        self.view_poses[frame_key]=np.asarray(cam_pos)@np.diag([1.,-1.,-1.,1.])
        return self._world_gobs(payload,image_rgb,cam_pos)

    def _register_detection(self,native_id,index,class_name):
        member=self._frame_key+":d"+format(index,"05d")
        self.members[native_id]={member}
        self.history[native_id]=dict(status="active",class_name=class_name,members={member})

    def resolve(self,native_id):
        seen=set()
        while native_id in self.aliases:
            if native_id in seen:raise RuntimeError("Alias cycle")
            seen.add(native_id);native_id=self.aliases[native_id]
        return None if native_id in self.retired else native_id

    def on_merge(self,src,dst):
        if src==dst:raise RuntimeError("Self merge is invalid")
        dst=self.resolve(dst)
        if dst is None:raise RuntimeError("Merge target retired")
        self.aliases[src]=dst
        self._shared_pointclouds.pop(src,None)
        self._geometry_snapshots.pop(src,None)
        self.members.setdefault(dst,set()).update(self.members.pop(src,set()))
        self.history.setdefault(src,dict(members=set(),class_name="unknown")).update(status="alias",dst=dst)
        self.history.setdefault(dst,dict(class_name="unknown",status="active")).update(members=self.members[dst].copy())
        for view in list(self.views.values())+list(self.anchor_views.values()):
            if src in view.full_obj_list:
                confidence=view.full_obj_list.pop(src)
                view.full_obj_list[dst]=max(confidence,view.full_obj_list.get(dst,0.))
            view.cluster=list(dict.fromkeys(dst if x==src else x for x in view.cluster))
            if view.visual_prompt is not None:
                ids=view.visual_prompt.data.get("obj_id",[])
                view.visual_prompt.data["obj_id"]=[dst if x==src else x for x in ids]

    def on_retire(self,native_id):
        if native_id in self.aliases:return
        self.retired.add(native_id)
        self._shared_pointclouds.pop(native_id,None)
        self._geometry_snapshots.pop(native_id,None)
        self.history.setdefault(native_id,dict(members=set(),class_name="unknown")).update(status="retired")
        for view in list(self.views.values())+list(self.anchor_views.values()):
            view.full_obj_list.pop(native_id,None)
            view.cluster=[x for x in view.cluster if x!=native_id]
            if view.visual_prompt is not None:
                ids=view.visual_prompt.data.get("obj_id",[])
                view.visual_prompt.data["obj_id"]=[self.resolve(x)for x in ids]

    def periodic_cleanup_objects(self,frame_idx,pts):
        self.cleanup_metrics={}
        before=set(self.objects)
        token=_ACTIVE_SCENE.set(self)
        try:self._source_cleanup(frame_idx,pts)
        finally:_ACTIVE_SCENE.reset(token)
        for oid in before-set(self.objects):self.on_retire(oid)
        self._shared_pointclouds = {
            oid: cloud for oid, cloud in self._shared_pointclouds.items()
            if oid in self.objects and self.objects[oid]["pcd"] is cloud}
        self.repair_references()

    def repair_references(self):
        active=set(self.objects)
        for view in list(self.views.values())+list(self.anchor_views.values()):
            full={}
            for oid,conf in view.full_obj_list.items():
                resolved=self.resolve(oid)
                if resolved in active:full[resolved]=max(conf,full.get(resolved,0))
            view.full_obj_list=full
            view.cluster=list(dict.fromkeys(x for x in (self.resolve(o)for o in view.cluster)if x in active))
            if view.visual_prompt is not None:
                view.visual_prompt.data["obj_id"]=[self.resolve(o)for o in view.visual_prompt.data.get("obj_id",[])]
        self.anchor_views={k:v for k,v in self.anchor_views.items()if v.cluster}
        for oid,obj in self.objects.items():
            if obj.get("image")not in self.anchor_views:obj["image"]=None

    def fuse(self,image_rgb,depth,K_up,T_G_up,base_position_G,global_voxel_index,frame_key,*,frame_idx):
        token=_ACTIVE_SCENE.set(self)
        try:
            result=self.update_objects(image_rgb,depth,K_up,T_G_up,base_position_G,global_voxel_index,frame_key)
            self.periodic_cleanup_objects(frame_idx,base_position_G)
            near=self.cfg.perception.object_visibility_dist_m+.5
            ids={oid for oid in result[1]if oid in self.objects}
            ids|={oid for oid,obj in self.objects.items()if np.linalg.norm(obj["bbox"].center[[0,2]]-base_position_G[[0,2]])<near}
            self.update_anchor_views(ids,min_detection=self.cfg.perception.min_detection)
            self.repair_references()
            return result
        finally:_ACTIVE_SCENE.reset(token)

    def snapshot(self,store,pose_map_version):
        from ..storage.store import _verify_ref
        self._geometry_snapshots = {oid: value for oid, value in self._geometry_snapshots.items()
                                    if oid in self.objects}
        objects=[]
        for oid,obj in self.objects.items():
            pcd=obj["pcd"];bbox=obj["bbox"]
            if isinstance(bbox,o3d.geometry.OrientedBoundingBox):
                bounds=dict(kind="obb",center=np.asarray(bbox.center).tolist(),
                    rotation=np.asarray(bbox.R).tolist(),extent=np.asarray(bbox.extent).tolist())
            else:
                bounds=dict(kind="aabb",minimum=np.asarray(bbox.min_bound).tolist(),
                    maximum=np.asarray(bbox.max_bound).tolist())
            arrays=dict(points=np.asarray(pcd.points),colors=np.asarray(pcd.colors),
                        clip_ft=obj["clip_ft"].detach().cpu().numpy())
            signature=tuple((name,value.dtype.str,value.shape,
                             hashlib.sha256(np.ascontiguousarray(value).tobytes()).digest())
                            for name,value in sorted(arrays.items()))
            cached=self._geometry_snapshots.get(oid)
            if cached is not None and cached[0]==str(store.root) and cached[1]==signature:
                _verify_ref(store.root,cached[2])
                blob=copy.deepcopy(cached[2])
                self.copy_metrics["blob_hits"]+=1
            else:
                blob=store.put_arrays(arrays)
                self._geometry_snapshots[oid]=(str(store.root),signature,copy.deepcopy(blob))
                self.copy_metrics["blob_misses"]+=1
            objects.append(dict(id=int(oid),class_name=obj["class_name"],class_id=[int(x)for x in obj["class_id"]],
                num_detections=int(obj["num_detections"]),conf=float(obj["conf"]),image=obj.get("image"),
                bbox=bounds,geometry_blob=blob))
        def view_state(view):
            prompt=view.visual_prompt
            return dict(image=view.image,color=list(view.color),obs_point=np.asarray(view.obs_point).tolist(),
                full_obj_list={str(k):float(v)for k,v in view.full_obj_list.items()},cluster=list(view.cluster),
                position=None if view.position is None else np.asarray(view.position).tolist(),
                prompt=None if prompt is None else dict(xyxy=prompt.xyxy.tolist(),
                    class_id=None if prompt.class_id is None else prompt.class_id.tolist(),
                    obj_id=list(prompt.data.get("obj_id",[]))))
        history={str(k):dict(v,members=sorted(v["members"]))for k,v in self.history.items()}
        state=dict(schema_version=1,epoch=self.epoch,object_id_counter=self.object_id_counter,
            objects=objects,views={k:view_state(v)for k,v in self.views.items()},
            anchor_keys=list(self.anchor_views),members={str(k):sorted(v)for k,v in self.members.items()},
            history=history,aliases={str(k):v for k,v in self.aliases.items()},retired=sorted(self.retired),
            view_poses={k:np.asarray(v).tolist()for k,v in self.view_poses.items()})
        active={x["id"]:x for x in objects};entities=[];aliases=[]
        for oid,record in self.history.items():
            native=active.get(oid)
            entity = dict(epoch=self.epoch,id=oid,status=record["status"],class_name=record["class_name"],
                members=sorted(record["members"]),view_uids=sorted({x.rsplit(":d",1)[0]for x in record["members"]}),
                pose_map_version=pose_map_version if native is not None else None,
                attributes=native)
            if record["status"] == "active" and native is not None:
                entity["historical_class_name"] = record["class_name"]
                entity["class_name"] = native["class_name"]
            entities.append(entity)
            if oid in self.aliases:
                aliases.append(dict(epoch=self.epoch,src=oid,dst_epoch=self.epoch,
                    dst=self.resolve(oid),status="alias"if self.resolve(oid)is not None else"retired"))
        return state,entities,aliases

    @classmethod
    def restore(cls,cfg,cg_cfg,*,models,camera_cache,observations,state,store,cache_only=False):
        if state["schema_version"]!=1:raise ValueError("Scene state schema mismatch")
        result=cls(cfg,cg_cfg,models=models,camera_cache=camera_cache,observations=observations,
                   epoch=state["epoch"],cache_only=cache_only)
        result.object_id_counter=state["object_id_counter"]
        for item in state["objects"]:
            arrays=store.get_arrays(item["geometry_blob"]);pcd=o3d.geometry.PointCloud()
            pcd.points=o3d.utility.Vector3dVector(np.array(arrays["points"],copy=True))
            pcd.colors=o3d.utility.Vector3dVector(np.array(arrays["colors"],copy=True))
            b=item["bbox"]
            bbox=(o3d.geometry.OrientedBoundingBox(np.asarray(b["center"]),np.asarray(b["rotation"]),np.asarray(b["extent"]))
                if b["kind"]=="obb"else o3d.geometry.AxisAlignedBoundingBox(np.asarray(b["minimum"]),np.asarray(b["maximum"])))
            result.objects[item["id"]]=dict(id=item["id"],class_name=item["class_name"],class_id=item["class_id"],
                num_detections=item["num_detections"],conf=item["conf"],image=item["image"],pcd=pcd,bbox=bbox,
                clip_ft=torch.tensor(np.array(arrays["clip_ft"],copy=True)))
        for key,v in state["views"].items():
            prompt=v["prompt"]
            detection=None
            if prompt is not None:
                detection=sv.Detections(xyxy=np.asarray(prompt["xyxy"],np.float32).reshape(-1,4),
                    class_id=None if prompt["class_id"]is None else np.asarray(prompt["class_id"],int))
                detection.data["obj_id"]=prompt["obj_id"]
            result.views[key]=ViewRecord(image=v["image"],color=tuple(v["color"]),obs_point=np.asarray(v["obs_point"]),
                full_obj_list={int(k):x for k,x in v["full_obj_list"].items()},cluster=list(v["cluster"]),
                position=None if v["position"]is None else np.asarray(v["position"]),visual_prompt=detection)
        result.anchor_views={k:result.views[k]for k in state["anchor_keys"]}
        result.members={int(k):set(v)for k,v in state["members"].items()}
        result.history={int(k):dict(v,members=set(v["members"]))for k,v in state["history"].items()}
        result.aliases={int(k):v for k,v in state["aliases"].items()};result.retired=set(state["retired"])
        result.view_poses={k:np.asarray(v)for k,v in state["view_poses"].items()}
        result.repair_references()
        return result

    def _detect_camera(self,image_rgb,depth,intrinsics):
        obj_classes = self.obj_classes

        results = self.detection_model.predict(Image.fromarray(image_rgb), conf=0.1, verbose=False)
        confidences = results[0].boxes.conf.cpu().numpy()
        detection_class_ids = results[0].boxes.cls.cpu().numpy().astype(int)
        detection_class_labels = [
            f"{obj_classes.get_classes_arr()[class_id]} {class_idx}"
            for class_idx, class_id in enumerate(detection_class_ids)
        ]
        xyxy_tensor = results[0].boxes.xyxy
        xyxy_np = xyxy_tensor.cpu().numpy().copy()

        if xyxy_tensor.numel() != 0:
            sam_out = self.sam_predictor.predict(Image.fromarray(image_rgb), bboxes=xyxy_tensor, verbose=False)
            masks_np = sam_out[0].masks.data.cpu().numpy()
        else:
            masks_np = np.empty((0, *image_rgb.shape[:2]), dtype=np.float64)

        # Keep separate observation evidence from the same detector/SAM invocation.
        # The source foreground filter deliberately removes ordinary doors.
        labels=obj_classes.get_classes_arr()
        door_indices=np.asarray([i for i,c in enumerate(detection_class_ids) if labels[c]=='door'],dtype=np.int32)
        door_data=dict(door_candidate_count=len(door_indices))
        if len(door_indices):
            door_data.update(door_proposal_indices=door_indices,door_xyxy=xyxy_np[door_indices].copy(),
                             door_confidence=confidences[door_indices].copy(),
                             door_mask_bits=np.packbits(masks_np[door_indices].astype(bool),axis=2,bitorder='little'))

        curr_det = sv.Detections(xyxy=xyxy_np, confidence=confidences, class_id=detection_class_ids, mask=masks_np)
        if len(curr_det) == 0:
            return dict(self._empty_camera(image_rgb),**door_data)

        # remove overlapping detections
        curr_det, _ = filter_detections(
            image=image_rgb,
            detections=curr_det,
            classes=obj_classes,
            given_labels=detection_class_labels,
            iou_threshold=self.cfg_cg.object_detection_iou_threshold,
            min_mask_size_ratio=self.cfg_cg.min_mask_size_ratio,
            confidence_threshold=self.cfg_cg.object_detection_confidence_threshold,
        )
        if curr_det is None:
            return dict(self._empty_camera(image_rgb),**door_data)

        image_crops, image_feats, text_feats = compute_clip_features_batched(
            image_rgb,
            curr_det,
            self.clip_model,
            self.clip_preprocess,
            self.clip_tokenizer,
            obj_classes.get_classes_arr(),
            self.device,
        )
        raw_gobs = {
            "xyxy": curr_det.xyxy,
            "confidence": curr_det.confidence,
            "class_id": curr_det.class_id,
            "mask": curr_det.mask,
            "classes": obj_classes.get_classes_arr(),
            "image_crops": image_crops,
            "image_feats": image_feats,
            "text_feats": text_feats,
            "detection_class_labels": detection_class_labels,
        }
        gobs = filter_gobs(
            resize_gobs(raw_gobs, image_rgb),
            image_rgb,
            skip_bg=self.cfg_cg.skip_bg,
            BG_CLASSES=obj_classes.get_bg_classes_arr(),
            mask_area_threshold=self.cfg_cg.mask_area_threshold,
            max_bbox_area_ratio=self.cfg_cg.max_bbox_area_ratio,
            mask_conf_threshold=self.cfg_cg.mask_conf_threshold,
        )
        if len(gobs["mask"]) == 0:
            return dict(self._empty_camera(image_rgb),**door_data)

        # keep e.g. pillows on couches as separate objects
        gobs["mask"] = mask_subtract_contained(gobs["xyxy"], gobs["mask"])

        return dict(self._local_payload(gobs,depth,intrinsics,image_rgb),**door_data)
    def update_objects(
        self,
        image_rgb: np.ndarray,
        depth: np.ndarray,
        intrinsics,
        cam_pos,
        pts,
        pts_voxel,
        img_path: str,
    ) -> Tuple[np.ndarray, List[int]]:
        """Detect, segment and merge the object instances of one observation.

        Returns the annotated image and the ids of the newly created instances.
        """
        obj_classes = self.obj_classes
        gobs = self._prepared_gobs(image_rgb,depth,intrinsics,cam_pos,img_path)
        if gobs is None:return image_rgb,[]
        # visible objects are limited to the visibility distance of the view
        gobs = self._filter_by_distance(pts, gobs)
        detection_list = self._make_detection_list(gobs, obj_classes)
        if len(detection_list) == 0:
            return image_rgb, []

        view = ViewRecord(
            image=img_path,
            # Display-only color is a pure frame-identity function. Source
            # random colors changed on identical rebuilds;association never
            # reads this field,so keep visualization stable without RNG state.
            color=tuple(x/255. for x in hashlib.sha256(img_path.encode()).digest()[:3]),
            obs_point=pts_voxel,
            full_obj_list={obj_id: detection_list[obj_id]["conf"] for obj_id in detection_list.keys()},
        )
        det_visual_prompt = sv.Detections(xyxy=gobs["xyxy"], class_id=gobs["class_id"])

        if len(self.objects) == 0:
            self.objects.update(detection_list)
            det_visual_prompt.data["obj_id"] = list(detection_list.keys())
            view.visual_prompt = det_visual_prompt
            self.views[img_path] = view
            return image_rgb, list(detection_list.keys())

        spatial_sim = compute_spatial_similarities(
            spatial_sim_type=self.cfg_cg["spatial_sim_type"],
            detection_list=detection_list,
            objects=self.objects,
            downsample_voxel_size=self.cfg_cg["downsample_voxel_size"],
        )
        visual_sim = compute_visual_similarities(detection_list, self.objects)
        agg_sim = aggregate_similarities(
            match_method=self.cfg_cg["match_method"],
            phys_bias=self.cfg_cg["phys_bias"],
            spatial_sim=spatial_sim,
            visual_sim=visual_sim,
        )
        match_indices = match_detections_to_objects(
            agg_sim=agg_sim,
            detection_threshold=self.cfg_cg["sim_threshold"],
            existing_obj_ids=list(self.objects.keys()),
            detected_obj_ids=list(detection_list.keys()),
        )
        if self.cfg_cg.get("separate_same_frame_claims",False):
            ids=list(detection_list)
            visible=[i for i,pcd in enumerate(gobs["pcd"]) if pcd is not None]
            masks={oid:gobs["mask"][i] for oid,i in zip(ids,visible)}
            match_indices=separate_same_frame_claims(match_indices,detection_list,self.objects,agg_sim,masks)
        captions, added_obj_ids, all_obj_ids = self._merge_matches(detection_list, match_indices, obj_classes, view)
        det_visual_prompt.data["obj_id"] = all_obj_ids
        view.visual_prompt = det_visual_prompt
        self.views[img_path] = view

        det_visualize = sv.Detections(xyxy=gobs["xyxy"], confidence=gobs["confidence"], class_id=gobs["class_id"])
        det_visualize.data["class_name"] = captions
        annotated = sv.BoundingBoxAnnotator(thickness=1).annotate(image_rgb.copy(), det_visualize)
        annotated = sv.LabelAnnotator(text_thickness=1, text_scale=0.25, text_color=sv.Color.BLACK).annotate(
            annotated, det_visualize
        )
        return annotated, added_obj_ids
    def _filter_by_distance(self, pts, gobs):
        keep = [
            idx
            for idx in range(len(gobs["bbox"]))
            if gobs["bbox"][idx] is not None
            and np.linalg.norm(gobs["bbox"][idx].center[[0, 2]] - pts[[0, 2]]) <= self.cfg.perception.object_visibility_dist_m
        ]
        self._visible_detection_indices=[self._frame_detection_indices[i]for i in keep]
        for attribute in gobs.keys():
            if isinstance(gobs[attribute], str) or attribute in ("classes", "labels", "edges", "text_feats", "captions"):
                continue
            if isinstance(gobs[attribute], list):
                gobs[attribute] = [gobs[attribute][i] for i in keep]
            elif isinstance(gobs[attribute], np.ndarray):
                gobs[attribute] = gobs[attribute][keep]
            else:
                raise NotImplementedError(f"Unhandled type {type(gobs[attribute])}")
        return gobs
    def _merge_matches(self, detection_list: DetectionDict, match_indices, obj_classes, view: ViewRecord):
        captions, all_obj_ids, added_obj_ids = [], [], []
        for detected_obj_id, existing_obj_id in match_indices:
            if existing_obj_id is None:
                self.objects[detected_obj_id] = detection_list[detected_obj_id]
                obj = self.objects[detected_obj_id]
                captions.append(f"{detected_obj_id} {obj['class_name']} {obj['conf']:.3f} N")
                all_obj_ids.append(detected_obj_id)
                added_obj_ids.append(detected_obj_id)
                continue
            detected_obj = detection_list[detected_obj_id]
            merged_obj = merge_obj2_into_obj1(
                obj1=self.objects[existing_obj_id],
                obj2=detected_obj,
                downsample_voxel_size=self.cfg_cg["downsample_voxel_size"],
                dbscan_remove_noise=self.cfg_cg["dbscan_remove_noise"],
                dbscan_eps=self.cfg_cg["dbscan_eps"],
                dbscan_min_points=self.cfg_cg["dbscan_min_points"],
                spatial_sim_type=self.cfg_cg["spatial_sim_type"],
                device=self.device,
                run_dbscan=False,
            )
            # the instance takes the most frequent category of its detections
            most_common_class_id = Counter(merged_obj["class_id"]).most_common(1)[0][0]
            merged_obj["class_name"] = obj_classes.get_classes_arr()[most_common_class_id]
            view.full_obj_list[existing_obj_id] = detected_obj["conf"]
            view.full_obj_list.pop(detected_obj_id)
            self.objects[existing_obj_id] = merged_obj
            captions.append(
                f"{existing_obj_id} {merged_obj['class_name']} {detected_obj['conf']:.3f} {merged_obj['num_detections']}"
            )
            all_obj_ids.append(existing_obj_id)
        return captions, added_obj_ids, all_obj_ids
    def _make_detection_list(self, gobs, obj_classes) -> DetectionDict:
        detection_list = DetectionDict()
        for mask_idx in range(len(gobs["mask"])):
            if gobs["pcd"][mask_idx] is None:
                continue
            class_name = gobs["classes"][gobs["class_id"][mask_idx]]
            detection_list[self.object_id_counter] = {
                "id": self.object_id_counter,
                "class_name": class_name,
                "class_id": [obj_classes.get_classes_arr().index(class_name)],
                "num_detections": 1,
                "conf": gobs["confidence"][mask_idx],
                "pcd": gobs["pcd"][mask_idx],
                "bbox": gobs["bbox"][mask_idx],
                "clip_ft": to_tensor(gobs["image_feats"][mask_idx]),
                "image": None,  # key of the anchor view that holds the instance
            }
            self._register_detection(self.object_id_counter,self._visible_detection_indices[mask_idx],class_name)
            self.object_id_counter += 1
        return detection_list
    def _merge_with_observation_checks(self, **options):
        """Filter proposed cleanup merges using co-observed source masks in this episode."""
        objects=options["objects"]
        threshold=options["merge_overlap_thresh"]
        if len(objects)<2 or threshold<=0:
            return objects
        # Use the pinned overlap computation and its original descending candidate order.
        ratios=cg_utils.compute_overlap_matrix_general(objects_a=objects, objects_b=None,
                                                       downsample_voxel_size=options["downsample_voxel_size"])
        rows,cols=ratios.nonzero()
        order=np.argsort(ratios[rows,cols])[::-1]
        ids=list(objects)
        frame_members={}
        def by_frame(oid):
            if oid not in frame_members:
                frames={}
                for member in self.members[oid]:
                    frame,index=member.rsplit(":d",1)
                    frames.setdefault(frame,[]).append(int(index))
                frame_members[oid]=frames
            return frame_members[oid]
        def inconsistent(first,second):
            left,right=by_frame(first),by_frame(second)
            for frame in left.keys() & right.keys():
                raw=self.camera_cache[frame]
                for i in left[frame]:
                    for j in right[frame]:
                        if raw["class_id"][i]!=raw["class_id"][j] and not np.any(raw["mask"][i] & raw["mask"][j]):
                            return True
            return False
        for k in order:
            i,j=rows[k],cols[k]
            if ratios[i,j]<=threshold:break
            src,dst=ids[i],ids[j]
            if src not in objects or dst not in objects:continue
            score=torch.nn.functional.cosine_similarity(to_tensor(objects[src]["clip_ft"]),
                                                        to_tensor(objects[dst]["clip_ft"]),dim=0)
            if not (score>options["merge_visual_sim_thresh"] and score>options["merge_text_sim_thresh"]):
                continue
            if inconsistent(src,dst):continue
            if objects[dst]["conf"]<objects[src]["conf"]:src,dst=dst,src
            objects[dst]=merge_obj2_into_obj1(objects[dst],objects[src],options["downsample_voxel_size"],
                options["dbscan_remove_noise"],options["dbscan_eps"],options["dbscan_min_points"],
                options["spatial_sim_type"],options["device"],run_dbscan=True)
            objects.pop(src)
            # on_merge just changed dst's provenance; a later pair must see the union.
            frame_members.pop(dst,None);frame_members.pop(src,None)
        return objects

    def _source_cleanup(self, frame_idx, pts):
        """Denoise, filter and merge instances at the intervals of the ConceptGraphs config."""
        if processing_needed(self.cfg_cg["denoise_interval"], self.cfg_cg["run_denoise_final_frame"], frame_idx, is_final_frame=False):
            from time import perf_counter
            started=perf_counter()
            if self.denoise_cache_bytes:
                self.cleanup_metrics.update(self.keep_all_clouds.apply(self.objects,self.cfg_cg,self.denoise_cache_bytes))
            else:
                self.objects = measure_time(denoise_objects)(
                    downsample_voxel_size=self.cfg_cg["downsample_voxel_size"],
                    dbscan_remove_noise=self.cfg_cg["dbscan_remove_noise"],
                    dbscan_eps=self.cfg_cg["dbscan_eps"],
                    dbscan_min_points=self.cfg_cg["dbscan_min_points"],
                    spatial_sim_type=self.cfg_cg["spatial_sim_type"],
                    device=self.device,
                    objects=self.objects,
                )
            self.cleanup_metrics['denoise_s']=perf_counter()-started
        if processing_needed(self.cfg_cg["filter_interval"], self.cfg_cg["run_filter_final_frame"], frame_idx, is_final_frame=False):
            self.objects = filter_objects(
                obj_min_points=self.cfg_cg["obj_min_points"],
                obj_min_detections=self.cfg_cg["obj_min_detections"],
                min_distance=self.cfg.perception.object_visibility_dist_m,
                objects=self.objects,
                pts=pts,
            )
        if processing_needed(self.cfg_cg["merge_interval"], self.cfg_cg["run_merge_final_frame"], frame_idx, is_final_frame=False):
            merge=(self._merge_with_observation_checks if self.cfg_cg.get("separate_same_frame_claims",False)
                   else merge_objects)
            self.objects = measure_time(merge)(
                merge_overlap_thresh=self.cfg_cg["merge_overlap_thresh"],
                merge_visual_sim_thresh=self.cfg_cg["merge_visual_sim_thresh"],
                merge_text_sim_thresh=self.cfg_cg["merge_text_sim_thresh"],
                objects=self.objects,
                downsample_voxel_size=self.cfg_cg["downsample_voxel_size"],
                dbscan_remove_noise=self.cfg_cg["dbscan_remove_noise"],
                dbscan_eps=self.cfg_cg["dbscan_eps"],
                dbscan_min_points=self.cfg_cg["dbscan_min_points"],
                spatial_sim_type=self.cfg_cg["spatial_sim_type"],
                device=self.device,
            )

        # drop removed instances from the view records
        for key in list(self.views.keys()):
            view = self.views[key]
            view.cluster = [obj_id for obj_id in view.cluster if obj_id in self.objects]
            view.full_obj_list = {k: v for k, v in view.full_obj_list.items() if k in self.objects}
            if len(view.full_obj_list) == 0:
                self.views.pop(key)
    def _drop_empty_views(self):
        self.views = {k: v for k, v in self.views.items() if len(v.full_obj_list) > 0}
        self.anchor_views = {k: v for k, v in self.anchor_views.items() if len(v.cluster) > 0}
    def update_anchor_views(self, obj_ids, min_detection=1):
        """Re-cluster the instances near the agent and select the anchor views
        that observe each cluster (co-visibility clustering)."""
        self._drop_empty_views()
        prev_anchor_views = copy.deepcopy(self.anchor_views)

        obj_ids_temp = obj_ids.copy()
        for key, view in self.anchor_views.items():
            if any(obj_id in obj_ids_temp for obj_id in view.cluster):
                obj_ids = obj_ids.union(set(view.cluster))
                prev_anchor_views.pop(key)
        obj_ids = list(set(obj_ids))

        # instances observed fewer than ``min_detection`` times are not assigned
        obj_exclude = [obj_id for obj_id in self.objects.keys() if self.objects[obj_id]["num_detections"] < min_detection]
        obj_ids = [obj_id for obj_id in obj_ids if obj_id not in obj_exclude]

        obj_centers = np.zeros((len(obj_ids), 2))
        for i, obj_id in enumerate(obj_ids):
            obj_centers[i] = self.objects[obj_id]["bbox"].center[[0, 2]]
        if len(obj_centers) == 0:
            return

        self.clustering.split_coincident_by_view=self.cfg_cg.get("separate_same_frame_claims",False)
        new_anchor_views = self.clustering.fit(obj_centers, obj_ids, self.views)
        assert {o for v in new_anchor_views.values() for o in v.cluster} == set(obj_ids)

        for key, view in new_anchor_views.items():
            if key in prev_anchor_views:
                prev_anchor_views[key].cluster += view.cluster
            else:
                prev_anchor_views[key] = view
        self.anchor_views = prev_anchor_views

        for key, view in self.anchor_views.items():
            for obj_id in view.cluster:
                self.objects[obj_id]["image"] = key
        # the anchor views and their view records are the same objects
        for key, view in self.anchor_views.items():
            self.views[key] = view
    def visible_objects(self, view_key: str) -> List[int]:
        """O^vis(v): instances detected in the view within the visibility distance."""
        view = self.views.get(view_key) or self.anchor_views.get(view_key)
        if view is None:
            return []
        return [obj_id for obj_id in view.full_obj_list if obj_id in self.objects]
    def object_crop(self, view_key: str, obj_id: int, size: Optional[Tuple[int, int]] = None) -> Optional[np.ndarray]:
        """Representative crop for the original live-view caller. Use SnapshotReader.get_object_evidence for source members."""
        if obj_id is None or obj_id not in self.objects:return None
        view = self.views.get(view_key) or self.anchor_views.get(view_key)
        img = self.observations.get(view_key)
        if view is None or img is None or view.visual_prompt is None:
            return None
        ids = list(view.visual_prompt.data.get("obj_id", []))
        if obj_id not in ids:
            return None
        from ..storage.store import clip_detection_box
        bounds = clip_detection_box(view.visual_prompt.xyxy[ids.index(obj_id)], img.shape,
                                    legacy_integer=True)
        if bounds is None:
            return None
        x0, y0, x1, y1 = bounds
        crop = img[y0:y1, x0:x1]
        if size is not None and crop.size > 0:
            # Exact pinned habitat_utils.resize_image uses only PIL;keep that
            # pure function here without importing its simulator-owning module.
            h, w = crop.shape[:2]
            scale = min(size[0] / h, size[1] / w)
            crop = np.array(Image.fromarray(crop).resize((max(1,int(w*scale)),max(1,int(h*scale)))))
        return crop if crop.size > 0 else None


from ..storage.features import DOOR_ARRAYS,check_door_arrays


def pack_camera(payload):
    """One safe NPZ bundle per frame, including pre-world local contributions."""
    n=len(payload["mask"]);points=payload["local_points"];colors=payload["local_colors"]
    if len(points)!=n or len(colors)!=n:raise ValueError("Local contribution count mismatch")
    offsets=np.cumsum([0]+[len(x)for x in points],dtype=np.int64)
    arrays={name:np.asarray(payload[name])for name in ("xyxy","confidence","class_id","mask","image_feats")}
    arrays["local_points"]=np.concatenate(points,axis=0)if n else np.empty((0,3),np.float32)
    arrays["local_colors"]=np.concatenate(colors,axis=0)if n else np.empty((0,3),np.float32)
    arrays["local_offsets"]=offsets
    if "full_clip"in payload:arrays["full_clip"]=np.asarray(payload["full_clip"])
    metadata=dict(count=n,image_hw=list(payload["mask"].shape[1:]),mask_encoding="bool_array",
                       local_coordinate="camera_up_negative_z",features="original_source_CLIP",
                       has_full_clip="full_clip"in payload,room_hint=payload.get("room_hint"))

    if "door_candidate_count" in payload:
        count=payload["door_candidate_count"]
        metadata["door_candidate_count"]=count
        if type(count) is not int or count<0:raise ValueError("Invalid door candidate count")
        if count:
            arrays.update({k:np.asarray(payload[k]) for k in DOOR_ARRAYS})
            check_door_arrays(arrays,count,*metadata["image_hw"])
    return arrays,metadata


def unpack_camera(arrays,metadata):
    n=metadata["count"];offsets=np.asarray(arrays["local_offsets"])
    if (offsets.shape!=(n+1,)or offsets.dtype.kind not in "iu" or offsets[0]!=0
        or np.any(np.diff(offsets)<0)or offsets[-1]!=len(arrays["local_points"])
        or np.shape(arrays["local_points"])!=np.shape(arrays["local_colors"])):
        raise ValueError("Local point contribution offsets invalid")
    result={name:np.asarray(arrays[name])for name in ("xyxy","confidence","class_id","mask","image_feats")}
    if result["mask"].shape!=(n,*metadata["image_hw"]):raise ValueError("Mask dimensions mismatch")
    result["local_points"]=[np.asarray(arrays["local_points"][a:b])for a,b in zip(offsets[:-1],offsets[1:])]
    result["local_colors"]=[np.asarray(arrays["local_colors"][a:b])for a,b in zip(offsets[:-1],offsets[1:])]
    if metadata.get("has_full_clip"):result["full_clip"]=np.asarray(arrays["full_clip"])
    if metadata.get("room_hint")is not None:result["room_hint"]=metadata["room_hint"]
    if "door_candidate_count" in metadata:
        count=metadata["door_candidate_count"]
        check_door_arrays(arrays,count,*metadata["image_hw"])
        result["door_candidate_count"]=count
        if count:result.update({k:arrays[k] for k in DOOR_ARRAYS})
    return result

from dataclasses import dataclass,field
from typing import Callable,Sequence

@dataclass
class ViewNode:
    id: str
    kind: str  # "visited", "anchor" or "frontier"
    position: np.ndarray  # estimated G Y-up full3D camera position;never simulator GT
    image_key: Optional[str] = None
    room: str = "unknown"
    objects: List[int] = field(default_factory=list)  # visible objects (anchor views)
    anchor_link: Optional[str] = None  # nearest visited view (frontier views)

class RoomLabeler:
    """Threshold-free CLIP room label: argmax over 'a photo of a <room>' prompts."""

    def __init__(self, clip_model, clip_preprocess, clip_tokenizer, room_vocab: Sequence[str], image_size: int = 360):
        import torch

        self.torch = torch
        self.model = clip_model
        self.preprocess = clip_preprocess
        self.vocab = list(room_vocab)
        self.image_size = int(image_size)
        self.device = next(clip_model.parameters()).device
        with torch.no_grad():
            tokens = clip_tokenizer([f"a photo of a {r}" for r in self.vocab]).to(self.device)
            feat = clip_model.encode_text(tokens)
            self.text_feat = feat / (feat.norm(dim=-1, keepdim=True) + 1e-6)

    def __call__(self, image: Optional[np.ndarray]) -> str:
        if image is None:
            return "unknown"
        from PIL import Image


        img = resize_image(np.asarray(image)[..., :3], self.image_size, self.image_size)
        with self.torch.no_grad():
            x = self.preprocess(Image.fromarray(img)).unsqueeze(0).to(self.device)
            feat = self.model.encode_image(x)
            feat = feat / (feat.norm(dim=-1, keepdim=True) + 1e-6)
            idx = int((feat @ self.text_feat.T).squeeze(0).argmax().item())
        return self.vocab[idx]


class VSMGraph:
    def __init__(self, room_labeler: Optional[Callable[[Optional[np.ndarray]], str]] = None):
        self.room_labeler = room_labeler
        self._room_cache: Dict[Tuple, str] = {}
        self.reset()
    def reset(self):
        """The VSMGraph is cleared at the end of each episode."""
        self.visited: List[ViewNode] = []
        self.navigability: List[Tuple[str, str]] = []
        self.anchors: Dict[str, ViewNode] = {}
        self.frontiers: Dict[str, ViewNode] = {}
        self.objects: Dict[int, Dict] = {}
        self._room_cache.clear()
    def _label(self, cache_key: Tuple, image: Optional[np.ndarray]) -> str:
        if cache_key in self._room_cache:
            return self._room_cache[cache_key]
        if self.room_labeler is None:
            return "unknown"
        self._room_cache[cache_key] = self.room_labeler(image)
        return self._room_cache[cache_key]
    def add_visited_view(self, step: int, position: np.ndarray, image_key: Optional[str]) -> ViewNode:
        node = ViewNode(id=f"v{step}", kind="visited", position=np.asarray(position, dtype=float), image_key=image_key)
        self.visited.append(node)
        return node
    def sync_anchor_views(self, scene, pose_lookup: Callable) -> None:
        nodes = {}
        for key, view in scene.anchor_views.items():
            cache_key=("anchor",key)
            image=(None if cache_key in self._room_cache or self.room_labeler is None
                   else scene.observations.get(key))
            nodes[key] = ViewNode(
                id=key,
                kind="anchor",
                position=np.asarray(pose_lookup(key)[:3,3], dtype=float),
                image_key=key,
                room=self._label(cache_key,image),
                objects=scene.visible_objects(key),
            )
        self.anchors = nodes
        self.objects = {
            int(oid): {"category": obj["class_name"], "anchor": obj.get("image")} for oid, obj in scene.objects.items()
        }
    def visibility_edges(self) -> List[Tuple[str, int]]:
        return [(a.id, oid) for a in self.anchors.values() for oid in a.objects]
    def room_type_index(self) -> Dict[str, Dict[str, list]]:
        """Uncalibrated room-type index only;not physical room instances."""
        out: Dict[str, Dict[str, list]] = {}
        for a in self.anchors.values():
            out.setdefault(a.room, {"anchors": [], "frontiers": [], "objects": []})["anchors"].append(a.id)
        for f in self.frontiers.values():
            out.setdefault(f.room, {"anchors": [], "frontiers": [], "objects": []})["frontiers"].append(f.id)
        for oid, obj in self.objects.items():
            anchor = self.anchors.get(obj.get("anchor"))
            if anchor is not None:
                out[anchor.room]["objects"].append(oid)
        return out

