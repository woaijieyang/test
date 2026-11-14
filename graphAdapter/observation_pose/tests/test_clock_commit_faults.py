"""Endpoint accounting and fail-closed publication regression tests (CPU, no native accuracy claim)."""
import ast,json,os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest
from graphAdapter.observation_pose.tests.test_review_rework import new_hook,start
from graphAdapter.observation_pose.tests.fixtures import sensor_spec
from graphAdapter.observation_pose.aware_hook import CaptureAttemptAborted
from graphAdapter.observation_pose import aware_hook
from graphAdapter.observation_pose.host_wiring import capture_from_environment
from case1_runtime.trace import TraceRecorder

RGB=np.zeros((8,8,3),np.uint8)
DEPTH=np.ones((8,8),np.float32)
def rows(h):return [json.loads(s) for s in (h.coordinator.root/"flow_trace.jsonl").read_text().splitlines()]
def unavailable(h,p):
    assert p is h.latest_packet and p.frame_uid==h.coordinator.frame_uid
    assert h.latest_geometry_input.geometry_status==h.latest_perception_input.geometry_status=="unavailable"
    assert h.latest_geometry_input.T_map_camera_cv is h.latest_perception_input.T_map_camera_cv is None
def aborted(h,exc,previous=1):
    assert h._aborted and h.packet_count==previous
    assert h.latest_packet is h.latest_geometry_input is h.latest_perception_input is None
    endpoint=exc.value.endpoint
    assert endpoint["capture_seq"]==2 and endpoint["env_step"]==1
    assert endpoint["frame_uid"]=="unit:f000002" and endpoint["action_id"]==2
    assert h.abort_receipt and json.loads(Path(h.abort_receipt).read_text())["committed"] is False
    for call in (h.decision,lambda:h.begin_macro(1,1),lambda:h.capture(RGB,DEPTH,3,action_id=1),
                 lambda:h.reset("next",sensor_spec(),RGB,DEPTH,1)):
        with pytest.raises(CaptureAttemptAborted):call()

@pytest.mark.parametrize("clock",[1,0,None])
def test_fault_endpoint_then_decision_reason_and_next_good(tmp_path,clock):
    h=new_hook(tmp_path);first=start(h)
    try:
        h.begin_macro(2,1);p=h.capture(RGB,DEPTH,clock,action_id=2,
            received_monotonic_ns=99,capture_clock_source="missing_endpoint" if clock is None else "endpoint")
        assert (p.env_step,p.capture_seq,p.frame_uid)==(1,2,"unit:f000002")
        assert p.capture_monotonic_ns==clock and p.received_monotonic_ns==99
        assert p.raw_rgb_ref!=first.raw_rgb_ref and p.raw_depth_ref!=first.raw_depth_ref
        np.testing.assert_array_equal(np.load(p.raw_depth_ref),DEPTH)
        unavailable(h,p)
        assert len(h.pose.frames)==1 and h.macro is None
        a=h.decision();b=h.decision()
        assert a["frame_uid"]==b["frame_uid"]==p.frame_uid
        assert a["cutoff_event_seq"]>=p.event_seq and a["env_step"]==b["env_step"]==1
        h.begin_macro(1,1);nextp=h.capture(RGB,DEPTH,3,action_id=1)
        assert (nextp.env_step,nextp.capture_seq)==(2,3)
        assert nextp.pose_record["geometry_status"]=="available" and len(h.pose.frames)==2
        archive=[r for r in rows(h) if r["kind"]=="raw_archive"][1]
        assert archive["clock_errors"][0]["raw_value"]==clock
        assert archive["capture_monotonic_ns"]==clock
    finally:h.close()

@pytest.mark.parametrize("fault_index",[1,2,3])
def test_macro_first_middle_last_and_terminal_reset(tmp_path,fault_index):
    h=new_hook(tmp_path);start(h);h.begin_macro(2,3)
    try:
        last=1
        for index in range(1,4):
            clock=last if index==fault_index else last+1
            p=h.capture(RGB,DEPTH,clock,action_id=2,terminal=index==3)
            if index!=fault_index:last=clock
            assert p.action["macro_id"]==1 and p.action["primitive_index"]==index and p.action["primitive_count"]==3
            if index==fault_index:unavailable(h,p)
        assert h.macro is None and h.pose.execution.authorized is None
        h.end_episode([2,1]);assert h.latest_packet is h.latest_geometry_input is h.latest_perception_input is None
        terminal=rows(h)[-1];assert terminal["env_step"]==3 and terminal["cancelled_actions"]==[2,1]
        reset=h.reset("next",sensor_spec(),RGB,DEPTH,1)
        assert reset.episode_uid=="next" and reset.env_step==0 and reset.capture_seq==1
        assert reset.frame_uid!="unit:f000001" and len(h.pose.frames)==1
    finally:h.close()

def test_host_missing_acquisition_time_preserves_depth_and_marks_receive_clock(tmp_path):
    h=new_hook(tmp_path);start(h)
    class Env:
        def call_at(self,index,name):return {"depth":DEPTH,"collision":False}
    try:
        p=capture_from_environment(h,Env(),0,{"rgb":RGB},action_id=1,terminal=False)
        unavailable(h,p)
        assert p.capture_monotonic_ns is None and p.capture_clock_source=="missing_endpoint"
        assert type(p.received_monotonic_ns)is int and p.received_monotonic_ns>0
        assert "graph_raw_depth_endpoint.capture_monotonic_ns" in p.failure_reason
        np.testing.assert_array_equal(np.load(p.raw_depth_ref),DEPTH)
    finally:h.close()

def test_archive_directory_collision_preserves_original_and_aborts(tmp_path):
    h=new_hook(tmp_path);start(h)
    folder=h.coordinator.root/"unit/f000002";folder.mkdir()
    for name in ("rgb","depth"):(folder/(name+".npy")).write_bytes(b"original-"+name.encode())
    try:
        h.begin_macro(2,1)
        with pytest.raises(CaptureAttemptAborted) as error:h.capture(RGB+7,DEPTH+3,2,action_id=2)
        aborted(h,error)
        for name in ("rgb","depth"):assert (folder/(name+".npy")).read_bytes()==b"original-"+name.encode()
        assert error.value.endpoint["raw_rgb_ref"] is error.value.endpoint["raw_depth_ref"] is None
        backup=error.value.endpoint["abort_raw_backup"]
        np.testing.assert_array_equal(np.load(backup["rgb"]),RGB+7)
        np.testing.assert_array_equal(np.load(backup["depth"]),DEPTH+3)
    finally:h.close()

@pytest.mark.parametrize("target",["rgb.npy","depth.npy","aligned_depth.npy","depth_valid_mask.npy","source_pixel_map.npy"])
def test_partial_archive_never_published_or_overwritten(tmp_path,target):
    h=new_hook(tmp_path);start(h);original=np.save
    def save(stream,array,**kwargs):
        if Path(stream.name).name==target and "aborted-endpoints" not in str(stream.name):
            stream.write(b"partial-evidence");raise OSError("injected partial "+target)
        return original(stream,array,**kwargs)
    try:
        with patch.object(np,"save",side_effect=save):
            with pytest.raises(CaptureAttemptAborted) as error:h.capture(RGB,DEPTH,2,action_id=2)
        aborted(h,error)
        partial=h.coordinator.root/"unit/f000002"/target
        assert partial.read_bytes()==b"partial-evidence"
        assert not [r for r in rows(h) if r["kind"]=="observation_packet" and r["frame_uid"]=="unit:f000002"]
        assert "partial" in error.value.endpoint["error"] or "partial" in str(error.value.endpoint["archive_errors"])
    finally:h.close()

@pytest.mark.parametrize("failure",["mkdir","open","flush"])
def test_unwritable_archive_aborts_with_execution_identity(tmp_path,failure):
    h=new_hook(tmp_path);start(h);mkdir=Path.mkdir;open_file=Path.open;sync=os.fsync
    def make(path,*a,**kw):
        if path.name=="f000002":raise PermissionError("unwritable frame directory")
        return mkdir(path,*a,**kw)
    def open_(path,*a,**kw):
        if path.name=="rgb.npy" and "f000002" in path.parts:raise PermissionError("unwritable raw file")
        return open_file(path,*a,**kw)
    def flush(fd):
        if "/unit/f000002/" in os.readlink("/proc/self/fd/"+str(fd)):raise OSError("raw flush failed")
        return sync(fd)
    try:
        with patch.object(Path,"mkdir",make),patch.object(Path,"open",open_),patch.object(os,"fsync",flush):
            # Only one independent fault per case.
            if failure!="mkdir":Path.mkdir=mkdir
            if failure!="open":Path.open=open_file
            if failure!="flush":os.fsync=sync
            with pytest.raises(CaptureAttemptAborted) as error:h.capture(RGB,DEPTH,2,action_id=2)
        aborted(h,error)
    finally:h.close()

class FaultStream:
    def __init__(self,base,operation,kind=None,observe=None):
        self.base=base;self.operation=operation;self.kind=kind;self.observe=observe;self.last=None;self.fired=False
    def write(self,text):
        self.last=json.loads(text).get("kind")
        if self.observe:self.observe()
        if not self.fired and self.operation=="write" and (self.kind is None or self.last==self.kind):
            self.fired=True;raise OSError("injected log write")
        return self.base.write(text)
    def flush(self):
        if self.observe:self.observe()
        if not self.fired and self.operation=="flush" and (self.kind is None or self.last==self.kind):
            self.fired=True;raise OSError("injected log flush")
        return self.base.flush()
    def close(self):return self.base.close()

@pytest.mark.parametrize("stream,operation,kind",[
    ("packet","write",None),("packet","flush",None),
    ("flow","write","raw_archive"),("flow","flush","raw_archive"),
    ("flow","write","observation_packet"),("flow","flush","observation_packet"),
    ("flow","write","geometry_unavailable"),("flow","flush","geometry_unavailable"),
    ("flow","write","pose_runtime_error"),("flow","flush","pose_runtime_error")])
def test_each_log_write_flush_failure_aborts_no_ghost_latest(tmp_path,stream,operation,kind):
    h=new_hook(tmp_path);start(h)
    owner=h if stream=="packet" else h.coordinator
    attribute="packet_stream" if stream=="packet" else "stream"
    original=getattr(owner,attribute);fault=FaultStream(original,operation,kind);setattr(owner,attribute,fault)
    try:
        with pytest.raises(CaptureAttemptAborted) as error:
            h.capture(RGB,DEPTH,1 if kind in {"geometry_unavailable","pose_runtime_error"} else 2,action_id=2)
        assert fault.fired;aborted(h,error)
    finally:setattr(owner,attribute,original);h.close()

def test_no_readable_commit_before_both_log_flushes(tmp_path):
    h=new_hook(tmp_path);start(h);original=h.coordinator.stream;observations=[]
    def observe():
        observations.append((h.latest_packet,h.latest_geometry_input,h.latest_perception_input,h.packet_count))
        assert observations[-1]==(None,None,None,1)
    h.coordinator.stream=FaultStream(original,None,observe=observe)
    try:
        p=h.capture(RGB,DEPTH,2,action_id=1)
        assert observations and h.packet_count==2 and h.latest_packet is p
        assert json.loads((h.coordinator.root/"observation-packets.jsonl").read_text().splitlines()[-1])==p.to_record()
    finally:h.coordinator.stream=original;h.close()

def test_packet_validation_fallback_keeps_full_action_evidence(tmp_path):
    h=new_hook(tmp_path);start(h);original=aware_hook.ObservationPacket;count=0
    def construct(*args,**kwargs):
        nonlocal count
        count+=1
        if count==1:raise ValueError("injected packet validation")
        return original(*args,**kwargs)
    try:
        h.begin_macro(2,3)
        with patch.object(aware_hook,"ObservationPacket",side_effect=construct):
            p=h.capture(RGB,DEPTH,2,action_id=2)
        unavailable(h,p)
        assert dict(p.action)==dict(action_id=2,terminal=False,collision=None,macro_id=1,primitive_index=1,primitive_count=3)
        assert p.frame_uid=="unit:f000002" and "packet validation" in p.failure_reason
    finally:h.close()

def test_packet_validation_fallback_failure_aborts(tmp_path):
    h=new_hook(tmp_path);start(h)
    try:
        with patch.object(aware_hook,"ObservationPacket",side_effect=ValueError("all packet constructors failed")):
            with pytest.raises(CaptureAttemptAborted) as error:h.capture(RGB,DEPTH,2,action_id=2)
        aborted(h,error)
    finally:h.close()

def test_terminal_log_failure_revokes_current_and_attributes_original_episode(tmp_path):
    h=new_hook(tmp_path);start(h);stream=h.coordinator.stream
    h.coordinator.stream=FaultStream(stream,"flush","terminal")
    try:
        with pytest.raises(CaptureAttemptAborted) as error:h.end_episode([1,2])
        assert error.value.endpoint["episode_uid"]=="unit"
        assert h._aborted and h.latest_packet is h.latest_geometry_input is h.latest_perception_input is None
    finally:h.coordinator.stream=stream;h.close()

@pytest.mark.parametrize("done",[False,True])
@pytest.mark.parametrize("index,queue",[(1,[]),(2,[2,2]),(3,[2])])
def test_actual_trainer_step_records_executed_action_and_aborts_without_success(tmp_path,done,index,queue):
    path=Path(__file__).resolve().parents[3]/"vlnce_baselines/awarevln_trainer.py"
    tree=ast.parse(path.read_text())
    fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=="record_step")
    ep=SimpleNamespace(scene_id="/scene/scan/scan.glb",episode_id="1",instruction=SimpleNamespace(instruction_id="i"))
    class Env:
        executed=[]
        def current_episodes(self):return [ep]
        def call_at(self,index,name):return {"elapsed_steps":1}
        def step(self,actions):
            self.executed+=actions
            return [(dict(rgb=RGB),0.,done,{})]
    env=Env();recorder=TraceRecorder(tmp_path/"trace","r2r")
    error=CaptureAttemptAborted("cannot commit",{"frame_uid":"unit:f000002","env_step":1,"action_id":2,
        "macro_id":1,"primitive_index":index,"primitive_count":3})
    module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
    namespace=dict(envs=env,recorder=recorder,graph_hook=object(),queue_actions=queue)
    exec(compile(module,str(path),"exec"),namespace)
    with patch("graphAdapter.observation_pose.host_wiring.capture_from_environment",side_effect=error):
        with pytest.raises(CaptureAttemptAborted):namespace["record_step"]([2])
    log=[json.loads(s) for s in next((tmp_path/"trace/episodes").glob("*/trace.jsonl")).read_text().splitlines()]
    assert env.executed==[2] and [r["kind"]for r in log]==["reset","primitive_action","attempt_aborted"]
    assert log[1]["done"] is done and log[1]["action"]==2
    assert log[-1]["steps"]==1 and log[-1]["cancelled_actions"]==[2]*(3-index) and log[-1]["success"] is False
    assert log[-1]["host_queue_at_failure"]==queue and log[-1]["cancelled_actions_source"]=="endpoint_macro"
    assert not list((tmp_path/"trace").rglob("result.json")) and not (tmp_path/"trace/results.jsonl").exists()
    recorder.close()

@pytest.mark.parametrize("target",["sensor_spec.json","calibration.json","effective-pose-config.json"])
def test_initial_configuration_archive_write_failure_aborts_preserving_raw(tmp_path,target):
    h=new_hook(tmp_path);original=Path.open
    def open_(path,*a,**kwargs):
        if path.name==target:raise PermissionError("configuration archive denied")
        return original(path,*a,**kwargs)
    try:
        with patch.object(Path,"open",open_):
            with pytest.raises(CaptureAttemptAborted) as error:start(h)
        assert h._aborted and h.packet_count==0 and h.latest_packet is None
        endpoint=error.value.endpoint
        assert endpoint["episode_uid"]=="unit" and endpoint["frame_uid"]=="unit:f000001"
        assert endpoint["env_step"]==0 and endpoint["action_id"] is None
        assert Path(endpoint["raw_rgb_ref"]).exists() and Path(endpoint["raw_depth_ref"]).exists()
        assert h.abort_receipt
    finally:h.close()
