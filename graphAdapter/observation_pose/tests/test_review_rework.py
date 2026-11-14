"""Independent counterexamples for reviewed stage000 production contracts."""
import json
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest
from poseAdapter import PoseAdapter,PoseEstimate,DepthSpec
from graphAdapter.observation_pose.pose_bridge import PoseBridge
from graphAdapter.observation_pose.aware_hook import AwarePoseHook
from graphAdapter.observation_pose.host_wiring import reset_from_environment
from graphAdapter.observation_pose.tests.suite import aligned,cal
from graphAdapter.observation_pose.tests.fixtures import sensor_spec,adapter_factory
from graphAdapter.observation_pose.alignment import array_hash
from graphAdapter.observation_packet import geometry_input,perception_input,require_same_frame
from case1_runtime.episode_scope import episode_scope

PROFILE=Path(__file__).parents[1]/"profiles/000_pose_shadow.json"
def profile():return json.loads(PROFILE.read_text())
def new_hook(tmp_path):
    return AwarePoseHook(tmp_path/"hook",profile(),adapter_factory=adapter_factory)
def start(hook):
    return hook.reset("unit",sensor_spec(),np.zeros((8,8,3),np.uint8),np.ones((8,8),np.float32),1)

@pytest.mark.parametrize("episode,version",[("other",1),("unit",2)])
def test_mixed_binding_snapshot_rejected(episode,version):
    class Mixed:
        def get_pose_for_frame(self,f,**kw):
            return PoseEstimate("unit",f,1,T_odom_base=np.eye(4),T_map_base=np.eye(4),valid=True,
                source="cuvslam_rtabmap_rgbd",tracking_state="tracking",map_version=1)
        def spatial_bindings(self):return {"episode_id":episode,"map_version":version}
    bridge=PoseBridge(None,None,cal(),adapter=Mixed(),aligned_depth_spec=DepthSpec("meters","z","float32",0,10))
    bridge.episode_uid="unit"
    with pytest.raises(ValueError,match="snapshot episode/version"):bridge.get_mapping_pose("unit:f",1)

def test_published_keyframe_geometry_not_just_labels_is_checked():
    class Wrong:
        def get_pose_for_frame(self,f,**kw):
            return PoseEstimate("unit",f,1,T_odom_base=np.eye(4),T_map_base=np.eye(4),valid=True,
                source="cuvslam_rtabmap_rgbd",tracking_state="tracking",map_version=0,
                rtab_keyframe_id=1,T_keyframe_base=np.eye(4),diagnostics={"measurement_support":{"kind":2,"used":1,"prediction_used":False}})
        def spatial_bindings(self):
            matrix=np.eye(4);matrix[0,3]=10
            return dict(episode_id="unit",map_version=0,optimized_keyframes={"1":matrix.tolist()})
    bridge=PoseBridge(None,None,cal(),adapter=Wrong(),aligned_depth_spec=DepthSpec("meters","z","float32",0,10))
    bridge.episode_uid="unit"
    with pytest.raises(ValueError,match="keyframe geometry"):bridge.get_mapping_pose("unit:f",1)

@pytest.mark.parametrize("kind",["depth","declared_hash","mask","source","registration","camera"])
def test_duplicate_full_aligned_product_rejected_before_integration(kind):
    adapter=PoseAdapter()
    bridge=PoseBridge(None,None,cal(),adapter=adapter,aligned_depth_spec=DepthSpec("meters","z","float32",0,10))
    bridge.reset("unit");value=aligned()
    try:
        bridge.ingest("unit:f",1,value)
        changed=value
        if kind=="depth":
            depth=np.full_like(value.depth,2);changed=replace(value,depth=depth,aligned_depth_hash=array_hash(depth))
        if kind=="declared_hash":changed=replace(value,aligned_depth_hash="different")
        if kind=="mask":changed=replace(value,valid_mask=np.zeros_like(value.valid_mask))
        if kind=="source":changed=replace(value,source_pixel_map=np.zeros_like(value.source_pixel_map))
        if kind=="registration":changed=replace(value,calibration_hash="changed")
        if kind=="camera":bridge.calibration=replace(bridge.calibration,cx=2.)
        with pytest.raises(ValueError):bridge.ingest("unit:f",1,changed)
        assert len(bridge.frames)==1 and adapter.get_status()["buffered_frames"]==1
    finally:bridge.shutdown()

def test_initial_bad_calibration_archives_rgb_depth_and_unavailable_packet(tmp_path):
    hook=AwarePoseHook(tmp_path/"bad",profile())
    try:
        rgb=np.zeros((8,8,3),np.uint8);depth=np.ones((8,8),np.float32)
        packet=hook.reset("bad",{"rgb":{}},rgb,depth,1)
        assert packet.pose_record["geometry_status"]=="unavailable"
        assert packet.pose_record["T_map_camera_cv"] is None
        np.testing.assert_array_equal(np.load(packet.raw_rgb_ref),rgb)
        np.testing.assert_array_equal(np.load(packet.raw_depth_ref),depth)
        assert packet.failure_reason
        rows=[json.loads(s) for s in (hook.coordinator.root/"flow_trace.jsonl").read_text().splitlines()]
        assert [x["kind"] for x in rows][:2]==["reset","raw_archive"]
        assert any(x.get("stage")=="calibration" for x in rows)
    finally:hook.close()

@pytest.mark.parametrize("failed_method",["graph_static_sensor_spec","graph_raw_depth_endpoint"])
def test_actual_host_reset_wiring_preserves_rgb_on_sensor_error(tmp_path,failed_method):
    class Envs:
        def call_at(self,index,name):
            if name==failed_method:raise KeyError("injected-"+name)
            if name=="graph_static_sensor_spec":return sensor_spec()
            if name=="graph_raw_depth_endpoint":
                return dict(depth=np.ones((8,8),np.float32),capture_monotonic_ns=1,collision=False)
            raise AssertionError(name)
    hook=AwarePoseHook(tmp_path/"wired",profile())
    try:
        packet=reset_from_environment(hook,Envs(),0,{"rgb":np.zeros((8,8,3),np.uint8)},{"episode_uid":"wired"})
        assert Path(packet.raw_rgb_ref).is_file()
        assert packet.pose_record["geometry_status"]=="unavailable"
        assert failed_method in packet.failure_reason
    finally:hook.close()

def test_macro_terminal_alignment_failure_always_clears_authorization(tmp_path):
    hook=new_hook(tmp_path);start(hook)
    try:
        hook.begin_macro(2,2)
        hook.capture(np.zeros((8,8,3),np.uint8),np.ones((8,8),np.float32),2,action_id=2)
        hook.pose.execution.authorized=2
        hook.pose.adapter._recovery.authorized_action="turn_left"
        with patch.object(hook.align,"align",side_effect=ValueError("terminal-alignment-fault")):
            packet=hook.capture(np.zeros((8,8,3),np.uint8),np.ones((8,8),np.float32),3,action_id=2)
        assert hook.macro is None and hook.pose.execution.authorized is None
        assert hook.pose.adapter._recovery.authorized_action is None
        assert packet.pose_record["geometry_status"]=="unavailable"
    finally:hook.close()

def test_shutdown_error_keeps_episode_identity_and_terminal_last(tmp_path):
    hook=new_hook(tmp_path);start(hook);adapter=hook.pose.adapter
    with patch.object(hook.pose,"shutdown",side_effect=RuntimeError("shutdown-fault")):
        hook.end_episode([])
    hook.close();adapter.shutdown()
    rows=[json.loads(s) for s in (hook.coordinator.root/"flow_trace.jsonl").read_text().splitlines()]
    error=next(x for x in rows if x["kind"]=="pose_shutdown_error")
    assert error["episode_uid"]=="unit" and error["frame_uid"].startswith("unit:")
    assert rows[-1]["kind"]=="terminal" and rows[-1]["episode_uid"]=="unit"

def test_two_real_input_ports_reject_frame_calibration_and_version_mix(tmp_path):
    hook=new_hook(tmp_path)
    try:
        first=start(hook);second=hook.capture(np.zeros((8,8,3),np.uint8),np.ones((8,8),np.float32),2,action_id=1)
        a=geometry_input(first);b=perception_input(first)
        require_same_frame(a,b)
        for changed in (perception_input(second),replace(b,pose_map_version=2),replace(b,K=((1.,0.,0.),)*3)):
            with pytest.raises(ValueError):require_same_frame(a,changed)
        with pytest.raises(TypeError):first.pose_record["spatial_bindings"]["map_version"]=2
    finally:hook.close()

def test_unique_full_identity_across_domains_runs_attempts_and_members():
    ep=SimpleNamespace(scene_id="/root/mp3d/scan/scan.glb",episode_id="115",
                       instruction=SimpleNamespace(instruction_id="i1"))
    first=episode_scope(ep,run_uid="r",attempt_id="a0",dataset="r2r")
    alternatives=[
      episode_scope(ep,run_uid="r",attempt_id="a0",dataset="rxr_us"),
      episode_scope(ep,run_uid="r2",attempt_id="a0",dataset="r2r"),
      episode_scope(ep,run_uid="r",attempt_id="a1",dataset="r2r"),
      episode_scope(SimpleNamespace(scene_id=ep.scene_id,episode_id="115",
          instruction=SimpleNamespace(instruction_id="i2")),run_uid="r",attempt_id="a0",dataset="r2r")]
    assert len({first["episode_uid"],*(x["episode_uid"]for x in alternatives)})==5
    assert first["member"][-1]=="i1"

def test_actual_trainer_batches_only_whitelisted_policy_inputs():
    import ast
    path=Path(__file__).resolve().parents[3]/"vlnce_baselines/awarevln_trainer.py"
    tree=ast.parse(path.read_text())
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="batch_obs"]
    assert len(calls)==2 and all(isinstance(n.args[0],ast.Name) and n.args[0].id=="policy_inputs" for n in calls)
    assert '"attempt0-" + str' not in path.read_text()
