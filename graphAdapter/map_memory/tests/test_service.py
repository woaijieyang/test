"""Correction and execution semantics use actual public contract shapes;CPU fixtures."""
from pathlib import Path
import copy,numpy as np,pytest
from graphAdapter.map_memory.service import GraphMapCorrectionConsumer,execution_relation,cross_revision_entities
from graphAdapter.map_memory.geometry.core import transform_points
from graphAdapter.map_memory.storage.store import VersionUnavailable,IntegrityError
from poseAdapter.coordinate.frames import OPTICAL_TO_FLU

def capture(seq,key=10):
    mount=np.eye(4);mount[:3,:3]=OPTICAL_TO_FLU;mount[:3,3]=[0,0,1.25]
    relative=np.eye(4);relative[0,3]=1
    pose=dict(episode_id="e",frame_id="e:f"+str(seq),timestamp_ns=seq,valid=True,
        geometry_status="available",source="cuvslam_rtabmap_rgbd",tracking_state="tracking",map_version=1,
        T_odom_base=np.eye(4).tolist(),rtab_keyframe_id=key,T_keyframe_base=relative.tolist(),
        diagnostics=dict(measurement_support=dict(kind=2,used=50,prediction_used=False),
            global_frame_link=dict(verified=True,epoch=0),odometry_frame_link=np.eye(4).tolist()))
    return dict(episode_uid="e",frame_uid=pose["frame_id"],capture_seq=seq,pose_record=pose,T_base_camera=mount.tolist(),
        action=dict(action_id=1,collision=False,terminal=False))

def test_G09_two_keyframes_get_different_actual_corrections_not_one_offset():
    first=capture(1,10);second=capture(2,20)
    k10=np.eye(4);k10[0,3]=.5
    k20=np.array([[0.,-1,0,0],[1,0,0,2],[0,0,1,0],[0,0,0,1]])
    bindings=dict(episode_id="e",map_version=2,optimized_keyframes={"10":k10.tolist(),"20":k20.tolist()})
    consumer=GraphMapCorrectionConsumer("e")
    original=copy.deepcopy([first,second])
    corrected=consumer.prepare([first,second],bindings)
    p1=transform_points(np.array([[0,0,2.]]),corrected[first["frame_uid"]]["T_G_cv"])[0]
    p2=transform_points(np.array([[0,0,2.]]),corrected[second["frame_uid"]]["T_G_cv"])[0]
    np.testing.assert_allclose(p1,[0,1.25,-3.5],atol=1e-5)
    np.testing.assert_allclose(p2,[-5,1.25,0],atol=1e-5)
    assert [first,second]==original
    assert corrected[first["frame_uid"]]["binding"]["pose_map_version"]==2
    assert corrected[second["frame_uid"]]["binding"]["keyframe_id"]==20

def test_G09_missing_keyframe_invalid_history_and_public_hold_are_not_guessed():
    c=capture(1);consumer=GraphMapCorrectionConsumer("e")
    binding=dict(episode_id="e",map_version=2,optimized_keyframes={})
    with pytest.raises(VersionUnavailable):consumer.resolve(c,binding)
    invalid=copy.deepcopy(c);invalid["pose_record"]["geometry_status"]="unavailable"
    assert consumer.resolve(invalid,binding)is None
    binding["optimized_keyframes"]["10"]=np.eye(4).tolist()
    def held(record):return dict(record,valid=False,map_version=2)
    with pytest.raises(VersionUnavailable):consumer.resolve(c,binding,restore_estimate=held)

@pytest.mark.parametrize("kind",["turn","collision","gap","chart","link","map_only"])
def test_G08_temporal_is_not_navigability_for_turn_collision_gap_or_map_correction(kind):
    a=capture(1);b=capture(2)
    camera=np.eye(4);camera[0,3]=2
    b["pose_record"]["T_map_camera_cv"]=camera.tolist()
    if kind=="turn":b["action"]["action_id"]=2
    if kind=="collision":b["action"]["collision"]=True
    if kind=="gap":b["pose_record"]["valid"]=False
    if kind=="chart":b["pose_record"]["diagnostics"]["global_frame_link"]["epoch"]=1
    if kind=="link":
        link=np.eye(4);link[0,3]=1;b["pose_record"]["diagnostics"]["odometry_frame_link"]=link.tolist()
    if kind=="map_only":b["pose_record"]["map_version"]=99
    result=execution_relation(a,b)
    assert result["temporal"]["type"]=="temporal_next" and result["traversed"]is None

def test_G08_actual_forward_base_odom_only_gives_recorded_direction():
    a=capture(1);b=capture(2)
    odom=np.eye(4);odom[0,3]=.25;b["pose_record"]["T_odom_base"]=odom.tolist()
    b["pose_record"]["map_version"]=99
    result=execution_relation(a,b)
    assert result["traversed"]["src"]==a["frame_uid"] and result["traversed"]["dst"]==b["frame_uid"]
    assert result["traversed"]["direction"]=="recorded_only" and result["traversed"]["current_passability"]=="unknown"
    assert result["traversed"]["straight_shortcut"]is False

def test_G09_cross_revision_ids_follow_detection_members_and_mark_split_ambiguous():
    old=[dict(epoch="old",id=1,status="active",members=["f1:d0","f2:d0"])]
    new=[dict(epoch="new",id=1,status="active",members=["f1:d0"]),
         dict(epoch="new",id=2,status="active",members=["f2:d0"])]
    relation=cross_revision_entities(old,new)[0]
    assert relation["status"]=="ambiguous" and len(relation["candidates"])==2
    new=[dict(epoch="new",id=99,status="active",members=["f1:d0","f2:d0","f3:d0"])]
    relation=cross_revision_entities(old,new)[0]
    assert relation["status"]=="alias" and relation["dst"]==99 and relation["dst_epoch"]=="new"


def test_G09_live_client_coalesces_new_target_and_commits_only_latest():
    from graphAdapter.map_memory.worker import MemoryWorkerClient
    from types import SimpleNamespace
    p=SimpleNamespace(episode_uid="e",frame_uid="e:f1",sensor_timestamp_ns=1,capture_seq=1,event_seq=10,
        pose_provider="cuvslam_rtabmap_rgbd",
        to_record=lambda:{"pose_record":{"spatial_bindings":{"map_version":0}}})
    client=MemoryWorkerClient.__new__(MemoryWorkerClient)
    client.active_episode="e";client.count=0;calls=[]
    def call(message):
        calls.append(message)
        if message["op"]=="prepare":
            version=message["bindings"]["map_version"]
            return {"result":{"duplicate":False,"target_pose_map_version":version,"candidate_hash":str(version)}}
        return {"result":{"snapshot_id":"latest","versions":{"pose_map_version":message.get("target_pose_map_version")},"cutoff":{"capture_seq":1,"event_seq":10}}}
    client.call=call
    versions=iter([0,1,1,1])
    adapter=SimpleNamespace(get_frame_snapshot=lambda *a,**k:(None,{"map_version":next(versions)}))
    result=client.consume(p,{"committed":True},pose_adapter=adapter)
    assert result["snapshot_id"]=="latest"and client.count==1
    assert [x["op"]for x in calls]==["prepare","cancel","prepare","commit"]
    assert calls[-1]["target_pose_map_version"]==1 and calls[-1]["candidate_hash"]=="1"

def test_G09_live_client_never_commits_an_unstable_pose_target():
    from graphAdapter.map_memory.worker import MemoryWorkerClient
    from types import SimpleNamespace
    p=SimpleNamespace(episode_uid="e",frame_uid="e:f1",sensor_timestamp_ns=1,capture_seq=1,event_seq=10,
        pose_provider="cuvslam_rtabmap_rgbd",
        to_record=lambda:{"pose_record":{"spatial_bindings":None}})
    client=MemoryWorkerClient.__new__(MemoryWorkerClient)
    client.active_episode="e";client.count=0;calls=[]
    def call(message):
        calls.append(message)
        return {"result":{"duplicate":False,"target_pose_map_version":message.get("bindings",{}).get("map_version"),"candidate_hash":"x"}}
    client.call=call
    versions=iter(range(16))
    adapter=SimpleNamespace(get_frame_snapshot=lambda *a,**k:(None,{"map_version":next(versions)}))
    with pytest.raises(RuntimeError,match="did not stabilize"):client.consume(p,{},pose_adapter=adapter)
    assert not any(x["op"]=="commit"for x in calls)and client.count==0


def test_G11_broker_rejects_nonempty_or_overlapping_output_mounts(tmp_path,monkeypatch):
    from graphAdapter.map_memory import worker
    root=tmp_path/"case";monkeypatch.setattr(worker,"ROOT",root)
    source=root/"outputs/graph_memory/source/observation_pose";source.mkdir(parents=True)
    session=root/"runtime/graph_memory/sessions/new";session.mkdir(parents=True)
    existing=root/"outputs/graph_memory/existing";existing.mkdir();(existing/"sentinel").write_text("unrelated existing file")
    with pytest.raises(ValueError,match="new empty"):worker.isolated_command(session,source,existing)
    with pytest.raises(ValueError,match="new empty"):worker.isolated_command(session,source,root/"outputs/graph_memory")
    assert (existing/"sentinel").read_text()=="unrelated existing file"
