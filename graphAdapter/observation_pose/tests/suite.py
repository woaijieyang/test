"""P00-P11 executable stage-000 contracts. Native deployment is reported separately."""
import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from poseAdapter.coordinate.calibration import Calibration, DepthSpec
from poseAdapter.pose_adapter import PoseAdapter
from poseAdapter.pose_types import PoseEstimate
from case1_runtime.observations import policy_observations
from graphAdapter.observation_packet import geometry_input,perception_input,require_same_frame
from .fixtures import sensor_spec,adapter_factory
from graphAdapter.observation_pose.alignment import RGBDAlignmentBridge, intrinsic
from graphAdapter.observation_pose.coordinator import Coordinator
from graphAdapter.observation_pose.pose_bridge import PoseBridge, PoseExecutionBridge

def cal(w=8,h=8,cx=None):
    return Calibration(w,h,w/2,h/2,(w-1)/2 if cx is None else cx,(h-1)/2,np.eye(4))

def aligned():
    c=cal()
    return RGBDAlignmentBridge(c,c,DepthSpec("meters","z","float32",0,10),np.eye(4)).align(
        np.zeros((8,8,3),np.uint8),np.ones((8,8),np.float32))

class Contracts(unittest.TestCase):
    def test_P00_capture_decision_primitive_terminal_reset(self):
        with tempfile.TemporaryDirectory() as d:
            c=Coordinator(Path(d)/"capture")
            c.reset("attempt0-one")
            a=aligned()
            c.capture(a.rgb,a.depth,1)
            first=c.frame_uid
            c.decision();c.decision()
            self.assertEqual(c.frame_uid,first)
            self.assertEqual((c.capture_seq,c.env_step,c.decision_id),(1,0,2))
            c.capture(a.rgb,a.depth,2,action_id=1,macro_id=1,primitive_index=1,primitive_count=3)
            c.capture(a.rgb,a.depth,3,action_id=1,terminal=True,macro_id=1,primitive_index=2,primitive_count=3)
            c.end_episode([1])
            c.reset("attempt0-two");c.capture(a.rgb,a.depth,4)
            self.assertEqual((c.env_step,c.decision_id,c.capture_seq),(0,0,1))
            c.end_episode();c.close()
            rows=[json.loads(x) for x in (Path(d)/"capture/flow_trace.jsonl").read_text().splitlines()]
            self.assertEqual([x["event_seq"] for x in rows],list(range(1,len(rows)+1)))
            self.assertEqual([x["cancelled_actions"] for x in rows if x["kind"]=="terminal"],[[1],[]])

    def test_P01_noncentral_512_256_ray_mapping(self):
        rgb=cal(512,512,cx=249.25)
        depth=Calibration(256,256,128,128,(rgb.cx+.5)/2-.5,127.5,np.eye(4))
        y,x=np.indices((256,256))
        z=(2/(1+.1*(x-depth.cx)/depth.fx)).astype(np.float32)
        a=RGBDAlignmentBridge(rgb,depth,DepthSpec("meters","z","float32",0,10),np.eye(4)).align(
            np.zeros((512,512,3),np.uint8),z)
        dy,dx=a.source_pixel_map[:,:,0],a.source_pixel_map[:,:,1]
        v,u=np.indices((512,512))
        rays=intrinsic(depth)@np.linalg.inv(intrinsic(rgb))@np.stack([u.ravel(),v.ravel(),np.ones(u.size)])
        valid=a.valid_mask.ravel()
        error=np.maximum(np.abs(dx.ravel()[valid]-rays[0,valid]),np.abs(dy.ravel()[valid]-rays[1,valid]))*2
        self.assertLessEqual(float(error.max()),1.000001)
        self.assertTrue(np.array_equal(a.depth[a.valid_mask],z[dy[a.valid_mask],dx[a.valid_mask]]))

    def test_P02_extrinsic_zbuffer_and_holes(self):
        d=Calibration(2,1,1,1,0,0,np.eye(4))
        r=Calibration(4,2,.1,.1,0,0,np.eye(4))
        T=np.eye(4);T[0,3]=.01
        a=RGBDAlignmentBridge(r,d,DepthSpec("meters","z","float32",0,10),T).align(
            np.zeros((2,4,3),np.uint8),np.array([[2,1]],np.float32))
        self.assertEqual(a.depth[0,0],1.)
        self.assertEqual(int(a.valid_mask.sum()),1)
        self.assertTrue(np.all(a.source_pixel_map[~a.valid_mask]==-1))

    def test_P03_units_range_nan_zero_sentinel(self):
        c=cal()
        raw=np.full((8,8),.5,np.float32)
        raw[0,:4]=[0,np.nan,-99,1]
        bridge=RGBDAlignmentBridge(c,c,DepthSpec("normalized","range","float32",.1,10),np.eye(4),
                                  invalid_values=(0.,-99.))
        a=bridge.align(np.zeros((8,8,3),np.uint8),raw)
        self.assertTrue(np.all(a.depth[0,:3]==0))
        self.assertEqual(int(a.valid_mask.sum()),61)
        self.assertTrue(np.isfinite(a.depth).all())
        original=DepthSpec("meters","z","float32",0,100).metric_copy(a.depth,c)
        self.assertTrue(np.array_equal(original,a.depth))
        near=RGBDAlignmentBridge(c,c,DepthSpec("normalized","z","float32",.1,10),np.eye(4))
        self.assertAlmostEqual(float(near.align(a.rgb,np.zeros((8,8),np.float32)).depth[0,0]),.1,places=6)

    def test_P04_declared_backend_and_no_shadow_mapping(self):
        from poseAdapter.pose_config import PoseConfig
        for mode in ("original","cuvslam","cuvslam_shadow","cuvslam_rtabmap"):
            self.assertEqual(PoseConfig(pose_backend=mode).pose_backend,mode)
        with self.assertRaises(ValueError):PoseConfig(pose_backend="unknown")
        class Fake:
            def __init__(self,source):self.source=source
            def get_pose_for_frame(self,f,**kw):
                return PoseEstimate("e",f,1,T_odom_base=np.eye(4),T_map_base=np.eye(4),
                    valid=True,tracking_state="tracking",source=self.source,rtab_keyframe_id=1,T_keyframe_base=np.eye(4),diagnostics={"measurement_support":{"kind":2,"used":1,"prediction_used":False}})
            def spatial_bindings(self):
                return {"episode_id":"e","map_version":0,"optimized_keyframes":{"1":np.eye(4).tolist()}} if self.source=="cuvslam_rtabmap_rgbd" else None
        for source,expected in [("original_action_odometry","unavailable"),("cuvslam_rgbd","unavailable"),
                                ("cuvslam_rtabmap_rgbd","available")]:
            p=PoseBridge(None,None,cal(),adapter=Fake(source),aligned_depth_spec=DepthSpec("meters","z","float32",0,10));p.episode_uid="e"
            self.assertEqual(p.get_mapping_pose("e:f",1)["geometry_status"],expected)

    def test_P05_repeats_mismatch_order_and_changed_pixels(self):
        adapter=PoseAdapter(SimpleNamespace(turn_degrees=15,forward_step=.25),{"pose_backend":"original"})
        p=PoseBridge(None,None,cal(),adapter=adapter,aligned_depth_spec=DepthSpec("meters","z","float32",0,10))
        p.reset("e")
        a=aligned()
        first=p.ingest("e:f1",1,a)
        self.assertEqual(p.ingest("e:f1",1,a),first)
        with self.assertRaises(ValueError):p.ingest("wrong:f2",2,a)
        with self.assertRaises(ValueError):p.ingest("e:f2",0,a)
        from dataclasses import replace
        with self.assertRaises(ValueError):p.ingest("e:f1",1,replace(a,raw_rgb_hash="changed"))
        p.shutdown()

    def test_P06_single_immutable_consumer_product(self):
        from graphAdapter.observation_pose.aware_hook import AwarePoseHook
        with tempfile.TemporaryDirectory() as d:
            profile=json.loads((Path(__file__).parents[1]/"profiles/000_pose_shadow.json").read_text())
            hook=AwarePoseHook(Path(d)/"ports",profile,adapter_factory=adapter_factory)
            try:
                packet=hook.reset("unit-p06",sensor_spec(),np.zeros((8,8,3),np.uint8),np.ones((8,8),np.float32),1)
                geometry=hook.latest_geometry_input;perception=hook.latest_perception_input
                self.assertIsNot(geometry,perception)
                self.assertEqual(require_same_frame(geometry,perception),geometry.frame_key)
                self.assertEqual(geometry.K,packet.K)
                self.assertEqual(geometry.pose_map_version,packet.pose_record["map_version"])
                self.assertEqual(geometry.T_map_camera_cv,packet.pose_record["T_map_camera_cv"])
                with self.assertRaises(TypeError):packet.pose_record["map_version"]=99
                second=hook.capture(np.zeros((8,8,3),np.uint8),np.ones((8,8),np.float32),2,action_id=1)
                with self.assertRaises(ValueError):require_same_frame(geometry,perception_input(second))
            finally:hook.close()

    def test_P07_invalid_pose_has_no_stale_geometry(self):
        class Fake:
            def get_pose_for_frame(self,f,**kw):return PoseEstimate("e",f,1,source="cuvslam_rtabmap_rgbd",
                tracking_state="unobservable",reason="measurement gap")
            def spatial_bindings(self):return None
        p=PoseBridge(None,None,cal(),adapter=Fake(),aligned_depth_spec=DepthSpec("meters","z","float32",0,10));p.episode_uid="e"
        row=p.get_mapping_pose("e:f1",1)
        self.assertEqual(row["geometry_status"],"unavailable")
        self.assertIsNone(row["T_map_camera_cv"])
        with self.assertRaises(ValueError):p.get_mapping_pose("e:f1",2)

    def test_P08_exact_authorized_30_macro(self):
        class Fake:
            def __init__(self):self.calls=[]
            def recovery_status(self):return {"active":True}
            def authorize_tracking_recovery(self,direction):self.calls.append(direction)
            def end_tracking_recovery_attempt(self):self.calls.append("ended")
        f=Fake();p=PoseExecutionBridge(f)
        for count in (1,3):
            p.begin_macro(2,count)
            self.assertIsNone(p.pose_action(2,count,count))
        self.assertEqual(f.calls,[])
        p.begin_macro(2,2)
        self.assertIsNone(p.pose_action(2,1,2))
        self.assertEqual(p.pose_action(2,2,2),"turn_left")
        p.end_macro()
        self.assertEqual(f.calls,["left","ended"])

    def test_P09_oracle_extra_fields_rejected(self):
        from graphAdapter.observation_pose.aware_hook import AwarePoseHook
        from graphAdapter.observation_pose.host_wiring import reset_from_environment
        class Observation(dict):
            def __getitem__(self,key):
                if key!="rgb":raise AssertionError("Forbidden observation access: "+key)
                return super().__getitem__(key)
            def __iter__(self):raise AssertionError("Observation enumeration forbidden")
            def items(self):raise AssertionError("Observation enumeration forbidden")
        rgb=np.zeros((8,8,3),np.uint8)
        observation=Observation(rgb=rgb,goal=object(),infos=object(),gps=object(),progress=object())
        boundary=policy_observations([observation])
        self.assertEqual(set(boundary[0]),{"rgb"});self.assertIs(boundary[0]["rgb"],rgb)
        class Envs:
            def call_at(self,index,name):
                if name=="graph_raw_depth_endpoint":
                    return dict(depth=np.ones((8,8),np.float32),capture_monotonic_ns=1,collision=False)
                if name=="graph_static_sensor_spec":return sensor_spec()
                raise AssertionError("Forbidden environment call: "+name)
        with tempfile.TemporaryDirectory() as d:
            profile=json.loads((Path(__file__).parents[1]/"profiles/000_pose_shadow.json").read_text())
            hook=AwarePoseHook(Path(d)/"sentinel",profile,adapter_factory=adapter_factory)
            try:
                packet=reset_from_environment(hook,Envs(),0,observation,{"episode_uid":"unit-p09"})
                self.assertEqual(packet.pose_record["geometry_status"],"available")
                self.assertNotIn("gps",json.dumps(packet.to_record()))
                self.assertNotIn("goal",json.dumps(packet.to_record()))
            finally:hook.close()

    def test_P10_alignment_preserves_pixels_rng(self):
        rgb=np.arange(8*8*3,dtype=np.uint8).reshape(8,8,3)
        before=rgb.copy();py=random.getstate();nr=np.random.get_state()
        c=cal()
        RGBDAlignmentBridge(c,c,DepthSpec("meters","z","float32",0,10),np.eye(4)).align(
            rgb,np.ones((8,8),np.float32))
        self.assertTrue(np.array_equal(before,rgb))
        self.assertEqual(py,random.getstate())
        after=np.random.get_state()
        self.assertEqual(nr[0],after[0]);self.assertTrue(np.array_equal(nr[1],after[1]))
        self.assertEqual(nr[2:],after[2:])

    def test_P11_missing_native_dependencies_fail_closed(self):
        import os
        from graphAdapter.observation_pose.aware_hook import AwarePoseHook
        with tempfile.TemporaryDirectory() as d:
            profile=json.loads((Path(__file__).parents[1]/"profiles/000_pose_shadow.json").read_text())
            hook=AwarePoseHook(Path(d)/"missing-bwrap",profile)
            try:
                with patch.dict(os.environ,{"PATH":d}):
                    with patch.dict(os.environ,{},clear=False):
                        old=os.environ.pop("POSEADAPTER_BROKER",None)
                        try:packet=hook.reset("unit-p11",sensor_spec(),np.zeros((8,8,3),np.uint8),np.ones((8,8),np.float32),1)
                        finally:
                            if old is not None:os.environ["POSEADAPTER_BROKER"]=old
                self.assertEqual(packet.pose_record["geometry_status"],"unavailable")
                self.assertIn("bwrap",packet.failure_reason)
                self.assertTrue(Path(packet.raw_rgb_ref).is_file())
                self.assertTrue(Path(packet.raw_depth_ref).is_file())
                self.assertEqual(hook.native_initialization_attempts,1)
            finally:hook.close()


class RecordingResult(unittest.TextTestResult):
    def startTest(self,test):
        super().startTest(test)
        self.rows.append(dict(id=test.id().split(".")[-1],status="RUNNING",
             expected=test.shortDescription() or test.id().split(".")[-1],
             actual="Assertions pending",scope="portable_cpu_production_interface"))
    def addSuccess(self,test):
        super().addSuccess(test)
        self.rows[-1].update(status="PASS",actual="All named assertions satisfied")
    def addFailure(self,test,err):
        super().addFailure(test,err)
        self.rows[-1].update(status="FAIL",actual=self._exc_info_to_string(err,test))
    def addError(self,test,err):
        super().addError(test,err)
        self.rows[-1].update(status="ERROR",actual=self._exc_info_to_string(err,test))

def run_suite(output):
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    with (out/"unittest.log").open("x") as log:
        runner=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=RecordingResult)
        # Result owns its rows per run rather than global state.
        runner.resultclass=type("RunResult",(RecordingResult,),{"rows":[]})
        result=runner.run(unittest.defaultTestLoader.loadTestsFromTestCase(Contracts))
    (out/"test_results.json").write_text(json.dumps(dict(scope="portable_cpu",
        native_tracking="NOT_RUN",tests=result.rows,successful=result.wasSuccessful()),indent=2))
    return result
