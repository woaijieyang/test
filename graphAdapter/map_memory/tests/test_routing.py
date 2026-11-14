"""Actual producer callbacks on isolated fresh roots;CPU fixture is not SLAM."""
from pathlib import Path
from types import SimpleNamespace
import json,os,hashlib
import numpy as np
import pytest
from graphAdapter.map_memory.storage.routing import create_run,RunRouting,from_environment
from graphAdapter.map_memory.storage.lifecycle import LifecycleError,audit_pair
from graphAdapter.observation_pose.aware_hook import AwarePoseHook
from graphAdapter.observation_pose.tests.fixtures import sensor_spec,adapter_factory
from case1_runtime.trace import TraceRecorder
from case1_runtime.episode_scope import episode_scope

def routing(tmp_path,monkeypatch,side="shadow"):
    member=["r2r","mp3d/fixture/fixture.glb","1","-"]
    plan=dict(owner_roles=["host","source000","pose"],owner_components={"host":"host_trace","source000":"file_owner","pose":"pose"},
        entries=[dict(key="e1",member=member,mode="ordinary",owner_roles_by_side={"control":["host"],"shadow":["host","source000","pose"]})],
        max_trace_raw_bytes=4*1024**2,max_trace_compressed_bytes=1024**2,max_diagnostic_bytes=16*1024**2,
        max_expanded_bytes=32*1024**2,max_ordinary_retained_bytes=8*1024**2,max_summary_bytes=1024**2)
    root=tmp_path/"run";common=create_run(root,plan,run_uid="owner-cpu-"+tmp_path.name)
    binding=dict(common,side=side,attempt="a",worker_id=side+"0")
    monkeypatch.setenv("CASE2_STORAGE_BINDING",json.dumps(binding))
    monkeypatch.setenv("CASE2_RUN_UID","runtime-"+side);monkeypatch.setenv("CASE2_ATTEMPT_ID","a");monkeypatch.setenv("CASE2_DATASET_KEY","r2r")
    ep=SimpleNamespace(scene_id=member[1],episode_id="1",instruction=SimpleNamespace(instruction_id=None))
    return root,RunRouting(binding),ep

def finish_host(root,ep):
    recorder=TraceRecorder(root/"shards/worker","r2r")
    (recorder.root/"effective-config.yaml").write_text("CONTRACT: true\n")
    recorder.ensure_episode(ep,{"elapsed_steps":0})
    recorder.step(ep,0,{"elapsed_steps":0},{"elapsed_steps":1},True,
        dict(success=0.,spl=0.,ndtw=0.,distance_to_goal=2.,oracle_success=0.))
    return recorder

def test_real_host_and_000_end_callbacks_gather_only_new_owned_paths(tmp_path,monkeypatch):
    root,route,ep=routing(tmp_path,monkeypatch)
    profile=json.loads((Path(__file__).parents[2]/"observation_pose/profiles/000_pose_shadow.json").read_bytes())
    hook=AwarePoseHook(root/"shards/worker/observation_pose",profile,adapter_factory=adapter_factory)
    scope=episode_scope(ep)
    hook.reset(scope["episode_uid"],sensor_spec(),np.zeros((8,8,3),np.uint8),np.ones((8,8),np.float32),1,identity=scope)
    recorder=finish_host(root,ep)
    storage=recorder.storage_episode
    assert storage._state()["state"]=="ACTIVE"
    hook.end_episode([])
    assert storage._state()["state"]=="DELETED"and not storage.work.exists()
    assert not recorder.directory.exists()
    assert not(hook.coordinator.root/scope["episode_uid"]).exists()
    retained=json.loads((storage.result/"retention.json").read_bytes())
    assert retained["trace_audit"]["status"]=="VERIFIED"
    assert set(retained["release"]["session_receipts"])=={"host","source000","pose"}
    hook.close()

def test_control_does_not_wait_for_shadow_owner_roles(tmp_path,monkeypatch):
    root,route,ep=routing(tmp_path,monkeypatch,"control")
    recorder=finish_host(root,ep)
    assert recorder.storage_episode._state()["state"]=="DELETED"
    assert json.loads((recorder.storage_episode.result/"retention.json").read_bytes())["summary"]["metrics"]["sr"]==0.

@pytest.mark.parametrize("namespace",["../old/ep","run/../ep","/run/ep","run/ep/extra","run\\ep",""])
def test_pure_pose_namespace_defaults_and_invalid_paths(namespace):
    from poseAdapter.pose_config import PoseConfig
    if namespace=="":assert PoseConfig(artifact_namespace=namespace).artifact_namespace==""
    else:
        with pytest.raises(ValueError):PoseConfig(artifact_namespace=namespace)

def test_producer_registration_refuses_adoption_and_symlink(tmp_path,monkeypatch):
    root,route,ep=routing(tmp_path,monkeypatch)
    owner=route.episode(episode_scope(ep))
    old=root/"existing";old.mkdir()
    with pytest.raises(LifecycleError):route.register(owner,"host",old,"host")
    alias=root/"alias";alias.symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(LifecycleError):route.register(owner,"host",alias/"new","host")

def test_retained_report_rejects_directed_fixture_as_navigation(tmp_path,monkeypatch):
    from graphAdapter.evaluation.retained import report_retained
    root,route,ep=routing(tmp_path,monkeypatch,"control")
    finish_host(root,ep)
    result=report_retained(root,root/"retained-report")
    assert result["status"]=="FAIL_OR_INCOMPLETE_RETAINED_AUDIT"
    assert "no_actual_evaluator_manifests"in result["hard_contract_errors"]

def test_crashed_creator_recovery_preserves_failure_and_reclaims_registered_scope(tmp_path,monkeypatch):
    import subprocess,sys
    from graphAdapter.map_memory.storage.routing import recover_failed_episode
    from graphAdapter.map_memory.storage.lifecycle import EpisodeLifecycle,process_identity
    root,route,member=routing(tmp_path,monkeypatch,"control")
    child_script=root/"crash-producer.py"
    child_script.write_text(
        "from pathlib import Path\nfrom types import SimpleNamespace\n"
        "from case1_runtime.trace import TraceRecorder\n"
        "r=TraceRecorder(Path("+repr(str(root/"crashed/worker"))+"),'r2r')\n"
        "ep=SimpleNamespace(scene_id='mp3d/fixture/fixture.glb',episode_id='1',instruction=SimpleNamespace(instruction_id=None))\n"
        "r.ensure_episode(ep,{'scope':'CPU_crash_contract'})\n"
        "(r.directory/'data.bin').write_bytes(b'owned'*4096)\n"
        "print('READY',flush=True)\nimport time;time.sleep(30)\n")
    process=subprocess.Popen([sys.executable,"-B",str(child_script)],stdout=subprocess.PIPE,text=True,
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[3])))
    assert process.stdout.readline().strip()=="READY"
    identity=process_identity(process.pid);assert identity is not None
    process.kill();process.wait(timeout=10)
    owner=EpisodeLifecycle(root,"e1","control","a",plan_sha256=route.plan_sha)
    outcome=recover_failed_episode(route,owner)
    assert outcome["state"]=="DELETED"
    retained=json.loads((owner.result/"retention.json").read_bytes())
    assert retained["summary"]["status"]=="failed"
    assert retained["trace_audit"]["status"]=="FAILED_OR_INCOMPLETE"
    assert(owner.result/"failure-owner-recovery.json").exists()

def test_process_scope_keeps_native_protocol_metadata_but_releases_work(tmp_path,monkeypatch):
    import subprocess,sys
    from graphAdapter.map_memory.storage.routing import create_process_scope,bind_process_scope,release_process_scopes
    from graphAdapter.map_memory.storage.lifecycle import process_identity
    root,route,ep=routing(tmp_path,monkeypatch,"control")
    process=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"])
    output=create_process_scope(root,root/"process-test","host_output")
    bind_process_scope(root,output,process_identity(process.pid))
    (output/"effective-config.yaml").write_text("frozen: true\n")
    (output/"model-receipt.json").write_text('{"scope":"CPU_fixture"}')
    (output/"native.log").write_text("owned log\n")
    assert release_process_scopes(root)["pending"]
    process.terminate();process.wait(timeout=10)
    result=release_process_scopes(root)
    assert not result["pending"]and(output/"effective-config.yaml").exists()
    assert not(output/"native.log").exists()
    assert release_process_scopes(root)==dict(released=[],pending=[])

def test_native_startup_failure_preserves_first_stage_and_does_not_query_closed_adapter(tmp_path):
    from graphAdapter.observation_pose.aware_hook import CaptureAttemptAborted
    from graphAdapter.observation_pose.tests.fixtures import Runtime
    from poseAdapter import PoseAdapter
    class Failed(Runtime):
        def reset(self,*args):raise RuntimeError("native-startup-sentinel")
    def factory(config,options):return PoseAdapter(config,options,native_factory=Failed)
    profile=json.loads((Path(__file__).parents[2]/"observation_pose/profiles/000_pose_shadow.json").read_bytes())
    hook=AwarePoseHook(tmp_path/"startup-fail",profile,adapter_factory=factory)
    with pytest.raises(CaptureAttemptAborted)as captured:
        hook.reset("failed-native",sensor_spec(),np.zeros((8,8,3),np.uint8),np.ones((8,8),np.float32),1)
    assert captured.value.endpoint["stage"]=="native_reset"
    assert "native-startup-sentinel"in str(captured.value)
    assert Path(captured.value.endpoint["raw_rgb_ref"]).exists()
    flow=[json.loads(x)for x in(hook.coordinator.root/"flow_trace.jsonl").read_text().splitlines()]
    assert any(x.get("stage")=="native_reset"for x in flow)
    assert not any(x.get("stage")=="packet_validation_or_commit"for x in flow)
    assert hook.active_pose_adapter()is None
    hook.close()

def test_inactive_pose_reference_is_not_used_as_snapshot_provider(tmp_path):
    profile=json.loads((Path(__file__).parents[2]/"observation_pose/profiles/000_pose_shadow.json").read_bytes())
    hook=AwarePoseHook(tmp_path/"inactive",profile,adapter_factory=adapter_factory)
    class Closed:
        def get_status(self):return dict(episode_id=None,closed=True,runtime=None)
        def get_frame_snapshot(self,*a,**kw):raise AssertionError("closed provider queried")
    hook.pose=SimpleNamespace(adapter=Closed())
    assert hook.active_pose_adapter()is None
    hook.pose=None;hook.close()

def test_nested_process_scopes_release_children_before_parent(tmp_path,monkeypatch):
    import subprocess,sys
    from graphAdapter.map_memory.storage.routing import create_process_scope,bind_process_scope,release_process_scopes
    from graphAdapter.map_memory.storage.lifecycle import process_identity
    root,route,ep=routing(tmp_path,monkeypatch,"control")
    child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"])
    parent_scope=create_process_scope(root,root/"worker-output","host_output")
    nested=create_process_scope(root,parent_scope/"map_memory","memory_output")
    owner=process_identity(child.pid)
    bind_process_scope(root,parent_scope,owner);bind_process_scope(root,nested,owner)
    (parent_scope/"effective-config.yaml").write_text("native_contract: true\n")
    (nested/"process-receipt.json").write_text('{"scope":"CPU_fixture"}')
    child.terminate();child.wait(timeout=10)
    result=release_process_scopes(root)
    assert not result["pending"]and not nested.exists()
    assert(parent_scope/"effective-config.yaml").exists()
    assert release_process_scopes(root)==dict(released=[],pending=[])
