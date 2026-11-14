"""Minimum A selector/report contracts;synthetic results never count as navigation."""
from pathlib import Path
import json,hashlib
import pytest
from graphAdapter.evaluation.selector import selected_rows,shard
from graphAdapter.evaluation.report import first_difference,report

def seal(tmp_path,identities,dataset="r2r"):
    f=tmp_path/"A.json";f.write_text(json.dumps(dict(identities=identities)))
    data=dict(manifests={dataset:{"A":dict(file=f.name,sha256=hashlib.sha256(f.read_bytes()).hexdigest())}})
    (tmp_path/"seal.json").write_text(json.dumps(data))
def row(eid,instruction="i"):
    return dict(scene_id="mp3d/scan/scan.glb",episode_id=eid,instruction=dict(instruction_id=instruction,language="en-US"))
def test_E00_full_identity_required_when_display_id_ambiguous(tmp_path):
    seal(tmp_path,[["1"]]);annotation=dict(episodes=[row("1","i1"),row("1","i2")])
    with pytest.raises(ValueError,match="ambiguous"):selected_rows(tmp_path,"r2r","A",annotation)
    seal(tmp_path,[["r2r","mp3d/scan/scan.glb","1","i2"]])
    chosen=selected_rows(tmp_path,"r2r","A",annotation)
    assert chosen[0]["row"]["instruction"]["instruction_id"]=="i2"

def test_E00_seal_missing_duplicate_language_and_hash_rejected(tmp_path):
    seal(tmp_path,[["2"]])
    with pytest.raises(ValueError):selected_rows(tmp_path,"r2r","A",dict(episodes=[row("1")]))
    seal(tmp_path,[["1"],["1"]])
    with pytest.raises(ValueError,match="Duplicate selected"):selected_rows(tmp_path,"r2r","A",dict(episodes=[row("1")]))
    (tmp_path/"A.json").write_text("{}")
    with pytest.raises(ValueError,match="changed"):selected_rows(tmp_path,"r2r","A",dict(episodes=[row("1")]))

def test_E01_sealed_index_shards_have_exact_union_and_no_overlap():
    source=list(range(103));groups=[shard(source,i,4)for i in range(4)]
    assert sorted(x for part in groups for x in part)==source
    assert sum(map(len,groups))==len(set(x for part in groups for x in part))
    for args in ((True,4),(0,False),(-1,2),(2,2)):
        with pytest.raises(ValueError):shard(source,*args)

def test_G13_E05_first_difference_is_identified_not_ignored():
    a=[dict(kind="model_input",prompt="a",input_ids=[1],processed_image_shape=[1],processed_image_sha256="h",generation={},stop_str="x",sep2="y",images=[])]
    b=[dict(a[0],prompt="b")]
    assert first_difference(a,b)==dict(kind="model_input",index=0,left_count=1,right_count=1)
    assert first_difference(a,a)is None

def test_E02_fixed_fullA_failure_denominator_and_native_metric_NA(tmp_path):
    roots=[tmp_path/"candidate",tmp_path/"control"]
    identity=dict(source_sha256="s",profile_sha256="p",registry_sha256="r",partition="A",smoke=False)
    for root in roots:
        root.mkdir();(root/"run_identity.json").write_text(json.dumps(identity))
        for dataset,count in (("r2r",612),("rxr_us",407)):
            domain=root/dataset;worker=domain/"worker";worker.mkdir(parents=True)
            registered=[dict(identity=[dataset,"mp3d/scan/scan.glb",str(i),"i"])for i in range(count)]
            (domain/"registered_identities.json").write_text(json.dumps(registered))
            (worker/"hook-load.json").write_text(json.dumps(dict(completed=True,hook_enabled=False,
                broker_supplied=False,memory_broker_supplied=False,memory_worker_started=False,loaded_graph_modules=[])))
    output=report(roots[0],roots[1],out=tmp_path/"report")
    assert output["status"]=="FAIL_OR_INCOMPLETE_ENGINEERING"
    for result,denominator in zip(output["domains"],(612,407)):
        assert result["fixed_denominator"]==denominator
        assert result["SR"]==dict(shadow=0.,control=0.)
        assert result["native_metrics"]["ne"]["shadow"]["mean"]is None
        assert result["native_metrics"]["ne"]["shadow"]["coverage"]==0
    assert output["failed_or_missing_count"]==2*(612+407)


def test_G13_earliest_output_divergence_precedes_its_later_input_symptom():
    first=dict(kind="model_input",prompt="same",images=[])
    output=dict(kind="model_call",output_ids=[1],raw_decoded_output="one",normalized_output="one")
    next_input=dict(kind="model_input",prompt="later",images=[])
    left=[first,output,next_input]
    right=[first,dict(output,output_ids=[2]),dict(next_input,prompt="changed")]
    assert first_difference(left,right)==dict(kind="model_call",index=0,left_count=1,right_count=1)

def test_G13_image_pixel_divergence_precedes_later_generated_output():
    first=dict(kind="model_input",prompt="same",images=[dict(pixel_sha256="a",size=[32,32],mode="RGB")])
    last=dict(kind="model_call",output_ids=[1])
    assert first_difference([first,last],[dict(first,images=[dict(pixel_sha256="b",size=[32,32],mode="RGB")]),dict(last,output_ids=[2])])==dict(kind="image_slots_pixels",index=0)


def test_E05_actual_host_image_and_cost_evidence_cannot_be_replaced_by_matching_logs(tmp_path):
    from graphAdapter.evaluation.report import _audit_host
    from PIL import Image
    domain=tmp_path/"domain";episode=domain/"worker/episodes/e";episode.mkdir(parents=True)
    image=domain/"worker/images/a.png";image.parent.mkdir()
    im=Image.new("RGB",(4,4),(1,2,3));im.save(image)
    digest=hashlib.sha256(im.mode.encode()+str(im.size).encode()+im.tobytes()).hexdigest()
    source=dict(call_id=1,prompt="x",images=[dict(path="worker/images/a.png",pixel_sha256=digest,size=[4,4],mode="RGB")],
        input_ids=[[1]],processed_image_sha256="actual-hash",generation=dict(do_sample=False,temperature=0.,max_new_tokens=256),stop_str="END",sep2="SEP")
    trace=[dict(kind="reset"),dict(kind="model_input",**source),
        dict(kind="model_call",**source,output_ids=[[2]],raw_decoded_output="stop",normalized_output="stop"),
        dict(kind="primitive_action",step=1,action=0,last_call_id=1,done=True,stop_source="model"),
        dict(kind="terminal",steps=1,model_calls=1,native_metrics=dict(success=1.,spl=1.,ndtw=1.,distance_to_goal=0.))]
    config=domain/"worker/effective-config.yaml";config.write_text("config")
    (episode/"model_costs.jsonl").write_text(json.dumps(dict(call_id=1,seconds=.25))+"\n")
    (episode/"host_cost.json").write_text("{}")
    entry=dict(trace=trace,path=str(episode/"trace.jsonl"),result=dict(status="completed",metrics=dict(sr=1.,spl=1.,ndtw=1.,ne=0.),effective_config_sha256=hashlib.sha256(config.read_bytes()).hexdigest()))
    verified=_audit_host(entry,domain,{})
    assert verified["status"]=="VERIFIED"and verified["tokens"]==dict(input=1,output=1)
    assert verified["model_boundary_latency_seconds"]["p95"]==.25
    Image.new("RGB",(4,4),(3,2,1)).save(image)
    assert "host_image_hash_or_grid_mismatch"in _audit_host(entry,domain,{})["errors"]
    (episode/"host_cost.json").unlink()
    assert "missing_host_cost"in _audit_host(entry,domain,{})["errors"]


def test_E02_native_success_requires_exact_official_terminal_metric_and_finite_units():
    from graphAdapter.evaluation.report import _native_complete
    result=dict(status="completed",metrics=dict(sr=1.,spl=.5,ndtw=.4,ne=1.))
    trace=[dict(kind="terminal",native_metrics=dict(success=1.,spl=.5,ndtw=.4,distance_to_goal=1.))]
    assert _native_complete(dict(result=result,trace=trace))
    for value in (0.,float("nan"),2.):
        changed=dict(result,metrics=dict(result["metrics"],sr=value))
        assert not _native_complete(dict(result=changed,trace=trace))


def test_E03_E07_online_gates_reject_missing_or_drifted_prerequisites_before_models(tmp_path):
    from graphAdapter.evaluation.runner import verify_map_prerequisites
    config={"geometry":{"voxel_size":.1}}
    profile=dict(map_memory=config)
    with pytest.raises(RuntimeError,match="missing or changed"):verify_map_prerequisites(tmp_path,profile)
    code=tmp_path/"source.py";code.write_text("actual code")
    config_hash=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    lock=dict(status="READY_FOR_16_PER_DOMAIN",code_files=[dict(path=str(code),sha256=hashlib.sha256(code.read_bytes()).hexdigest())],
        evidence_files=[],asset_locks=[],map_memory_config_sha256=config_hash)
    path=tmp_path/"prerequisites.json";path.write_text(json.dumps(lock))
    profile.update(prerequisite_lock=str(path),prerequisite_lock_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert verify_map_prerequisites(tmp_path,profile)==lock
    with pytest.raises(RuntimeError,match="completed16"):verify_map_prerequisites(tmp_path,profile,full_A=True)
    code.write_text("different code")
    with pytest.raises(RuntimeError,match="source/evidence drift"):verify_map_prerequisites(tmp_path,profile)


def test_E01_metadata_only_collection_has_exact_union_and_detects_shard_drift(tmp_path):
    from graphAdapter.evaluation.report import collect_shards,domain_sources
    family=tmp_path/"family";roots=[]
    for worker in range(4):
        root=family/"shards"/str(worker);root.mkdir(parents=True);roots.append(root)
        identity=dict(stage="001",partition="A",smoke=True,hook_mode="off",method="baseline",sidecar_feature="disabled",source_sha256="s",
            profile_sha256="p",registry_sha256="r",run_uid=str(worker),shard=dict(worker_count=4,worker_index=worker))
        (root/"run_identity.json").write_text(json.dumps(identity))
        for name in ("effective_config.json","acceptance_policy.json"):(root/name).write_text("{}")
        for dataset in ("r2r","rxr_us"):
            (root/dataset).mkdir()
            rows=[dict(identity=[dataset,"mp3d/s/s.glb",str(i),"i"],registered_identity=[str(i)],sealed_index=i)for i in range(worker,16,4)]
            (root/dataset/"registered_identities.json").write_text(json.dumps(rows))
    collected=family/"control";status=collect_shards(roots,collected)
    assert status==dict(shards=4,members=dict(r2r=16,rxr_us=16),raw_evidence_copied=False)
    assert domain_sources(collected,"r2r")==[root/"r2r"for root in roots]
    assert not(collected/"r2r/worker").exists()
    with pytest.raises(ValueError,match="Missing/duplicate"):collect_shards(roots[:3],family/"bad")
    (roots[0]/"run_identity.json").write_text("{}")
    with pytest.raises(ValueError,match="changed"):domain_sources(collected,"r2r")

def test_E03_paired_native_config_budget_and_model_receipt_are_checked(tmp_path):
    from graphAdapter.evaluation.report import paired_protocol
    import yaml
    roots=[tmp_path/"candidate",tmp_path/"control"]
    required=("checkpoint","python","prefix","torch","transformers","model_class","mode_token_ids",
        "tokenizer_size","dtype","num_video_frames","source_sha256")
    receipt={k:"same"for k in required}
    for root in roots:
        domain=root/"r2r";worker=domain/"worker";worker.mkdir(parents=True)
        (root/"run_identity.json").write_text(json.dumps(dict(resource_budget=dict(gpus=[5],cpu=[32]),shard=dict(worker_index=0))))
        config=dict(RESULTS_DIR=str(worker/"native"),TASK_CONFIG=dict(ENVIRONMENT=dict(MAX_EPISODE_STEPS=500),DATASET=dict(DATA_PATH=str(domain/"annotation.json.gz"))))
        (worker/"effective-config.yaml").write_text(yaml.safe_dump(config))
        (worker/"model-receipt.json").write_text(json.dumps(receipt))
    assert paired_protocol(*roots,"r2r")==[dict(worker=0,status="VERIFIED")]
    path=roots[0]/"r2r/worker/effective-config.yaml";bad=yaml.safe_load(path.read_text())
    bad["TASK_CONFIG"]["ENVIRONMENT"]["MAX_EPISODE_STEPS"]=501;path.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError,match="protocol mismatch"):paired_protocol(*roots,"r2r")


def test_E03_geometry_shadow_passes_actual_baseline_policy_gate_without_weakening_it(tmp_path,monkeypatch):
    from graphAdapter.evaluation.runner import navigation_policy_identity
    from hamlet_v2.policy import bind_worker
    root=Path(__file__).resolve().parents[4]
    monkeypatch.setenv("CASE2_HAMLET_CONFIG","stale")
    run=tmp_path/"run";run.mkdir()
    policy=navigation_policy_identity(True,"on")
    assert policy==dict(method="baseline",sidecar_feature="geometry_shadow")
    (run/"run_manifest.json").write_text(json.dumps(dict(policy,stage="001")))
    bind_worker(root,run)
    import os
    assert "CASE2_HAMLET_CONFIG"not in os.environ
    (run/"run_manifest.json").write_text(json.dumps(dict(method="geometry_shadow",stage="001")))
    with pytest.raises(ValueError,match="Missing candidate policy binding"):bind_worker(root,run)

def test_E03_actual_worker_environment_turns_sidecar_on_and_both_features_off(tmp_path,monkeypatch):
    from graphAdapter.evaluation.runner import navigation_policy_identity,navigation_worker_environment
    from hamlet_v2.policy import bind_worker
    root=Path(__file__).resolve().parents[4]
    profile=root/"src/graphAdapter/map_memory/profiles/000_geometry_shadow.json"
    assert json.loads(profile.read_text())["map_memory"]["enabled"]is True
    base=dict(CASE2_HAMLET_CONFIG="stale",POSEADAPTER_BROKER="pose",GRAPH_MEMORY_BROKER="memory",
        POSEADAPTER_BROKER_PID="1",GRAPH_MEMORY_BROKER_PID="2",CASE2_POSE_PROFILE="old")
    for hook in ("on","off"):
        run=tmp_path/hook;run.mkdir()
        manifest=dict(navigation_policy_identity(True,hook),stage="001",hook_mode=hook)
        (run/"run_manifest.json").write_text(json.dumps(manifest))
        env=navigation_worker_environment(base,domain=run,source_sha="s",run_uid="r",attempt_id="a",
            dataset="r2r",map_stage=True,hook_mode=hook,profile_path=profile)
        assert "CASE2_HAMLET_CONFIG"not in env
        if hook=="on":
            assert env["CASE2_POSE_PROFILE"]==str(profile)
            assert env["GRAPH_MEMORY_BROKER"]=="memory"and env["POSEADAPTER_BROKER"]=="pose"
        else:
            assert not set(env)&{"CASE2_POSE_PROFILE","GRAPH_MEMORY_BROKER","POSEADAPTER_BROKER","GRAPH_MEMORY_BROKER_PID","POSEADAPTER_BROKER_PID"}
        bind_worker(root,run)
        import os
        assert "CASE2_HAMLET_CONFIG"not in os.environ


def test_random32_presealed_selection_preserves_original_index_and_exact_shards(tmp_path):
    import copy
    from graphAdapter.evaluation.selector import validate_registered_selection
    source=[row(str(i),"-")for i in range(40)]
    seal(tmp_path,[[str(i)]for i in range(40)])
    indices=list(range(8,40,2))
    spec=dict(status="FROZEN_BEFORE_RANDOM32_EXECUTION",stage="001",partition="A",total=32,
        original_registry=str(tmp_path),original_registry_sha256=hashlib.sha256((tmp_path/"seal.json").read_bytes()).hexdigest(),
        selected={"r2r":[dict(identity=["r2r","mp3d/scan/scan.glb",str(i),"-"],
            registered_identity=[str(i)],original_sealed_index=i,sample_index=n)for n,i in enumerate(indices)]})
    manifest=tmp_path/"sample.json";manifest.write_text(json.dumps(spec))
    checksum=hashlib.sha256(manifest.read_bytes()).hexdigest()
    selected=selected_rows(tmp_path,"r2r","A",dict(episodes=source),16,
        selection_manifest=manifest,selection_sha256=checksum)
    assert [x["sealed_index"]for x in selected]==indices
    assert [x["selection_index"]for x in selected]==list(range(16))
    groups=[shard(selected,i,4)for i in range(4)]
    assert all([x["selection_index"]for x in part]==list(range(i,16,4))for i,part in enumerate(groups))
    registered=[{k:v for k,v in x.items()if k!="row"}for x in selected]
    validate_registered_selection(registered,"r2r",manifest,checksum)
    bad=copy.deepcopy(registered);bad[0]["sealed_index"]=0
    with pytest.raises(ValueError,match="differs"):validate_registered_selection(bad,"r2r",manifest,checksum)
    with pytest.raises(ValueError,match="checksum"):
        selected_rows(tmp_path,"r2r","A",dict(episodes=source),16,selection_manifest=manifest,selection_sha256="0"*64)
    spec["selected"]["r2r"][0]["identity"][2]="wrong"
    manifest.write_text(json.dumps(spec));changed=hashlib.sha256(manifest.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match="full annotation"):
        selected_rows(tmp_path,"r2r","A",dict(episodes=source),16,selection_manifest=manifest,selection_sha256=changed)


def native_entry():
    return dict(result=dict(status="completed",metrics=dict(sr=0.,spl=.2,ndtw=.4,ne=5.)),
        trace=[dict(kind="terminal",native_metrics=dict(success=0.,spl=.2,ndtw=.4,distance_to_goal=5.))])

def test_native_nonfinite_is_per_metric_NA_with_complete_matching_execution():
    from graphAdapter.evaluation.report import _native_result_audit,_native_complete
    entry=native_entry()
    for target in (entry["result"]["metrics"],entry["trace"][-1]["native_metrics"]):
        target["spl"]={"nonfinite":"nan"}
    entry["result"]["metrics"]["ne"]={"nonfinite":"inf"}
    entry["trace"][-1]["native_metrics"]["distance_to_goal"]={"nonfinite":"inf"}
    audit=_native_result_audit(entry)
    assert audit["execution_complete"]and audit["native_evidence_matched"]and _native_complete(entry)
    assert audit["metric_availability"]==dict(sr="finite",spl="native_nonfinite",ndtw="finite",ne="native_nonfinite")
    assert entry["result"]["metrics"]["ne"]=={"nonfinite":"inf"}

@pytest.mark.parametrize("case",["missing","finite_mismatch","nonfinite_mismatch","illegal_SR","boolean_SR",
    "out_of_range","negative_distance","negative_infinity","malformed_tag","extra_tag_key","exception","unclosed","invalid_structure"])
def test_native_missing_mismatch_invalid_scores_and_malformed_tags_remain_failures(case):
    from graphAdapter.evaluation.report import _native_result_audit,_native_complete
    entry=native_entry();metrics=entry["result"]["metrics"];native=entry["trace"][-1]["native_metrics"]
    if case=="missing":metrics.pop("spl")
    elif case=="finite_mismatch":metrics["spl"]=.3
    elif case=="nonfinite_mismatch":metrics["spl"]={"nonfinite":"nan"}
    elif case=="illegal_SR":metrics["sr"]=native["success"]=.5
    elif case=="boolean_SR":metrics["sr"]=native["success"]=False
    elif case=="out_of_range":metrics["spl"]=native["spl"]=1.1
    elif case=="negative_distance":metrics["ne"]=native["distance_to_goal"]=-1.
    elif case=="negative_infinity":metrics["ne"]=native["distance_to_goal"]={"nonfinite":"-inf"}
    elif case=="malformed_tag":metrics["ne"]=native["distance_to_goal"]={"nonfinite":[]}
    elif case=="extra_tag_key":metrics["ne"]=native["distance_to_goal"]={"nonfinite":"inf","guess":0}
    elif case=="exception":entry["result"]["status"]="failed"
    elif case=="unclosed":entry["trace"][-1]["kind"]="model_call"
    elif case=="invalid_structure":entry["result"]["metrics"]=None
    audit=_native_result_audit(entry)
    assert not audit["native_evidence_matched"]and audit["errors"]and not _native_complete(entry)

def test_frozen_policy_byte_copy_and_real_threshold_drift_rejection(tmp_path):
    from graphAdapter.evaluation.registry_binding import copy_frozen_json,verify_frozen_json_copy,AuditError
    original=tmp_path/"original.json";original.write_bytes(b'{"geometry":0.9,"perception":0.9}\n')
    checksum=hashlib.sha256(original.read_bytes()).hexdigest();copy=tmp_path/"copy.json"
    assert copy_frozen_json(original,copy,checksum)["status"]=="VERIFIED_EXACT_BYTES"
    assert copy.read_bytes()==original.read_bytes()
    copy.write_text(json.dumps(json.loads(original.read_bytes()),indent=2)+"\n")
    with pytest.raises(AuditError,match="copy_byte_mismatch"):verify_frozen_json_copy(original,copy,checksum)
    copy.write_text('{"geometry":0.8,"perception":0.9}')
    with pytest.raises(AuditError,match="content_drift"):verify_frozen_json_copy(original,copy,checksum)
    original.write_text('{"geometry":0.8,"perception":0.9}')
    with pytest.raises(AuditError,match="source_hash_mismatch"):copy_frozen_json(original,tmp_path/"forbidden.json",checksum)
    assert not(tmp_path/"forbidden.json").exists()

@pytest.mark.parametrize("content",['{"geometry":0.9,"geometry":0.9}','{"geometry":NaN}'])
def test_frozen_policy_strict_JSON_rejects_duplicate_keys_and_nonfinite_constants(tmp_path,content):
    from graphAdapter.evaluation.registry_binding import copy_frozen_json,AuditError
    original=tmp_path/"source.json";original.write_text(content)
    checksum=hashlib.sha256(original.read_bytes()).hexdigest()
    with pytest.raises(AuditError):copy_frozen_json(original,tmp_path/"copy.json",checksum)

@pytest.mark.parametrize("failure",[None,"policy","execution","evidence","pair","memory"])
def test_engineering_acceptance_uses_execution_and_evidence_coverage_not_finite_metric_coverage(failure):
    from graphAdapter.evaluation.report import _engineering_acceptance
    domain=dict(fixed_denominator=16,all_pairs_equal=True,memory=dict(availability_gate=True),
        native_execution_coverage=dict(shadow=16,control=16),
        native_evidence_coverage=dict(shadow=16,control=16),
        native_metrics=dict(ne=dict(shadow=dict(coverage=15))))
    errors=[]
    if failure=="policy":errors=["policy_content_drift"]
    elif failure=="execution":domain["native_execution_coverage"]["control"]=15
    elif failure=="evidence":domain["native_evidence_coverage"]["shadow"]=15
    elif failure=="pair":domain["all_pairs_equal"]=False
    elif failure=="memory":domain["memory"]["availability_gate"]=False
    assert _engineering_acceptance(errors,[domain])is(failure is None)

