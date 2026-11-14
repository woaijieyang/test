"""CPU end-to-end service with000real producer interfaces and explicit cached camera fixtures."""
from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/"runtime/graph_memory/package_root"))
sys.path.insert(0,str(ROOT/"vendor_sources/EvoMemNav"))
# Match the private worker: canonical source must win over borrowed pose aliases.
sys.path.insert(0,str(ROOT/"src"))
import numpy as np,pytest
from graphAdapter.map_memory.storage.store import EpisodeStore,load_episode,IntegrityError,VersionUnavailable,canonical
from graphAdapter.map_memory.service import MapMemoryService
from graphAdapter.observation_pose.aware_hook import AwarePoseHook
def profile():
    return json.loads((ROOT/"src/graphAdapter/observation_pose/profiles/000_pose_shadow.json").read_text())
from graphAdapter.observation_pose.tests.fixtures import sensor_spec,adapter_factory
from test_perception import payload,config

def inputs(tmp_path):
    h=AwarePoseHook(tmp_path/"source",profile(),adapter_factory=adapter_factory)
    rgb=np.zeros((32,32,3),np.uint8);raw=np.ones((32,32),np.float32)
    p=h.reset("unit",sensor_spec(32),rgb,raw,1)
    return h,p,rgb,raw
def receipt_arrays(h,p,rgb,raw):
    packet,receipt=h.committed_endpoint()
    assert packet is p
    aligned=np.load(p.aligned_ref)if p.aligned_ref else None
    mask=np.load(Path(p.aligned_ref).parent/"depth_valid_mask.npy")if p.aligned_ref else None
    return dict(rgb=rgb,raw_depth=raw,aligned_depth=aligned,valid_mask=mask,
                committed_receipt=receipt,host_view=rgb,host_transform={"kind":"identity"})
def seeded_service(store,p,arguments):
    cfg,cg=config()
    service=MapMemoryService(store,cfg,cg,models=None,model_identity={"scope":"cpu_contract"},
        cpu_contract=True,geometry_options=dict(voxel_size=.25,core_size=(2,2,2),max_resident_tiles=2,max_candidate_tiles=128))
    seed_camera(service,p,arguments)
    return service
def seed_camera(service,p,args):
    service.store.archive_frame(p.to_record(),args["rgb"],args["raw_depth"],args["aligned_depth"],args["valid_mask"],
       host_view=args["host_view"],host_transform=args["host_transform"])
    service.camera[p.frame_uid]=payload(1)

def test_G00_G06_000commit_to_single_snapshot_reload_and_duplicate(tmp_path):
    h,p,rgb,raw=inputs(tmp_path)
    store=EpisodeStore(tmp_path/"memory","unit",dataset="r2r")
    try:
        args=receipt_arrays(h,p,rgb,raw);s=seeded_service(store,p,args)
        result=s.ingest(p,**args);pointer=(store.root/"CURRENT.json").read_bytes()
        reader=load_episode(store.root)
        assert reader.get_view(p.frame_uid)["geometry_status"]=="available"
        assert reader.verify()["views"]==1 and s.scene.objects
        duplicate=s.ingest(p,**args)
        assert duplicate["duplicate"]and pointer==(store.root/"CURRENT.json").read_bytes()
        reader.close()
        restored=MapMemoryService(store,*config(),models=None,model_identity={"scope":"cpu_contract"},
            cpu_contract=True,geometry_options=s.geometry_options)
        assert restored.pointer==s.pointer and set(restored.scene.objects)==set(s.scene.objects)
    finally:store.close();h.close()

def test_G00_bad_receipt_raw_or_mask_cannot_flow_into_memory(tmp_path):
    h,p,rgb,raw=inputs(tmp_path);store=EpisodeStore(tmp_path/"memory","unit",dataset="r2r")
    try:
        args=receipt_arrays(h,p,rgb,raw);s=seeded_service(store,p,args)
        for change in (dict(committed_receipt=None),dict(rgb=rgb+1),dict(valid_mask=~args["valid_mask"])):
            with pytest.raises(IntegrityError):s.prepare_endpoint(p,**dict(args,**change))
        assert not (store.root/"CURRENT.json").exists()
    finally:store.close();h.close()

def test_G09_changed_target_before_grant_leaves_current_and_cached_sources(tmp_path):
    h,p,rgb,raw=inputs(tmp_path);store=EpisodeStore(tmp_path/"memory","unit",dataset="r2r")
    try:
        args=receipt_arrays(h,p,rgb,raw);s=seeded_service(store,p,args);s.ingest(p,**args)
        old=(store.root/"CURRENT.json").read_bytes()
        h.begin_macro(1,1);second=h.capture(rgb,raw,2,action_id=1,collision=False)
        args2=receipt_arrays(h,second,rgb,raw);seed_camera(s,second,args2)
        ready=s.prepare_endpoint(second,**args2)
        with pytest.raises(VersionUnavailable):
            s.publish_prepared(frame_uid=second.frame_uid,target_pose_map_version=ready["target_pose_map_version"],version_check=lambda:False)
        assert old==(store.root/"CURRENT.json").read_bytes()and second.frame_uid in s.camera
        assert second.frame_uid not in s.frames
    finally:store.close();h.close()


def bound_packet(seq,key,bindings):
    from graphAdapter.observation_packet import ObservationPacket
    from poseAdapter.coordinate.frames import OPTICAL_TO_FLU
    mount=np.eye(4);mount[:3,:3]=OPTICAL_TO_FLU;mount[:3,3]=[0,0,1.25]
    relative=np.eye(4);relative[0,3]=1
    base=np.asarray(bindings["optimized_keyframes"][str(key)])@relative
    pose=dict(episode_id="unit",frame_id=f"unit:f{seq:06d}",timestamp_ns=seq,valid=True,
        tracking_state="tracking",source="cuvslam_rtabmap_rgbd",geometry_status="available",
        map_version=bindings["map_version"],T_map_base=base.tolist(),T_odom_base=base.tolist(),
        T_map_camera_cv=(base@mount).tolist(),rtab_keyframe_id=key,T_keyframe_base=relative.tolist(),
        spatial_bindings=bindings,diagnostics=dict(measurement_support=dict(kind=2,used=50,prediction_used=False),
          global_frame_link=dict(verified=True,epoch=0),odometry_frame_link=np.eye(4).tolist()))
    packet=ObservationPacket("unit",pose["frame_id"],seq-1,None,seq*10,seq,seq,
        "cpu_fixture_rgb","cpu_fixture_depth","cpu_fixture_aligned","cpu_calibration",
        ((16.,0.,15.5),(0.,16.,15.5),(0.,0.,1.)),tuple(map(tuple,mount)),
        dict(action_id=1,terminal=False,collision=False,macro_id=seq,primitive_index=1,primitive_count=1),pose)
    rgb=np.zeros((32,32,3),np.uint8);depth=np.full((32,32),2.13,np.float32);mask=np.ones((32,32),bool)
    from graphAdapter.observation_pose.alignment import array_hash
    receipt=dict(committed=True,episode_uid=packet.episode_uid,frame_uid=packet.frame_uid,
        capture_seq=seq,env_step=seq-1,packet_event_seq=seq*10,calibration_hash=packet.calibration_hash,
        packet_record_hash=hashlib.sha256(canonical(packet.to_record())).hexdigest(),
        rgb_hash=array_hash(rgb),raw_depth_hash=array_hash(depth),
        alignment=dict(aligned_depth_hash=array_hash(depth),valid_mask_hash=hashlib.sha256(mask.tobytes()).hexdigest()))
    return packet,dict(rgb=rgb,raw_depth=depth,aligned_depth=depth,valid_mask=mask,committed_receipt=receipt,
                       host_view=rgb,host_transform={"kind":"identity"})

def test_G09_actual_service_full_rebuild_two_different_keyframes_matches_reference(tmp_path):
    from graphAdapter.map_memory.geometry.core import Q,S,A,TSDFSubmapManager
    from graphAdapter.map_memory.perception.scene import MemoryOnlyScene
    store=EpisodeStore(tmp_path/"memory","unit",dataset="r2r")
    try:
        original=dict(episode_id="unit",map_version=0,optimized_keyframes={"10":np.eye(4).tolist()})
        first,a1=bound_packet(1,10,original);s=seeded_service(store,first,a1);s.ingest(first,**a1)
        second_binding=json.loads(json.dumps(original))
        old20=np.eye(4);old20[1,3]=-3;second_binding["optimized_keyframes"]["20"]=old20.tolist()
        second,a2=bound_packet(2,20,second_binding);seed_camera(s,second,a2);s.ingest(second,**a2)
        old_reader=load_episode(store.root);old_pointer=(store.root/"CURRENT.json").read_bytes()
        k10=np.eye(4);k10[0,3]=.5
        k20=np.array([[0.,-1,0,0],[1,0,0,2],[0,0,1,0],[0,0,0,1]])
        corrected=dict(episode_id="unit",map_version=1,optimized_keyframes={
            "10":k10.tolist(),"20":k20.tolist(),"30":np.eye(4).tolist()})
        third,a3=bound_packet(3,30,corrected);seed_camera(s,third,a3)
        ready=s.prepare_endpoint(third,**a3)
        def fail(stage):
            if stage=="sqlite_prepared_committed":raise OSError("fail correction before visibility")
        with pytest.raises(OSError):s.publish_prepared(frame_uid=third.frame_uid,target_pose_map_version=1,fault=fail)
        assert s.version==0 and len(s.frames)==2 and old_pointer==(store.root/"CURRENT.json").read_bytes()
        with pytest.raises(VersionUnavailable):old_reader.require_pose_version("unit",1)
        assert old_reader.get_view(first.frame_uid)["pose_map_version"]==0
        ready=s.prepare_endpoint(third,**a3)
        s.publish_prepared(frame_uid=third.frame_uid,target_pose_map_version=1)
        assert s.version==1 and len(s.frames)==3
        current=load_episode(store.root)
        # Current corrected centre rays are analytical, not one shared global offset.
        from graphAdapter.map_memory.geometry.core import transform_points
        p1=transform_points(np.array([[0.,0.,2.]]),current.get_view(first.frame_uid)["T_G_cv"])[0]
        p2=transform_points(np.array([[0.,0.,2.]]),current.get_view(second.frame_uid)["T_G_cv"])[0]
        np.testing.assert_allclose(p1,[0,1.25,-3.5],atol=1e-5)
        np.testing.assert_allclose(p2,[-5,1.25,0],atol=1e-5)
        # Independently replay original source algorithms from empty with target per-frame poses.
        cfg,cg=config()
        refscene=MemoryOnlyScene(cfg,cg,models=None,camera_cache=s.camera,
            observations={p.frame_uid:args["rgb"]for p,args in ((first,a1),(second,a2),(third,a3))},
            epoch="cpu-full-reference",cache_only=True)
        refgeom=TSDFSubmapManager([0,0,0],backing=store,**s.geometry_options)
        for p,args in ((first,a1),(second,a2),(third,a3)):
            pose=p.to_record()["pose_record"]
            base=np.asarray(corrected["optimized_keyframes"][str(pose["rtab_keyframe_id"])])@np.asarray(pose["T_keyframe_base"])
            camera=Q@base@np.asarray(p.T_base_camera);base_g=Q@base;k=np.asarray(p.K)
            up=k.copy();up[1,2]=31-up[1,2]
            pos=base_g[:3,3];index=np.rint(A[:3,:3]@pos/refgeom.voxel_size)
            refscene.fuse(args["rgb"],args["aligned_depth"],up,camera@S,pos,index,p.frame_uid,frame_idx=p.capture_seq-1)
            refgeom.integrate(p.frame_uid,args["rgb"],args["aligned_depth"],args["valid_mask"],k,camera,
                              source_hash=store.raw(p.frame_uid)["raw_signature"])
        assert set(refgeom.records)==set(s.geometry.records)
        for key in refgeom.records:
            identity=refgeom.identifier(key)
            expected=refgeom.core_arrays(identity,snapshot_id="cpu-reference")["arrays"]
            actual=current.get_geometry(identity)["arrays"]
            for name in expected:np.testing.assert_array_equal(expected[name],actual[name])
        assert {frozenset(v)for v in refscene.members.values()}=={frozenset(v)for v in s.scene.members.values()}
        current.verify();old_reader.close();current.close()
    finally:store.close()

def test_G10_post_current_error_reconciles_memory_and_duplicate_is_not_reapplied(tmp_path):
    h,p,rgb,raw=inputs(tmp_path);store=EpisodeStore(tmp_path/"memory","unit",dataset="r2r")
    try:
        args=receipt_arrays(h,p,rgb,raw);s=seeded_service(store,p,args);s.ingest(p,**args)
        h.begin_macro(1,1);second=h.capture(rgb,raw,2,action_id=1,collision=False)
        a2=receipt_arrays(h,second,rgb,raw);seed_camera(s,second,a2)
        ready=s.prepare_endpoint(second,**a2)
        def fail(stage):
            if stage=="current_directory_fsynced":raise OSError("after linearization")
        with pytest.raises(OSError):
            s.publish_prepared(frame_uid=second.frame_uid,target_pose_map_version=ready["target_pose_map_version"],fault=fail)
        assert len(s.frames)==2 and second.frame_uid in s.graph["views"]
        before=(store.root/"CURRENT.json").read_bytes()
        assert s.ingest(second,**a2)["duplicate"]
        assert before==(store.root/"CURRENT.json").read_bytes()
    finally:store.close();h.close()


def test_G09_exact_unchanged_history_reuse_matches_full_rebuild_and_changed_pose_falls_back(tmp_path):
    import copy
    from graphAdapter.map_memory.storage.store import canonical
    stores=[EpisodeStore(tmp_path/name,"unit",dataset="r2r")for name in ("optimized","full")]
    original=dict(episode_id="unit",map_version=0,optimized_keyframes={"10":np.eye(4).tolist()})
    first,a1=bound_packet(1,10,original)
    services=[seeded_service(store,first,a1)for store in stores]
    services[0].correction_options={"reuse_exact_unchanged_history":True}
    try:
        for s in services:s.ingest(first,**a1)
        new=copy.deepcopy(original);new["map_version"]=1;new["optimized_keyframes"]["20"]=np.eye(4).tolist()
        for seq,key,binding in [(2,20,new),(3,20,dict(new,map_version=2,optimized_keyframes=dict(new["optimized_keyframes"],**{"10":(np.eye(4)+np.array([[0,0,0,.3],[0,0,0,0],[0,0,0,0],[0,0,0,0]])).tolist()})))]:
            packet,args=bound_packet(seq,key,binding)
            ready=[]
            for s in services:
                seed_camera(s,packet,args);ready.append(s.prepare_endpoint(packet,**args))
                s.publish_prepared(frame_uid=packet.frame_uid,target_pose_map_version=binding["map_version"])
            assert ready[0]["correction_strategy"]==("exact_unchanged_history_reuse"if seq==2 else"full_rebuild")
            assert ready[1]["correction_strategy"]=="full_rebuild"
            left,right=services
            # Epochs and aliases have storage ancestry identities;source object
            # state,point bytes,view poses and every owned voxel must be equal.
            ls,rs=copy.deepcopy(left.graph["scene_state"]),copy.deepcopy(right.graph["scene_state"])
            ls.pop("epoch");rs.pop("epoch")
            assert canonical(ls)==canonical(rs)
            assert set(left.geometry.records)==set(right.geometry.records)
            for tile in left.graph["tiles"]:
                x=left.geometry.core_arrays(tile,snapshot_id="test")["arrays"]
                y=right.geometry.core_arrays(tile,snapshot_id="test")["arrays"]
                for name in x:np.testing.assert_array_equal(x[name],y[name])
            for uid in left.graph["views"]:
                assert left.graph["views"][uid]["T_G_cv"]==right.graph["views"][uid]["T_G_cv"]
    finally:
        for store in stores:store.close()


def test_E05_report_verifies_every_published_historical_revision_and000source(tmp_path,tamper_page):
    from graphAdapter.evaluation.report import _audit_memory
    domain=tmp_path/"r2r"
    h=AwarePoseHook(domain/"worker/observation_pose",profile(),adapter_factory=adapter_factory)
    rgb=np.zeros((32,32,3),np.uint8);raw=np.ones((32,32),np.float32)
    first=h.reset("unit",sensor_spec(32),rgb,raw,1)
    store=EpisodeStore(domain/"worker/map_memory/episodes/r2r/opaque/attempt_000","unit",dataset="r2r")
    pointers=[]
    try:
        args=receipt_arrays(h,first,rgb,raw);s=seeded_service(store,first,args)
        for seq in (1,2):
            packet=first
            if seq==2:
                h.begin_macro(1,1);packet=h.capture(rgb,raw,2,action_id=1,collision=False)
                args=receipt_arrays(h,packet,rgb,raw);seed_camera(s,packet,args)
            result=s.ingest(packet,**args);pointers.append(result["snapshot_id"])
            h.coordinator.emit("PublishedSnapshot",frame_uid=packet.frame_uid,snapshot_id=result["snapshot_id"],
                versions=dict(pose_map_version=s.version),source_packet_event_seq=packet.event_seq,cutoff_event_seq=packet.event_seq)
        summary=dict(episode_uid="unit",snapshot_id=s.pointer["snapshot_id"],frames=2,eligible_endpoints=1,
            geometry_fused=sum(x["geometry_fused"]for x in s.graph["views"].values()if x["capture_seq"]>1),
            perception_complete=0)
        (store.root/"episode_summary.json").write_text(json.dumps(summary))
        candidate={("unit",):dict(scope=dict(episode_uid="unit"))}
        memory,errors=_audit_memory(domain,candidate)
        assert errors==[] and memory[0]["verified_history_revisions"]==2
        tamper_page(store.root,pointers[0],("graph",))
        with pytest.raises(IntegrityError):_audit_memory(domain,candidate)
    finally:store.close();h.close()


def test_G14_current_transition_index_does_not_copy_all_historical_epochs(tmp_path):
    store=EpisodeStore(tmp_path/"memory","unit",dataset="r2r")
    binding=dict(episode_id="unit",map_version=0,optimized_keyframes={"10":np.eye(4).tolist()})
    first,args=bound_packet(1,10,binding);s=seeded_service(store,first,args)
    s.correction_options={"reuse_exact_unchanged_history":True}
    first_reader=None
    try:
        first_epoch=None
        for seq in range(1,7):
            packet,args=bound_packet(seq,10,dict(binding,map_version=seq-1))
            if seq>1:seed_camera(s,packet,args)
            s.ingest(packet,**args)
            if seq==1:first_epoch=s.epoch;first_reader=load_episode(store.root)
            assert len({x["epoch"]for x in s.graph["entities"]})<=2
            # Original per-frame detection merges legitimately add aliases
            # inside the current epoch. Only copied older-epoch transitions
            # must stay bounded by the immediately preceding active objects.
            assert sum(x["epoch"]!=s.epoch for x in s.graph["aliases"])<=1
            assert {x["epoch"]for x in s.graph["aliases"]}<={x["epoch"]for x in s.graph["entities"]}
            assert all(not x["view_uids"]and not x["members"]for x in s.graph["entities"]if x["epoch"]!=s.epoch)
        current=load_episode(store.root)
        try:
            assert current.get_object(first_epoch,1)["epoch"]==s.epoch
            assert current.get_object(first_epoch,1)["attributes"]["num_detections"]==6
            assert first_reader.get_object(first_epoch,1)["attributes"]["num_detections"]==1
            assert store.pages.db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0]==6
            assert len(list((store.root/"detections").glob("*.meta.json")))==6
        finally:current.close()
    finally:
        if first_reader is not None:first_reader.close()
        store.close()


def test_G07_candidate_references_rejected_before_current_and_reader_checks_SQL(tmp_path,tamper_page):
    import copy
    h,p,rgb,raw=inputs(tmp_path);store=EpisodeStore(tmp_path/"memory","unit",dataset="r2r")
    try:
        args=receipt_arrays(h,p,rgb,raw);s=seeded_service(store,p,args);s.ingest(p,**args)
        old=(store.root/"CURRENT.json").read_bytes()
        broken=copy.deepcopy(s.graph)
        broken["scene_state"]["views"][p.frame_uid]["prompt"]["obj_id"]=[999]
        with pytest.raises(IntegrityError,match="semantic reference"):
            store.publish(broken,dict(pose_map_version=s.version),s.pointer["cutoff"])
        assert old==(store.root/"CURRENT.json").read_bytes()
        current=load_episode(store.root)
        try:
            assert current.verify()["reference_checks"]["errors"]==[]
            tamper_page(store.root,s.pointer["snapshot_id"],("graph","scene_state","views",p.frame_uid))
            with pytest.raises(IntegrityError):current.verify()
        finally:current.close()
    finally:store.close();h.close()

def test_G07_cached_camera_facts_reject_changed_model_preprocessing_identity(tmp_path):
    from graphAdapter.map_memory.service import CameraDetectionArchive
    h,p,rgb,raw=inputs(tmp_path);store=EpisodeStore(tmp_path/"memory","unit",dataset="r2r")
    try:
        args=receipt_arrays(h,p,rgb,raw);s=seeded_service(store,p,args)
        other=CameraDetectionArchive(store,dict(scope="cpu_contract",preprocess_hash="different_RGB_API"))
        with pytest.raises(IntegrityError,match="provenance"):other[p.frame_uid]
    finally:store.close();h.close()
