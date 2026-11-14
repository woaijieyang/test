from dataclasses import replace
from types import SimpleNamespace
from threading import RLock
import copy
import numpy as np
import pytest
from poseAdapter.pose_types import PoseEstimate
from poseAdapter.pose_adapter import PoseAdapter
from poseAdapter.graph_sync.keyframe_binding import KeyframeBindingStore
from poseAdapter.interfaces.mapping import measured_mapping_sample, MappingChart

def sample(n=1, version=0, x=0., correction=None, instance="attempt-a", epoch=0, latest=True):
    odom=np.eye(4);odom[0,3]=x
    correction=np.eye(4) if correction is None else correction
    support=dict(timestamp_ns=n,kind=2,detected=70,used=50,prediction_used=False)
    diagnostics=dict(measurement_support=support,
        global_frame_link=dict(verified=True,episode_id="episode",epoch=epoch),
        odometry_frame_link=np.eye(4).tolist())
    pose=PoseEstimate("episode",f"frame{n}",n,T_odom_base=odom,T_map_base=correction@odom,
        valid=True,tracking_state="tracking",source="cuvslam_rtabmap_rgbd",
        map_version=version,diagnostics=diagnostics)
    binding=dict(episode_id="episode",map_version=version,T_map_odom=correction.tolist(),optimized_keyframes={})
    value=measured_mapping_sample(pose,binding,latest_frame_id=pose.frame_id if latest else "other",
        episode_instance=instance)
    return value,pose,binding

def receipt(value,**changes):
    result=dict(committed=True,snapshot_id="a"*64,episode_id=value.episode_id,
        episode_instance=value.episode_instance,frame_id=value.frame_id,
        timestamp_ns=value.timestamp_ns,target_map_version=value.native_map_version,
        bindings_sha256=value.binding_digest)
    result.update(changes);return result

def test_real_public_pose_estimate_mapping_api():
    value,pose,binding=sample()
    assert "geometry_status" not in pose.to_record()
    adapter=object.__new__(PoseAdapter)
    adapter._publication_lock=RLock()
    adapter._get_pose_for_frame=lambda *a,**kw:pose
    adapter._buffer=SimpleNamespace(latest=lambda:pose)
    adapter.spatial_bindings=lambda:copy.deepcopy(binding)
    adapter._episode_instance="attempt-a"
    assert adapter.get_mapping_frame_snapshot(pose.frame_id,timestamp_ns=1)==value

def test_continuous_append_and_committed_noncommuting_correction():
    first,_,_=sample();chart=MappingChart.from_sample(first)
    c=np.array([[0.,-1,0,4],[1,0,0,2],[0,0,1,0],[0,0,0,1]])
    next_sample,_,_=sample(2,1,1.,c)
    before=chart.project(next_sample)
    np.testing.assert_array_equal(np.asarray(before["T_map_base"])[:3,3],[1,0,0])
    with pytest.raises(ValueError):chart.after_committed_correction(next_sample,receipt(next_sample,committed=False))
    with pytest.raises(ValueError):chart.after_committed_correction(next_sample,receipt(next_sample,bindings_sha256="b"*64))
    assert chart.applied_map_version==0
    updated=chart.after_committed_correction(next_sample,receipt(next_sample))
    np.testing.assert_array_equal(np.asarray(updated.project(next_sample)["T_map_base"])[:3,3],[4,3,0])
    assert updated.applied_map_version==1 and chart.applied_map_version==0
    with pytest.raises(ValueError):chart.project(sample(3,1,instance="reset-b")[0])
    with pytest.raises(ValueError):chart.project(sample(3,1,epoch=1)[0])

@pytest.mark.parametrize("mode",["timestamp","counts","epoch","episode","link"])
def test_bad_native_provenance_rejected(mode):
    _,pose,binding=sample()
    d=copy.deepcopy(pose.diagnostics)
    if mode=="timestamp":d["measurement_support"]["timestamp_ns"]=99
    if mode=="counts":d["measurement_support"]["used"]=100
    if mode=="epoch":d["global_frame_link"]["epoch"]=None
    if mode=="episode":d["global_frame_link"]["episode_id"]="other"
    if mode=="link":d["odometry_frame_link"]=None
    with pytest.raises((ValueError,RuntimeError)):
        measured_mapping_sample(replace(pose,diagnostics=d),binding,latest_frame_id=pose.frame_id,episode_instance="attempt-a")

def test_held_and_historical_samples_are_not_accepted_as_new_chart():
    _,pose,binding=sample()
    assert measured_mapping_sample(replace(pose,valid=False),binding,latest_frame_id=pose.frame_id,episode_instance="attempt-a") is None
    c=np.eye(4);c[0,3]=.1
    _,pose,binding=sample(2,1,1.,c)
    mapped=pose.T_map_base.copy();mapped[1,3]=5
    historical=measured_mapping_sample(replace(pose,T_map_base=mapped),binding,latest_frame_id="later",episode_instance="attempt-a")
    np.testing.assert_array_equal(historical.T_map_odom,c)
    with pytest.raises(ValueError):MappingChart.from_sample(historical)

def test_native_correction_export_transaction_identity():
    g=KeyframeBindingStore("episode")
    t=np.eye(4)
    update=dict(episode_id="episode",map_version=0,T_map_odom=t.tolist(),optimized_keyframes={"1":t.tolist()})
    next_g=g.proposed_update(update)
    assert "T_map_odom" not in g.snapshot()
    np.testing.assert_array_equal(next_g.snapshot()["T_map_odom"],t)
    update["T_map_odom"][0][3]=1
    with pytest.raises(ValueError):next_g.proposed_update(update)
    np.testing.assert_array_equal(next_g.snapshot()["T_map_odom"],t)
