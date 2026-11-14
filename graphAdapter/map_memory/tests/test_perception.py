"""Actual original CG association/clustering with explicit CPU camera fixtures;not model/navigation evidence."""
from pathlib import Path
import sys,copy
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/"runtime/graph_memory/package_root"))
sys.path.insert(0,str(ROOT/"vendor_sources/EvoMemNav"))
import numpy as np
import pytest
from omegaconf import OmegaConf
from graphAdapter.map_memory.perception.scene import MemoryOnlyScene,pack_camera,unpack_camera,VSMGraph

def config():
    cfg=OmegaConf.load(ROOT/"vendor_sources/EvoMemNav/cfg/evomemnav_goatbench.yaml")
    cfg.data.object_classes_path=str(ROOT/"vendor_sources/EvoMemNav/data/scannet200_classes.txt")
    cg=OmegaConf.load(ROOT/"vendor_sources/EvoMemNav/cfg/concept_graph.yaml")
    return cfg,cg
def payload(count=1,shift=0.,sign=1.):
    grid=np.array([[x,y,z]for x in np.linspace(-.05,.05,5)
        for y in np.linspace(-.05,.05,5)for z in np.linspace(-2.05,-1.95,5)],np.float32)
    grid[:,0]+=shift
    feature=np.zeros((count,512),np.float32)
    if count:feature[:,0]=sign
    masks=np.zeros((count,32,32),bool);masks[:,8:20,8:20]=True
    return dict(xyxy=np.tile(np.array([[8,8,20,20]],np.float32),(count,1)),
        confidence=np.full(count,.9,np.float32),class_id=np.zeros(count,np.int64),
        mask=masks,image_feats=feature,local_points=[grid.copy()for _ in range(count)],
        local_colors=[np.zeros_like(grid)for _ in range(count)])
def scene(cache):
    cfg,cg=config();images={k:np.zeros((32,32,3),np.uint8)for k in cache}
    return MemoryOnlyScene(cfg,cg,models=None,camera_cache=cache,observations=images,epoch="cpu-fixture",cache_only=True)
def fuse(s,key,frame_idx=1,position=None):
    position=np.zeros(3)if position is None else position
    return s.fuse(s.observations[key],np.ones((32,32),np.float32),np.eye(3),np.eye(4),
                  position,np.zeros(3),key,frame_idx=frame_idx)

def test_G07_empty_frame_survives_archive_and_missing_cache_is_not_dummy_detector():
    s=scene({"e:f1":payload(0)})
    result=fuse(s,"e:f1")
    assert result[1]==[] and not s.objects and "e:f1"in s.observations
    assert not hasattr(s,"simulator") and not hasattr(s,"pathfinder")
    assert not hasattr(s,"get_observation") and not hasattr(s,"get_frontier_observation")
    with pytest.raises(RuntimeError,match="No cached"):
        s.prepare_camera(np.zeros((32,32,3),np.uint8),None,None,"missing")
    cfg,cg=config()
    with pytest.raises(RuntimeError,match="Actual perception"):
        MemoryOnlyScene(cfg,cg,models=None,camera_cache={},observations={},epoch="bad")

def test_G07_two_actual_source_merges_update_all_view_references_and_members():
    s=scene({"e:f1":payload(1),"e:f2":payload(2)})
    fuse(s,"e:f1")
    assert set(s.objects)=={1}
    old_image=s.observations["e:f1"].copy()
    fuse(s,"e:f2",2)
    assert set(s.objects)=={1}
    assert s.objects[1]["num_detections"]==3 and s.resolve(2)==s.resolve(3)==1
    assert len(s.members[1])==3
    for view in s.views.values():
        assert set(view.full_obj_list)=={1}
        assert set(view.cluster)<={1}
        assert set(view.visual_prompt.data["obj_id"])=={1}
    assert np.array_equal(old_image,s.observations["e:f1"])

def test_G07_actual_source_retire_preserves_images_and_does_not_reassign_by_name():
    s=scene({"e:f1":payload(1),"e:f2":payload(2),"e:f3":payload(1,shift=1.,sign=-1.),
             "e:f4":payload(0)})
    fuse(s,"e:f1");fuse(s,"e:f2",2);fuse(s,"e:f3",3)
    new=set(s.objects)-{1};assert len(new)==1;retired=next(iter(new))
    # Source filtering removes far,one-detection objects at its fixed12-frame interval.
    fuse(s,"e:f4",11,position=np.array([10.,0,0]))
    assert retired not in s.objects and retired in s.retired and s.resolve(retired)is None
    assert "e:f3"in s.observations and np.array_equal(s.observations["e:f3"],np.zeros((32,32,3),np.uint8))
    for view in s.views.values():assert retired not in view.full_obj_list and retired not in view.cluster

def test_G09_scene_candidate_fork_does_not_mutate_committed_data():
    s=scene({"e:f1":payload(1),"e:f2":payload(1)})
    fuse(s,"e:f1")
    candidate=s.fork();fuse(candidate,"e:f2",2)
    assert s.objects[1]["num_detections"]==1 and candidate.objects[1]["num_detections"]==2
    assert "e:f2"not in s.views and "e:f2"in candidate.views
    assert candidate.camera_cache is s.camera_cache and candidate.observations is s.observations

def test_G07_safe_camera_bundle_roundtrip():
    original=payload(2)
    arrays,meta=pack_camera(original);restored=unpack_camera(arrays,meta)
    for name in ("xyxy","confidence","class_id","mask","image_feats"):
        np.testing.assert_array_equal(original[name],restored[name])
    for a,b in zip(original["local_points"],restored["local_points"]):np.testing.assert_array_equal(a,b)
    arrays["local_offsets"]=np.array([0,500,2])
    with pytest.raises(ValueError):unpack_camera(arrays,meta)

def test_G11_G12_graph_anchor_uses_full_camera_pose_and_no_navigability_or_room_instance_merge():
    s=scene({"e:f1":payload(1)})
    fuse(s,"e:f1")
    graph=VSMGraph()
    graph.add_visited_view(1,np.array([0,0,0]),"e:f1")
    graph.add_visited_view(2,np.array([0,3,0]),"e:f2")
    assert not graph.navigability and not hasattr(graph,"sync_frontier_views")
    pose=np.eye(4);pose[:3,3]=[1,4.25,-2]
    graph.sync_anchor_views(s,lambda key:pose)
    for anchor in graph.anchors.values():np.testing.assert_array_equal(anchor.position,[1,4.25,-2])
    assert hasattr(graph,"room_type_index")and not hasattr(graph,"rooms")


def test_G07_scene_disk_snapshot_restore_keeps_aliases_objects_and_image_bindings(tmp_path):
    from graphAdapter.map_memory.storage.store import EpisodeStore
    s=scene({"e:f1":payload(1),"e:f2":payload(2)})
    fuse(s,"e:f1");fuse(s,"e:f2",2)
    store=EpisodeStore(tmp_path/"episode","e",dataset="r2r")
    try:
        state,entities,aliases=s.snapshot(store,3)
        cfg,cg=config()
        restored=MemoryOnlyScene.restore(cfg,cg,models=None,camera_cache=s.camera_cache,
            observations=s.observations,state=state,store=store,cache_only=True)
        assert restored.aliases==s.aliases and restored.members==s.members
        assert restored.objects[1]["num_detections"]==s.objects[1]["num_detections"]
        np.testing.assert_array_equal(np.asarray(restored.objects[1]["pcd"].points),np.asarray(s.objects[1]["pcd"].points))
        assert restored.objects[1]["image"]==s.objects[1]["image"]
        for key in restored.anchor_views:assert restored.anchor_views[key]is restored.views[key]
        assert all(x["epoch"]=="cpu-fixture"for x in entities)and len(aliases)==2
    finally:store.close()


def test_G14_camera_archive_cache_is_byte_bounded_and_source_immutable(tmp_path):
    from graphAdapter.map_memory.service import CameraDetectionArchive
    from graphAdapter.map_memory.storage.store import EpisodeStore
    from test_storage import archive,EP
    store=EpisodeStore(tmp_path/"episode",EP,dataset="r2r")
    try:
        cache=CameraDetectionArchive(store,{"scope":"cpu_contract"},max_bytes=40000)
        source=payload(1)
        for seq in range(1,21):
            from test_storage import capture
            meta=capture(seq);uid=meta["frame_uid"]
            store.archive_frame(meta,np.zeros((32,32,3),np.uint8),np.ones((32,32),np.float32),
                                np.ones((32,32),np.float32),np.ones((32,32),bool))
            cache[uid]=source
            assert cache.bytes<=40000
        uid=f"{EP}:f000020";source["local_points"][0][:]+=100
        recovered=cache[uid]
        assert abs(float(recovered["local_points"][0][0,0]))<1
        with pytest.raises(ValueError):recovered["local_points"][0][0,0]=5
        assert len(list((store.root/"detections").glob("*.npz")))==20
        assert len(cache)<21
        cache.__delitem__(uid)
        assert cache.record(uid)["metadata"]["count"]==1
    finally:store.close()


def test_G00_camera_masks_for_another_rgb_grid_are_rejected(tmp_path):
    from graphAdapter.map_memory.service import CameraDetectionArchive
    from graphAdapter.map_memory.storage.store import EpisodeStore,IntegrityError
    from test_storage import archive,EP
    store=EpisodeStore(tmp_path/"episode",EP,dataset="r2r")
    try:
        raw=archive(store,1)
        cache=CameraDetectionArchive(store,{"scope":"cpu_contract"})
        with pytest.raises(IntegrityError,match="RGB grid"):cache[raw["frame_uid"]]=payload(1)
    finally:store.close()


def test_G11_object_crop_resize_uses_original_PIL_pixels_without_simulator_import(monkeypatch):
    import builtins
    from PIL import Image
    s=scene({"e:f1":payload(1)});s.observations["e:f1"]=np.arange(32*32*3,dtype=np.uint8).reshape(32,32,3)
    fuse(s,"e:f1")
    original=builtins.__import__
    def no_sim(name,*a,**k):
        if name=="evomemnav.env.habitat_utils"or name.startswith(("habitat","habitat_sim")):raise AssertionError("Simulator import")
        return original(name,*a,**k)
    monkeypatch.setattr(builtins,"__import__",no_sim)
    raw=s.object_crop("e:f1",1)
    np.testing.assert_array_equal(s.object_crop("e:f1",1,size=(6,9)),np.array(Image.fromarray(raw).resize((6,6))))
    candidate=s.fork()
    assert candidate.clustering is not s.clustering
    candidate.clustering.samples_number=99
    assert getattr(s.clustering,"samples_number",None)!=99


def test_G11_model_RGB_entry_and_bbox_copy_survive_actual_API_mutation(monkeypatch):
    from types import SimpleNamespace
    import torch
    from PIL import Image
    import graphAdapter.map_memory.perception.scene as module
    s=scene({});rgb=np.zeros((32,32,3),np.uint8);rgb[:]=[11,33,77]
    boxes=torch.tensor([[8.,8.,20.,20.]])
    received=[];filtered_boxes=[]
    def detect(source,**kw):
        received.append(source)
        return [SimpleNamespace(boxes=SimpleNamespace(conf=torch.tensor([.9]),cls=torch.tensor([0.]),xyxy=boxes))]
    def segment(source,**kw):
        received.append(source)
        # Pinned SAM scales its prompt tensor in-place. The original CPU bbox
        # copy must therefore be independent even on CPU/no device transfer.
        kw["bboxes"].mul_(2)
        return [SimpleNamespace(masks=SimpleNamespace(data=torch.ones((1,32,32))))]
    def filter_source(**kw):
        filtered_boxes.append(kw["detections"].xyxy.copy());return None,None
    s.detection_model=SimpleNamespace(predict=detect);s.sam_predictor=SimpleNamespace(predict=segment)
    monkeypatch.setattr(module,"filter_detections",filter_source)
    s._detect_camera(rgb,None,None)
    assert all(isinstance(x,Image.Image)and x.mode=="RGB"for x in received)
    for x in received:np.testing.assert_array_equal(np.array(x),rgb)
    np.testing.assert_array_equal(filtered_boxes[0],np.array([[8.,8.,20.,20.]]))

def test_G11_pinned_PIL_RGB_preprocessing_keeps_channel_semantics(monkeypatch):
    from types import SimpleNamespace
    from PIL import Image
    import torch
    monkeypatch.setenv("YOLO_CONFIG_DIR",str(ROOT/"runtime/graph_memory/model-settings"))
    from ultralytics.data.loaders import LoadPilAndNumpy
    from ultralytics.engine.predictor import BasePredictor
    from ultralytics.models.sam.predict import Predictor
    rgb=np.zeros((32,32,3),np.uint8);rgb[:]=[11,33,77]
    for cls,scale in ((BasePredictor,255),(Predictor,1)):
        predictor=object.__new__(cls);predictor.device=torch.device("cpu")
        predictor.model=SimpleNamespace(fp16=False);predictor.pre_transform=lambda x:x
        predictor.im=None;predictor.mean=torch.zeros((1,3,1,1));predictor.std=torch.ones((1,3,1,1))
        actual=predictor.preprocess(LoadPilAndNumpy(Image.fromarray(rgb)).im0)
        np.testing.assert_array_equal((actual[0,:,0,0]*scale).numpy(),[11.,33.,77.])


def test_G07_retired_null_prompt_slot_is_not_a_crop_request():
    s=scene({"e:f1":payload(1)});fuse(s,"e:f1")
    # Exercise the actual retirement notification,independent of source cleanup
    # choosing to remove an entire empty view rather than keeping mixed slots.
    s.objects.pop(1);s.on_retire(1);s.repair_references()
    assert None in s.views["e:f1"].visual_prompt.data["obj_id"]
    assert s.object_crop("e:f1",None)is None
    assert s.object_crop("e:f1",1)is None


@pytest.mark.parametrize('has_model',[False,True])
def test_cached_room_hint_survives_without_model_and_never_reads_image(has_model):
    from types import SimpleNamespace
    from graphAdapter.map_memory.perception.scene import VSMGraph
    def forbidden(*args):raise AssertionError('Cached room evidence was recomputed/read')
    graph=VSMGraph(room_labeler=forbidden if has_model else None)
    graph._room_cache[('anchor','frame')]='kitchen'
    scene=SimpleNamespace(anchor_views={'frame':object()},observations=SimpleNamespace(get=forbidden),
        objects={1:dict(class_name='chair',image='frame')},visible_objects=lambda key:[1])
    graph.sync_anchor_views(scene,lambda key:np.eye(4))
    assert graph.anchors['frame'].room=='kitchen'
    assert graph.room_type_index()['kitchen']['objects']==[1]


def test_missing_room_hint_without_model_stays_unknown_without_reading_image():
    from types import SimpleNamespace
    from graphAdapter.map_memory.perception.scene import VSMGraph
    def forbidden(*args):raise AssertionError('No labeler exists to consume an image')
    graph=VSMGraph(room_labeler=None)
    scene=SimpleNamespace(anchor_views={'frame':object()},observations=SimpleNamespace(get=forbidden),
        objects={},visible_objects=lambda key:[])
    graph.sync_anchor_views(scene,lambda key:np.eye(4))
    assert graph.anchors['frame'].room=='unknown'


def test_structural_door_evidence_is_optional_and_separate_from_foreground():
    original=payload(1)
    arrays,meta=pack_camera(original)
    assert "door_candidate_count" not in unpack_camera(arrays,meta)
    original["door_candidate_count"]=0
    arrays,meta=pack_camera(original)
    assert unpack_camera(arrays,meta)["door_candidate_count"]==0
    mask=np.zeros((1,32,32),bool); mask[:,4:18,3:14]=True
    original.update(door_candidate_count=1,door_proposal_indices=np.array([2],np.int32),
                    door_xyxy=np.array([[3,4,14,18]],np.float32),door_confidence=np.array([.7],np.float32),
                    door_mask_bits=np.packbits(mask,axis=2,bitorder="little"))
    arrays,meta=pack_camera(original);copy=unpack_camera(arrays,meta)
    assert meta["count"]==1 and copy["door_candidate_count"]==1
    np.testing.assert_array_equal(np.unpackbits(copy["door_mask_bits"],axis=2,bitorder="little"),mask)
    np.testing.assert_array_equal(copy["class_id"],original["class_id"])


def test_conflicting_same_frame_claims_keep_distinct_masks_and_preserve_order():
    from graphAdapter.map_memory.perception.scene import separate_same_frame_claims
    a=np.eye(4,dtype=bool);b=~a
    d={2:{"class_name":"kettle"},3:{"class_name":"window"},4:{"class_name":"window"}}
    o={1:{"class_name":"window"}};s=np.array([[1.8],[1.7],[1.6]])
    pairs=[(2,1),(3,1),(4,1)]
    assert separate_same_frame_claims(pairs,d,o,s,{2:a,3:b,4:b})==[(2,None),(3,1),(4,1)]
    assert separate_same_frame_claims(pairs,d,o,s,{2:b,3:b,4:b})==pairs



def test_cleanup_checks_separated_claims_after_fork_and_restore(tmp_path):
    from graphAdapter.map_memory.storage.store import EpisodeStore
    second=payload(2);second["class_id"][1]=1
    second["mask"][0,:,16:]=False;second["mask"][1,:,:16]=False
    s=scene({"e:f1":payload(1),"e:f2":second});s.cfg_cg.separate_same_frame_claims=True
    fuse(s,"e:f1",1);fuse(s,"e:f2",2)
    expected={1:{"e:f1:d00000","e:f2:d00000"},3:{"e:f2:d00001"}}
    assert {i:s.members[i] for i in s.objects}==expected
    store=EpisodeStore(tmp_path/"episode","e",dataset="r2r")
    try:
        state,_,_=s.snapshot(store,0)
        restored=MemoryOnlyScene.restore(s.cfg,s.cfg_cg,models=None,camera_cache=s.camera_cache,
            observations=s.observations,state=state,store=store,cache_only=True)
        for value in (s.fork(copy_on_write=True),restored,s):
            value.periodic_cleanup_objects(11,np.zeros(3))
            assert {i:value.members[i] for i in value.objects}==expected
            assert value.views["e:f2"].visual_prompt.data["obj_id"]==[1,3]
            assert value.resolve(3)==3 and value.model_frames==0
    finally:store.close()


def test_cleanup_rechecks_provenance_after_a_third_object_absorbs_one_member(monkeypatch):
    from graphAdapter.map_memory.perception import scene as mapping
    # Object 1 precedes objects 2 and 3. Only 2 and 3 have incompatible same-frame observations.
    pair=payload(2,sign=-1.);pair["class_id"][1]=1
    pair["mask"][0,:,16:]=False;pair["mask"][1,:,:16]=False
    s=scene({"e:f1":payload(1),"e:f2":pair});s.cfg_cg.separate_same_frame_claims=True
    fuse(s,"e:f1",1);fuse(s,"e:f2",2)
    assert set(s.objects)=={1,2,3}
    s.objects[1]["conf"]=.99
    for o in s.objects.values():o["clip_ft"]=s.objects[1]["clip_ft"].clone()
    def fixture_ratios(**kw):
        assert list(kw["objects_a"])==[1,2,3]
        return np.array([[0,.99,.95],[0,0,0],[0,0,0]])
    monkeypatch.setattr(mapping.cg_utils,"compute_overlap_matrix_general",fixture_ratios)
    s.periodic_cleanup_objects(11,np.zeros(3))
    assert set(s.objects)=={1,3} and s.resolve(2)==1 and s.resolve(3)==3
    assert s.members[1]=={"e:f1:d00000","e:f2:d00000"} and s.members[3]=={"e:f2:d00001"}



def test_disjoint_claims_with_no_category_match_do_not_transfer_previous_identity():
    from graphAdapter.map_memory.perception.scene import separate_same_frame_claims
    first=np.eye(5,dtype=bool)
    det={5:{"class_name":"couch"},6:{"class_name":"pillow"},7:{"class_name":"plant"}}
    old={1:{"class_name":"sofa chair"},4:{"class_name":"plant"}}
    raw=[(5,1),(6,1),(7,4)]
    scores=np.array([[1.3,.2],[1.98,.2],[.2,1.7]])
    assert separate_same_frame_claims(raw,det,old,scores,{5:first,6:~first,7:first})==[(5,None),(6,None),(7,4)]
    assert separate_same_frame_claims(raw,det,old,scores,{5:first,6:first,7:first})==raw
    det[5]["class_name"]="sofa chair"
    assert separate_same_frame_claims(raw,det,old,scores,{5:first,6:~first,7:first})==[(5,1),(6,None),(7,4)]
