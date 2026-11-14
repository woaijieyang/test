"""Lifecycle fault contracts. No models, simulator or historical data mutations."""
from pathlib import Path
import copy
import gzip
import hashlib
import io
import json
import os
import tarfile
import pytest
from PIL import Image
import numpy as np
from graphAdapter.map_memory.storage.lifecycle import (
    EpisodeLifecycle, LifecycleError, audit_pair, capacity_budget, compare_traces,
    compress_jsonl, process_identity, unpack_tree, sha, memory_capability, EpisodeSession, audit_single, json_rows)
from graphAdapter.map_memory.tests.test_storage import archive, publish, EP
from graphAdapter.map_memory.storage.store import EpisodeStore, load_episode

MEMBER = ["r2r", "mp3d/fixture/fixture.glb", "1", "-"]
RELEASE = dict(consumers_joined=True, native_closed=True, memory_closed=True,
               pins=0, leases=0, cache_entries={"decoded": 0}, owners=[])

def plan(mode="ordinary"):
    return dict(owner_roles=["fixture_files"],owner_components={"fixture_files":"file_owner"},entries=[dict(key="e1", member=MEMBER, mode=mode)],
        max_trace_raw_bytes=4*1024**2, max_trace_compressed_bytes=1024**2,
        max_diagnostic_bytes=16*1024**2, max_expanded_bytes=32*1024**2,
        max_ordinary_retained_bytes=4*1024**2,max_summary_bytes=512*1024)

def pair(tmp_path, mode="ordinary"):
    root = tmp_path/"run"
    h = EpisodeLifecycle.create_run(root, plan(mode))
    result = []
    for side in ("control", "shadow"):
        ep = EpisodeLifecycle(root, "e1", side, "attempt0", plan_sha256=h)
        ep.create_work()
        Image.fromarray(np.arange(48, dtype=np.uint8).reshape(4,4,3)).save(ep.work/"rgb.png")
        with Image.open(ep.work/"rgb.png") as im:
            px = hashlib.sha256(im.mode.encode()+str(im.size).encode()+im.tobytes()).hexdigest()
        rows = [
            dict(kind="reset", episode_scope=dict(member=MEMBER)),
            dict(kind="model_input", call_id=1, prompt="fixture", input_ids=[[1]],
                 processed_image_shape=[1,3,4,4], processed_image_sha256="a"*64,
                 generation=dict(do_sample=False), stop_str="end", sep2="end",
                 images=[dict(path="rgb.png",pixel_sha256=px,size=[4,4],mode="RGB")]),
            dict(kind="model_call", call_id=1, output_ids=[[2]],raw_decoded_output="go",normalized_output="go"),
            dict(kind="primitive_action",action=1,done=True,stop_source=None),
            dict(kind="terminal",steps=1,model_calls=1,termination_reason="max_steps",stop_source=None)]
        rows[2]={**rows[1],**rows[2]}
        (ep.work/"trace.jsonl").write_text("".join(json.dumps(r)+"\n"for r in rows))
        (ep.work/"bulk.bin").write_bytes(b"x"*65536)
        result.append(ep)
    return result

def released(ep):
    release=copy.deepcopy(RELEASE)
    ticket=ep.result/'owner_sessions/fixture_files.json'
    if not ticket.exists():
        session=EpisodeSession(ep,'fixture_files')
        handle=(ep.work/'actual_owner_handle.log').open('w')
        acknowledgement=session.close_files([handle])
        (ep.result/'fixture_close.json').write_text(json.dumps(acknowledgement))
    release['session_receipts']={'fixture_files':json.loads((ep.result/'fixture_close.json').read_bytes())}
    return release

def seal(ep, **kw):
    return ep.seal(trace=ep.work/"trace.jsonl", image_root=ep.work,
                   summary=dict(status="failed_navigation",fixed_denominator=1),
                   release=released(ep), **kw)

def test_roundtrip_pair_cleanup_preserves_failed_denominator_and_idempotent(tmp_path):
    a,b=pair(tmp_path)
    ra,rb=seal(a),seal(b)
    assert ra["verified_host_images"]==1 and ra["capabilities"]==[]
    with gzip.open(a.result/"trace.jsonl.gz","rb")as f:
        assert f.read()==(a.work/"trace.jsonl").read_bytes()
    audit=audit_pair(a,b)
    assert audit["business_equivalence"]["equal"] and audit["failure_denominator_preserved"]
    out=a.finalize(audit)
    assert out["deleted"] and not a.work.exists() and b.work.exists()
    assert a.finalize(audit)==out
    assert json.loads((a.result/"retention.json").read_bytes())["summary"]["status"]=="failed_navigation"
    b.finalize(audit)
    assert not out["kernel_quota_enforced"]

@pytest.mark.parametrize("field,value",[
    ("native_closed",False),("memory_closed",False),("consumers_joined",False),
    ("pins",1),("leases",1),("cache_entries",{"late":1}),
    ("owners",[process_identity(os.getpid())])])
def test_live_producer_pin_lease_or_cache_rejects_seal(tmp_path,field,value):
    a,b=pair(tmp_path)
    release=released(a);release[field]=value
    with pytest.raises(LifecycleError):
        a.seal(trace=a.work/"trace.jsonl",image_root=a.work,summary={},release=release)
    assert a.work.exists() and a._state()["state"]=="ACTIVE"

def test_open_file_and_async_evidence_lease_block_cleanup(tmp_path):
    a,b=pair(tmp_path)
    with a.lease():
        with pytest.raises(LifecycleError,match="lease"):seal(a)
    seal(a);seal(b);audit=audit_pair(a,b)
    with (a.work/"bulk.bin").open("rb"):
        with pytest.raises(LifecycleError,match="still open"):a.finalize(audit)
    with pytest.raises(LifecycleError,match="frozen"):
        with a.lease():pass
    assert a.finalize(audit)["deleted"]

@pytest.mark.parametrize("stage",["delete_authorized","file_deleted","owner_removed"])
def test_actual_partial_delete_recovery_at_each_durable_boundary(tmp_path,stage):
    a,b=pair(tmp_path);seal(a);seal(b);audit=audit_pair(a,b)
    def fail(where):
        if where==stage:raise RuntimeError("injected interruption")
    with pytest.raises(RuntimeError):a.finalize(audit,fault=fail)
    recovered=EpisodeLifecycle(a.root,a.key,a.side,a.attempt,plan_sha256=a.plan_sha)
    assert recovered.finalize(audit)["deleted"]

def test_publish_interruption_leaves_source_and_can_reseal(tmp_path):
    a,b=pair(tmp_path)
    def fail(stage):raise RuntimeError("publication interrupted")
    with pytest.raises(RuntimeError):seal(a,fault=fail)
    assert a.work.exists() and a._state()["state"]=="ACTIVE"
    assert seal(a)["trace"]["rows"]==5

@pytest.mark.parametrize("kind",["symlink","external_hardlink","late_file","changed_source","wrong_owner"])
def test_ownership_and_postseal_changes_fail_closed(tmp_path,kind):
    a,b=pair(tmp_path)
    if kind in ("symlink","external_hardlink"):
        outside=tmp_path/"outside";outside.write_bytes(b"protected")
        if kind=="symlink":(a.work/"escape").symlink_to(outside)
        else:os.link(outside,a.work/"escape")
        with pytest.raises(LifecycleError):seal(a)
        assert outside.read_bytes()==b"protected"
        return
    seal(a);seal(b);audit=audit_pair(a,b)
    if kind=="late_file":(a.work/"late.bin").write_bytes(b"late")
    elif kind=="changed_source":(a.work/"bulk.bin").write_bytes(b"changed")
    else:(a.work/".owned.json").write_text("{}")
    with pytest.raises(LifecycleError):a.finalize(audit)
    assert a.work.exists()

@pytest.mark.parametrize("mode",["preview_only","graph_metadata_only"])
def test_distinct_readable_capabilities_not_inferred_from_saved_flag(tmp_path,mode):
    a,b=pair(tmp_path,mode)
    kw={"preview":a.work/"rgb.png"}if mode=="preview_only"else{"graph_metadata":a.work/"graph.json"}
    if mode=="graph_metadata_only":(a.work/"graph.json").write_text(json.dumps(dict(nodes=[],edges=[],revision="r1")))
    receipt=seal(a,**kw)
    assert receipt["capabilities"]==[mode] and "queryable" not in receipt["capabilities"]

@pytest.mark.parametrize("mode",["queryable","rebuildable","audit_full"])
def test_snapshot_capability_requires_real_materials_and_bounded_package(tmp_path,mode):
    a,b=pair(tmp_path,mode)
    store=EpisodeStore(a.work/"memory",EP,dataset="r2r")
    archive(store,1);publish(store,[1]);store.close()
    if mode=="audit_full":
        names=["host_trace","source_packets","calibration","native_db","source_lock","effective_config"]
        evidence={}
        for name in names:
            target=a.work/(name+".json")
            target.write_text(json.dumps({"fixture":name}))
            evidence[name]=dict(path=target.name,sha256=sha(target))
        import sqlite3
        db=sqlite3.connect(a.work/'native.db')
        db.execute('CREATE TABLE Node(id INTEGER PRIMARY KEY)');db.execute('CREATE TABLE Data(id INTEGER PRIMARY KEY,data BLOB)');db.commit();db.close()
        evidence['native_db']=dict(path='native.db',sha256=sha(a.work/'native.db'))
        (a.work/'source_packets.jsonl').write_text(json.dumps(dict(frame_uid=EP+':f000001',episode_uid=EP,raw_rgb_ref='rgb.png',raw_depth_ref=None,aligned_ref=None))+'\n')
        evidence['source_packets']=dict(path='source_packets.jsonl',sha256=sha(a.work/'source_packets.jsonl'))
        (a.work/"audit_inputs.json").write_text(json.dumps(evidence))
    if mode=='audit_full':
        with pytest.raises(LifecycleError,match='audit input roles'):seal(a,memory=a.work/'memory')
        assert a.work.exists()
        return
    receipt=seal(a,memory=a.work/"memory")
    assert "queryable"in receipt["capabilities"]
    desc=receipt["qualification"]["package"]
    out=tmp_path/"expanded"
    expanded=unpack_tree(a.result/"memory.tar.gz",out,max_expanded=32*1024**2,expected_sha256=desc["sha256"])
    assert expanded["source_plus_target_bytes"]==desc["compressed_bytes"]+desc["expanded_bytes"]
    assert memory_capability(out/"memory",mode)["images"]==1

def test_retained_corruption_and_wrong_pair_cannot_delete(tmp_path):
    a,b=pair(tmp_path);seal(a);seal(b);audit=audit_pair(a,b)
    wrong=copy.deepcopy(audit);wrong["key"]="different"
    with pytest.raises(LifecycleError):a.finalize(wrong)
    (a.result/"materials.jsonl.gz").write_bytes(b"corrupt")
    with pytest.raises(LifecycleError):a.finalize(audit)
    assert a.work.exists()

@pytest.mark.parametrize("fault",["partial_json","raw_limit","compressed_limit"])
def test_trace_limits_never_silently_truncate(tmp_path,fault):
    path=tmp_path/"source.jsonl";raw=b'{"x":"'+os.urandom(200).hex().encode()+b'"}\n'
    path.write_bytes(raw[:-1]if fault=="partial_json"else raw)
    before=path.read_bytes()
    with pytest.raises((LifecycleError,json.JSONDecodeError)):
        compress_jsonl(path,tmp_path/"out.gz",max_raw=10 if fault=="raw_limit"else 4096,max_compressed=10 if fault=="compressed_limit"else 4096)
    assert path.read_bytes()==before and not(tmp_path/"out.gz").exists()

@pytest.mark.parametrize("name",["../outside","/outside"])
def test_archive_path_traversal_rejected(tmp_path,name):
    arc=tmp_path/"bad.tar.gz"
    with tarfile.open(arc,"w:gz")as tar:
        entry=tarfile.TarInfo(name);entry.size=4;tar.addfile(entry,io.BytesIO(b"evil"))
    with pytest.raises(LifecycleError):unpack_tree(arc,tmp_path/"out",max_expanded=100,expected_sha256=sha(arc))
    assert not(tmp_path/"outside").exists()

def test_expanded_limit_and_wrong_checksum_rejected(tmp_path):
    arc=tmp_path/"archive.tar.gz"
    with tarfile.open(arc,"w:gz")as tar:
        entry=tarfile.TarInfo("large");entry.size=1000;tar.addfile(entry,io.BytesIO(b"x"*1000))
    with pytest.raises(LifecycleError):unpack_tree(arc,tmp_path/"out",max_expanded=500,expected_sha256=sha(arc))
    with pytest.raises(LifecycleError):unpack_tree(arc,tmp_path/"out2",max_expanded=5000,expected_sha256="0"*64)

def test_attempt_isolation_plan_drift_and_no_historical_adoption(tmp_path):
    a,b=pair(tmp_path)
    with pytest.raises(FileExistsError):a.create_work()
    second=EpisodeLifecycle(a.root,a.key,a.side,"attempt1",plan_sha256=a.plan_sha)
    second.create_work()
    assert second.work!=a.work and a.work.exists()
    with pytest.raises(LifecycleError):EpisodeLifecycle(a.root,"notselected","shadow","a",plan_sha256=a.plan_sha)
    (a.root/"retention_plan.json").write_text("{}")
    with pytest.raises(LifecycleError):EpisodeLifecycle(a.root,a.key,a.side,a.attempt,plan_sha256=a.plan_sha)

def test_business_difference_is_retained_not_relabeled_pass(tmp_path):
    a,b=pair(tmp_path)
    text=(b.work/"trace.jsonl").read_text().replace('"action": 1','"action": 2')
    (b.work/"trace.jsonl").write_text(text)
    seal(a);seal(b);audit=audit_pair(a,b)
    assert not audit["business_equivalence"]["equal"]
    assert audit["failure_denominator_preserved"]

def test_real_pinned_reader_blocks_cleanup_until_closed(tmp_path):
    a,b=pair(tmp_path)
    store=EpisodeStore(a.work/"memory",EP,dataset="r2r");archive(store,1);publish(store,[1]);store.close()
    reader=load_episode(a.work/"memory")
    try:
        with pytest.raises(LifecycleError):seal(a)
    finally:reader.close()
    seal(a);seal(b);audit=audit_pair(a,b)
    assert a.finalize(audit)["deleted"]

def test_unmanaged_postseal_sqlite_reader_mutation_keeps_sources(tmp_path):
    a,b=pair(tmp_path)
    store=EpisodeStore(a.work/"memory",EP,dataset="r2r");archive(store,1);publish(store,[1]);store.close()
    seal(a);seal(b);audit=audit_pair(a,b)
    reader=load_episode(a.work/"memory")
    try:
        with pytest.raises(LifecycleError):a.finalize(audit)
    finally:reader.close()
    with pytest.raises(LifecycleError,match="late material"):a.finalize(audit)
    assert a.work.exists()

def test_capacity_does_not_report_ledger_or_polling_as_enforcement():
    budget=capacity_budget(concurrent_workers=4,activity_peak=100,rebuild_extra=50,codec_extra=25,native_peak=20,
        retained_ordinary=1000,fixed_diagnostics=500,emergency=300,available=3000)
    assert budget["required_bytes"]==2580 and budget["capacity_admitted"]
    assert not budget["production_ready"] and not budget["kernel_quota_enforced"]

def test_store_cache_eviction_and_closed_indices_are_real(tmp_path):
    store=EpisodeStore(tmp_path/'memory',EP,dataset='r2r')
    archive(store,1);publish(store,[1]);expected=store.read_rgb(EP+':f000001').copy()
    assert not store.release_audit()['memory_closed']
    assert not any(store.evict_caches().values())
    assert np.array_equal(store.read_rgb(EP+':f000001'),expected)
    store.close();result=store.release_audit()
    assert result['memory_closed'] and result['pins_zero'] and not any(result['cache_entries'].values())
    assert result['native_closed'] is None

def test_geometry_sources_required_before_seal_and_preserved_after_cleanup(tmp_path):
    config=plan();config['entries'][0]['requires_geometry_evidence']=True
    root=tmp_path/'required';h=EpisodeLifecycle.create_run(root,config)
    side=EpisodeLifecycle(root,'e1','shadow','a',plan_sha256=h);side.create_work()
    (side.work/'trace.jsonl').write_text(json.dumps(dict(kind='reset',episode_scope=dict(member=MEMBER)))+'\n')
    with pytest.raises(LifecycleError,match='Per-frame'):seal(side)
    sources={}
    for name in ['observation_packets','flow','map_commits']:
        path=side.work/(name+'.jsonl');path.write_text(json.dumps(dict(frame_uid='e1:f1',snapshot_id='abc'))+'\n');sources[name]=path
    result=seal(side,evidence_streams=sources)
    assert set(result['evidence_streams'])==set(sources)
    assert result['trace_audit']['status']=='FAILED_OR_INCOMPLETE'
    assert result['trace_audit']['denominator_preserved']

def test_single_side_release_then_late_or_failed_shadow_pairs_from_receipts(tmp_path):
    a,b=pair(tmp_path)
    seal(a);single=audit_single(a)
    assert a.finalize(single)['deleted'] and not a.work.exists()
    text=(b.work/'trace.jsonl').read_text();rows=[json.loads(x)for x in text.splitlines()]
    rows[-1]=dict(kind='attempt_aborted',steps=1,reason='shadow late failure')
    (b.work/'trace.jsonl').write_text(''.join(json.dumps(x)+'\n'for x in rows))
    seal(b);assert b.finalize(audit_single(b))['deleted']
    paired=audit_pair(a,b)
    assert paired['audit_complete'] and not paired['complete_success']
    assert paired['failure_denominator_preserved']

@pytest.mark.parametrize('field',['call_id','frame','task_key','last_call_id','step','native_metrics'])
def test_deleted_evidence_still_detects_call_frame_member_action_metric_fault(tmp_path,field):
    a,b=pair(tmp_path);rows=[json.loads(x)for x in(b.work/'trace.jsonl').read_text().splitlines()]
    index=1 if field in ('call_id','frame','task_key')else 3 if field in('last_call_id','step')else 4
    rows[index][field]={'sr':0}if field=='native_metrics'else 'WRONG'
    (b.work/'trace.jsonl').write_text(''.join(json.dumps(x)+'\n'for x in rows))
    seal(a);seal(b);a.finalize(audit_single(a));b.finalize(audit_single(b))
    assert not audit_pair(a,b)['business_equivalence']['equal']

@pytest.mark.parametrize('kind',['missing','forged','active_capability','wrong_attempt'])
def test_session_revocation_is_required_even_when_process_lives(tmp_path,kind):
    a,b=pair(tmp_path);release=released(a)
    if kind=='missing':release.pop('session_receipts')
    elif kind=='forged':release['session_receipts']['fixture_files']['signature']='0'*64
    elif kind=='wrong_attempt':release['session_receipts']['fixture_files']['payload']['identity']['attempt']='wrong'
    else:
        guard=(a.result/'owner_sessions/fixture_files.lock').open('a+b')
        import fcntl
        fcntl.flock(guard,fcntl.LOCK_SH)
    try:
        with pytest.raises(LifecycleError):a.seal(trace=a.work/'trace.jsonl',image_root=a.work,summary={},release=release)
    finally:
        if kind=='active_capability':guard.close()
    assert process_identity(os.getpid())is not None and a.work.exists()

def test_actual_worker_end_episode_helper_revokes_session_without_model_process_exit(tmp_path):
    from graphAdapter.map_memory.worker import release_memory_episode,MemoryWorkerClient
    config=plan();config["owner_roles"]=["memory"];config["owner_components"]={"memory":"memory"}
    root=tmp_path/"worker-run";h=EpisodeLifecycle.create_run(root,config)
    ep=EpisodeLifecycle(root,"e1","shadow","a",plan_sha256=h);ep.create_work()
    session=EpisodeSession(ep,"memory")
    store=EpisodeStore(ep.work/"memory",EP,dataset="r2r");archive(store,1);publish(store,[1])
    client=MemoryWorkerClient.__new__(MemoryWorkerClient);client.active_episode=EP
    def rpc_fixture(request):
        assert request["op"]=="end_episode"
        return release_memory_episode(store,owner_session=session)
    client.call=rpc_fixture
    result=client.end_episode([])
    assert client.active_episode is None
    assert result["release"]["memory_closed"] and result["release"]["pins_zero"]
    assert result["session_acknowledgement"]["payload"]["session_revoked"]
    assert process_identity(os.getpid())is not None

def test_actual_host_terminal_and_runner_finalizer_path(tmp_path,monkeypatch):
    from case1_runtime.trace import TraceRecorder
    from graphAdapter.evaluation.runner import finalize_retained_episode
    from types import SimpleNamespace
    config=plan();config["owner_roles"]=["host"];config["owner_components"]={"host":"host_trace"}
    root=tmp_path/"host-run";h=EpisodeLifecycle.create_run(root,config)
    ep=EpisodeLifecycle(root,"e1","control","a",plan_sha256=h);ep.create_work()
    session=EpisodeSession(ep,"host")
    monkeypatch.setenv("CASE2_RUN_UID","cpu-real-trace-method")
    monkeypatch.setenv("CASE2_ATTEMPT_ID","a");monkeypatch.setenv("CASE2_DATASET_KEY","r2r")
    recorder=TraceRecorder(ep.work/"host","r2r")
    (recorder.root/"effective-config.yaml").write_text("CPU_CONTRACT: true\n")
    member=SimpleNamespace(scene_id="mp3d/fixture/fixture.glb",episode_id="1",instruction=SimpleNamespace(instruction_id=None))
    recorder.ensure_episode(member,dict(elapsed_steps=0))
    recorder.step(member,0,dict(elapsed_steps=0),dict(elapsed_steps=1),True,
                  dict(success=0.,spl=0.,ndtw=0.,distance_to_goal=2.,oracle_success=0.))
    acknowledgement=session.close_trace(recorder)
    release=copy.deepcopy(RELEASE);release["session_receipts"]={"host":acknowledgement}
    request=dict(trace=recorder.directory/"trace.jsonl",image_root=ep.work,
                 summary=json.loads((recorder.directory/"result.json").read_bytes()),release=release)
    result=finalize_retained_episode(ep,request)
    assert result["retention"]["trace_audit"]["status"]=="VERIFIED"
    assert result["finalization"]["deleted"] and not ep.work.exists()
    assert result["retention"]["summary"]["metrics"]["sr"]==0.
    repeated=finalize_retained_episode(ep,request)
    assert repeated==result

def test_same_aborted_traces_are_same_failure_not_complete_success(tmp_path):
    a,b=pair(tmp_path)
    for ep in (a,b):
        rows=[json.loads(x)for x in(ep.work/"trace.jsonl").read_text().splitlines()]
        rows[-1]=dict(kind="attempt_aborted",steps=1,reason="fixture interruption")
        (ep.work/"trace.jsonl").write_text("".join(json.dumps(x)+"\n"for x in rows))
        seal(ep);ep.finalize(audit_single(ep))
    result=audit_pair(a,b)
    assert result["business_equivalence"]["equal"] and not result["complete_success"]
    assert result["failure_denominator_preserved"]

def test_wrong_member_is_detected_before_source_release(tmp_path):
    a,b=pair(tmp_path)
    rows=[json.loads(x)for x in(b.work/"trace.jsonl").read_text().splitlines()]
    rows[0]["episode_scope"]["member"]=["wrong"]
    (b.work/"trace.jsonl").write_text("".join(json.dumps(x)+"\n"for x in rows))
    with pytest.raises(LifecycleError,match="member"):seal(b)
    assert b.work.exists()

def test_deleted_trace_detects_image_slot_swap_with_individually_valid_pixels(tmp_path):
    a,b=pair(tmp_path)
    for ep in (a,b):
        Image.fromarray(np.zeros((4,4,3),np.uint8)).save(ep.work/'second.png')
        with Image.open(ep.work/'second.png')as im:
            digest=hashlib.sha256(im.mode.encode()+str(im.size).encode()+im.tobytes()).hexdigest()
        rows=[json.loads(x)for x in(ep.work/'trace.jsonl').read_text().splitlines()]
        refs=[rows[1]['images'][0],dict(path='second.png',pixel_sha256=digest,size=[4,4],mode='RGB')]
        if ep.side=='shadow':refs.reverse()
        rows[1]['images']=refs;rows[2]['images']=refs
        (ep.work/'trace.jsonl').write_text(''.join(json.dumps(x)+'\n'for x in rows))
        seal(ep);ep.finalize(audit_single(ep))
    assert not audit_pair(a,b)['business_equivalence']['equal']

def test_actual_000_hook_optional_source_map_archive_preserves_pose_and_ipc_inputs(tmp_path):
    from graphAdapter.observation_pose.aware_hook import AwarePoseHook
    from graphAdapter.observation_pose.tests.fixtures import sensor_spec,adapter_factory
    from graphAdapter.observation_pose.alignment import array_hash
    profile_path=Path(__file__).parents[2]/"observation_pose/profiles/000_pose_shadow.json"
    original=json.loads(profile_path.read_bytes())
    hooks=[]
    captured=[]
    rgb=np.arange(8*8*3,dtype=np.uint8).reshape(8,8,3)
    depth=np.ones((8,8),np.float32)
    try:
        for keep in (True,False):
            cfg=copy.deepcopy(original);cfg["storage_lifecycle"]={"retain_source_pixel_map":keep}
            h=AwarePoseHook(tmp_path/("keep"if keep else"recompute"),cfg,adapter_factory=adapter_factory)
            hooks.append(h)
            packets=[h.reset("same-episode",sensor_spec(),rgb,depth,1,received_monotonic_ns=1)]
            packets.append(h.capture(rgb,depth,2,action_id=1,received_monotonic_ns=2))
            captured.append(packets)
            for packet in packets:
                folder=Path(packet.raw_rgb_ref).parent
                assert (folder/"source_pixel_map.npy").exists()==keep
                recomputed=h.align.align(np.load(packet.raw_rgb_ref),np.load(packet.raw_depth_ref))
                assert array_hash(np.load(packet.aligned_ref))==array_hash(recomputed.depth)
                assert array_hash(np.load(folder/"depth_valid_mask.npy"))==array_hash(recomputed.valid_mask)
            alignment_events=[x for x in json_rows(h.coordinator.root/"flow_trace.jsonl")if x["kind"]=="alignment"]
            assert all(x["source_pixel_map_hash"]==array_hash(h.align.align(rgb,depth).source_pixel_map)for x in alignment_events)
        for left,right in zip(*captured):
            for attr in ("capture_seq","event_seq","sensor_timestamp_ns","calibration_hash","K","T_base_camera"):
                assert getattr(left,attr)==getattr(right,attr)
            for key in ("T_map_camera_cv","T_map_base","map_version","geometry_status"):
                assert left.pose_record.get(key)==right.pose_record.get(key)
            assert np.array_equal(np.load(left.raw_rgb_ref),np.load(right.raw_rgb_ref))
            assert np.array_equal(np.load(left.aligned_ref),np.load(right.aligned_ref))
    finally:
        for hook in hooks:hook.close()

@pytest.mark.parametrize("fault",["none","source_hash","mask_hash","declared_npy_missing","same_depth_other_sources","legacy"])
def test_recording_reader_checks_typed_recompute_storage_and_explicit_legacy(tmp_path,fault):
    from dataclasses import replace
    from graphAdapter.observation_pose.aware_hook import AwarePoseHook
    from graphAdapter.observation_pose.tests.fixtures import sensor_spec,adapter_factory
    from graphAdapter.observation_pose.alignment import array_hash,RGBDAlignmentBridge
    from graphAdapter.evaluation.recordings import CommittedRecording
    from graphAdapter.map_memory.storage.store import IntegrityError
    cfg=json.loads((Path(__file__).parents[2]/"observation_pose/profiles/000_pose_shadow.json").read_bytes())
    cfg["storage_lifecycle"]={"retain_source_pixel_map":fault=="declared_npy_missing"}
    hook=AwarePoseHook(tmp_path/"recorded",cfg,adapter_factory=adapter_factory)
    try:
        packet=hook.reset("recorded-ep",sensor_spec(),np.zeros((8,8,3),np.uint8),np.ones((8,8),np.float32),1)
        events=list(json_rows(hook.coordinator.root/"flow_trace.jsonl"))
        raw=next(x for x in events if x["kind"]=="raw_archive")
        alignment=copy.deepcopy(next(x for x in events if x["kind"]=="alignment"))
        reader=CommittedRecording.__new__(CommittedRecording)
        reader.root=hook.coordinator.root;reader._bridges={packet.episode_uid:hook.align}
        reader.legacy_alignment_storage=False
        if fault=="source_hash":alignment["source_pixel_map_hash"]="0"*64
        elif fault=="mask_hash":alignment["valid_mask_typed_hash"]="0"*64
        elif fault=="declared_npy_missing":(Path(packet.aligned_ref).parent/"source_pixel_map.npy").unlink()
        elif fault=="same_depth_other_sources":
            old=hook.align
            alternate=RGBDAlignmentBridge(replace(old.rgb_cal,fx=old.rgb_cal.fx*2,fy=old.rgb_cal.fy*2),
                old.depth_cal,old.spec,old.T,invalid_values=(0.,))
            a=old.align(np.zeros((8,8,3),np.uint8),np.ones((8,8),np.float32))
            b=alternate.align(np.zeros((8,8,3),np.uint8),np.ones((8,8),np.float32))
            assert np.array_equal(a.depth,b.depth) and array_hash(a.source_pixel_map)!=array_hash(b.source_pixel_map)
            reader._bridges={packet.episode_uid:alternate}
            packet=replace(packet,calibration_hash=alternate.calibration_hash)
        elif fault=="legacy":
            for key in ["source_pixel_map_storage","source_pixel_map_hash","valid_mask_typed_hash"]:alignment.pop(key)
            with pytest.raises(IntegrityError,match="Legacy"):reader.materialize(packet,raw,alignment)
            reader.legacy_alignment_storage=True
        if fault in("none","legacy"):
            result=reader.materialize(packet,raw,alignment)
            assert result["committed_receipt"]["alignment"]["source_pixel_map_hash"]
        else:
            with pytest.raises(IntegrityError):reader.materialize(packet,raw,alignment)
    finally:hook.close()

def test_remote_memory_ticket_scope_mac_and_host_revoke_are_separate(tmp_path):
    from graphAdapter.map_memory.worker import release_memory_episode
    from graphAdapter.map_memory.storage.lifecycle import verify_session_receipts
    config=plan();config["owner_roles"]=["memory"];config["owner_components"]={"memory":"memory"}
    h=EpisodeLifecycle.create_run(tmp_path/"remote-run",config)
    ep=EpisodeLifecycle(tmp_path/"remote-run","e1","shadow","r",plan_sha256=h);ep.create_work()
    owner=EpisodeSession(ep,"memory")
    store=EpisodeStore(ep.work/"memory",EP,dataset="r2r");archive(store,1);publish(store,[1])
    ticket=owner.bind_remote_memory(store.root,EP)
    wrong=copy.deepcopy(ticket);wrong["expected_episode_uid"]="wrong"
    with pytest.raises(LifecycleError):release_memory_episode(store,remote_ticket=wrong)
    assert store.connection is not None
    closed=release_memory_episode(store,remote_ticket=ticket)
    ack=closed["session_acknowledgement"]
    with pytest.raises(LifecycleError):verify_session_receipts(ep,{"memory":ack})
    forged=copy.deepcopy(ack);forged["payload"]["observed"]["root"]="wrong"
    with pytest.raises(LifecycleError):owner.accept_remote_acknowledgement(forged)
    assert not owner.closed
    owner.accept_remote_acknowledgement(ack)
    assert verify_session_receipts(ep,{"memory":ack})["session_capabilities_revoked"]

def test_attempt_limit_counts_retained_failures_not_only_active_work(tmp_path):
    a,b=pair(tmp_path)
    second=EpisodeLifecycle(a.root,a.key,a.side,'attempt1',plan_sha256=a.plan_sha);second.create_work()
    third=EpisodeLifecycle(a.root,a.key,a.side,'attempt2',plan_sha256=a.plan_sha)
    with pytest.raises(LifecycleError,match='attempt count'):third.create_work()
    assert a.result.exists()and second.result.exists()

@pytest.mark.parametrize('mode',['preview_only','graph_metadata_only'])
def test_every_capability_artifact_hash_is_checked_before_source_cleanup(tmp_path,mode):
    a,b=pair(tmp_path,mode)
    for ep in(a,b):
        if mode=='preview_only':seal(ep,preview=ep.work/'rgb.png')
        else:
            (ep.work/'graph.json').write_text(json.dumps(dict(nodes=[],edges=[],revision='r')))
            seal(ep,graph_metadata=ep.work/'graph.json')
    audit=audit_pair(a,b)
    artifact=a.result/('preview.png'if mode=='preview_only'else'graph.json')
    artifact.write_bytes(b'corrupted')
    with pytest.raises(LifecycleError):a.finalize(audit)
    assert a.work.exists()

def test_diagnostic_capability_rejects_package_that_cannot_fit_expanded_bound(tmp_path):
    cfg=plan('queryable');cfg['max_expanded_bytes']=16
    root=tmp_path/'too-large';h=EpisodeLifecycle.create_run(root,cfg)
    ep=EpisodeLifecycle(root,'e1','shadow','a',plan_sha256=h);ep.create_work()
    store=EpisodeStore(ep.work/'memory',EP,dataset='r2r');archive(store,1);publish(store,[1]);store.close()
    (ep.work/'trace.jsonl').write_text(json.dumps(dict(kind='reset',episode_scope=dict(member=MEMBER)))+'\n')
    with pytest.raises(LifecycleError,match='expanded bound'):seal(ep,memory=ep.work/'memory')
    assert ep.work.exists()and ep._state()['state']=='ACTIVE'

def test_repeated_pair_audit_does_not_rewrite_published_receipt(tmp_path):
    a,b=pair(tmp_path);seal(a);seal(b);audit_single(a);audit_single(b)
    first=audit_pair(a,b)
    path=next((a.root/'reports').glob('*.json'));before=path.stat()
    assert audit_pair(a,b)==first
    after=path.stat();assert(after.st_ino,after.st_mtime_ns)==(before.st_ino,before.st_mtime_ns)
    receipt=json.loads((a.result/'retention.json').read_bytes());receipt['summary']['status']='tampered'
    (a.result/'retention.json').write_text(json.dumps(receipt))
    with pytest.raises(LifecycleError,match='metadata identity'):audit_pair(a,b)

def test_actual_snapshot_metadata_export_does_not_claim_rgb_or_rebuildability(tmp_path):
    a,b=pair(tmp_path,'graph_metadata_only')
    store=EpisodeStore(a.work/'memory',EP,dataset='r2r');archive(store,1);publish(store,[1]);store.close()
    result=seal(a,memory=a.work/'memory')
    data=json.loads((a.result/'graph.json').read_bytes())
    assert len(data['nodes']['views'])==1 and data['revision']
    assert data['source_capabilities']==dict(queryable=False,rebuildable=False)
    assert result['capabilities']==['graph_metadata_only']

def test_same_budget_truncation_preserves_native_metric_without_claiming_full_success(tmp_path):
    a,b=pair(tmp_path)
    for ep in(a,b):
        rows=[json.loads(x)for x in(ep.work/'trace.jsonl').read_text().splitlines()]
        rows[-1]['native_metrics']={'success':1.0}
        (ep.work/'trace.jsonl').write_text(''.join(json.dumps(x)+'\n'for x in rows));seal(ep)
    result=audit_pair(a,b)
    assert result['complete_execution_equivalent']and result['native_navigation_success']
    assert not result['complete_success']

def test_public_runner_finalizer_resumes_authorized_partial_delete_without_sources(tmp_path):
    from graphAdapter.evaluation.runner import finalize_retained_episode
    a,b=pair(tmp_path);seal(a)
    audited=audit_single(a)
    def fail(stage):
        if stage=='file_deleted':raise RuntimeError('public retry fault')
    with pytest.raises(RuntimeError):a.finalize(audited,fault=fail)
    result=finalize_retained_episode(a,{})
    assert result['finalization']['deleted']and not a.work.exists()
