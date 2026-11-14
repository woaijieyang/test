"""Paired A-only shadow/control report;official results retain fixed denominators."""
from pathlib import Path
import json,hashlib,statistics,math
import numpy as np

def load(path):return json.loads(Path(path).read_bytes())
def rows(path):
    with Path(path).open()as f:return [json.loads(x)for x in f]
def signature(trace,kind,keys):
    return [[x.get(k)for k in keys]for x in trace if x["kind"]==kind]
def first_difference(a,b):
    # Compare the actual causal event order. A changed output can cause the next
    # changed input; grouping all inputs first would report the later symptom.
    fields={"model_input":["prompt","input_ids","processed_image_shape","processed_image_sha256","generation","stop_str","sep2"],
        "model_call":["output_ids","raw_decoded_output","normalized_output"],
        "primitive_action":["action","done","stop_source"],
        "terminal":["steps","model_calls","termination_reason","stop_source"]}
    left=[x for x in a if x["kind"]in fields]
    right=[x for x in b if x["kind"]in fields]
    ordinals={k:0 for k in fields}
    for x,y in zip(left,right):
        kind=x["kind"];index=ordinals[kind]
        if kind!=y["kind"]or any(x.get(k)!=y.get(k)for k in fields[kind]):
            return dict(kind=kind,index=index,
                left_count=sum(z["kind"]==kind for z in left),
                right_count=sum(z["kind"]==kind for z in right))
        if kind=="model_input":
            images=lambda z:[(i["pixel_sha256"],i.get("size"),i.get("mode"))for i in z.get("images",[])]
            if images(x)!=images(y):return dict(kind="image_slots_pixels",index=index)
        ordinals[kind]+=1
    if len(left)!=len(right):
        kind=(left if len(left)>len(right)else right)[min(len(left),len(right))]["kind"]
        return dict(kind=kind,index=ordinals[kind],
            left_count=sum(z["kind"]==kind for z in left),
            right_count=sum(z["kind"]==kind for z in right))
    return None

def trace_index(domain):
    index={}
    for path in (domain/"worker/episodes").glob("*/trace.jsonl"):
        trace=rows(path)
        if not trace:continue
        scope=trace[0].get("episode_scope")
        if scope is None:raise ValueError("Missing full episode scope")
        key=tuple(scope["member"])
        if key in index:raise ValueError("Duplicate full episode identity")
        result_path=path.parent/"result.json"
        result=load(result_path)if result_path.exists()else None
        if result is not None and hashlib.sha256(path.read_bytes()).hexdigest()!=result["trace_sha256"]:
            raise ValueError("Native result trace checksum mismatch")
        index[key]=dict(path=str(path),trace=trace,result=result,scope=scope)
    return index


def _parser_functions():
    """Reuse the existing official-parser auditor;do not invent a second parser."""
    import sys,importlib
    scripts=Path(__file__).resolve().parents[3]/"scripts"
    sys.path.insert(0,str(scripts))
    try:
        module=importlib.import_module("audit_model_trace")
        if Path(module.__file__).resolve()!=scripts/"audit_model_trace.py":
            raise ValueError("Parser auditor module address mismatch")
        return module.inspect,module.parse
    finally:sys.path.pop(0)

def _quantiles(values):
    return dict(count=len(values),p50=float(np.quantile(values,.5))if values else None,
        p95=float(np.quantile(values,.95))if values else None,total=sum(values)if values else None)

def _metric_availability(name,value):
    # Nonfinite tags are native facts, not numeric scores. Keep them for the
    # per-episode record while excluding only that metric from finite averages.
    if isinstance(value,dict):
        allowed={"spl":{"nan"},"ndtw":{"nan"},"ne":{"nan","inf"}}
        if set(value)=={"nonfinite"}and isinstance(value["nonfinite"],str)and value["nonfinite"]in allowed.get(name,set()):
            return "native_nonfinite"
        return "invalid"
    if isinstance(value,bool)or not isinstance(value,(int,float))or not math.isfinite(value)or value<0:
        return "invalid"
    if name in ("sr","spl","ndtw","sdtw")and value>1:return "invalid"
    if name=="sr"and value not in (0.,1.):return "invalid"
    return "finite"

def _native_result_audit(entry):
    result=entry.get("result")if entry is not None else None
    trace=entry.get("trace",[])if entry is not None else[]
    complete=bool(isinstance(result,dict)and result.get("status")=="completed"and trace and trace[-1].get("kind")=="terminal")
    errors=[];availability={}
    if not complete:
        errors.append("native_execution_missing_or_incomplete")
    else:
        metrics=result.get("metrics",{});native=trace[-1].get("native_metrics",{})
        if not isinstance(metrics,dict)or not isinstance(native,dict):
            return dict(execution_complete=True,native_evidence_matched=False,
                metric_availability={},errors=["invalid_native_metrics_structure"])
        for name,source in (("sr","success"),("spl","spl"),("ndtw","ndtw"),("ne","distance_to_goal")):
            if name not in metrics or source not in native:
                errors.append("missing_native_metric:"+name);availability[name]="missing";continue
            value=metrics[name];availability[name]=_metric_availability(name,value)
            if availability[name]=="invalid":errors.append("invalid_native_metric:"+name)
            if value!=native[source]:errors.append("native_result_metric_mismatch:"+name)
    return dict(execution_complete=complete,native_evidence_matched=complete and not errors,
        metric_availability=availability,errors=errors)

def _native_complete(entry):
    return _native_result_audit(entry)["native_evidence_matched"]

def _audit_host(entry,domain,image_cache,tokenizer=None):
    if entry is None:return dict(errors=["missing_host_trace"],status="MISSING")
    from PIL import Image
    inspect,parse=_parser_functions()
    trace=entry["trace"];errors,fallbacks=inspect(trace)
    pending={};reasons=streak=max_streak=0;input_tokens=output_tokens=0
    for event in trace:
        if event["kind"]=="model_input":
            key=event["call_id"]
            if key in pending:errors.append("duplicate_model_input")
            pending[key]=event
        elif event["kind"]=="model_call":
            before=pending.pop(event["call_id"],None)
            if before is None or any(event.get(k)!=v for k,v in before.items()if k not in ("kind","task_key")):
                errors.append("input_output_causal_pair_mismatch")
            if not all(event.get(k)for k in ("prompt","images","input_ids","processed_image_sha256","output_ids")):
                errors.append("missing_model_material")
            _,reason,_=parse(event["normalized_output"])
            reasons+=int(reason);streak=streak+1 if reason else 0;max_streak=max(max_streak,streak)
            flat=lambda v:sum(len(x)if isinstance(x,list)else 1 for x in v)
            input_tokens+=flat(event["input_ids"]);output_tokens+=flat(event["output_ids"])
            if tokenizer is not None:
                decoded=tokenizer.batch_decode(event["output_ids"],skip_special_tokens=False)[0].strip()
                if decoded!=event["raw_decoded_output"]:errors.append("output_tokens_text_mismatch")
            for ref in event["images"]:
                path=(domain/ref["path"]).resolve()
                if not path.is_relative_to(domain.resolve()):raise ValueError("Host image outside domain")
                if str(path)not in image_cache:
                    with Image.open(path)as im:
                        image_cache[str(path)]=(hashlib.sha256(im.mode.encode()+str(im.size).encode()+im.tobytes()).hexdigest(),list(im.size),im.mode)
                if image_cache[str(path)]!=(ref["pixel_sha256"],ref["size"],ref["mode"]):
                    errors.append("host_image_hash_or_grid_mismatch")
        elif event["kind"]=="primitive_action":streak=0
    if pending:errors.append("unfinished_model_input")
    errors.extend(_native_result_audit(entry)["errors"])
    config=domain/"worker/effective-config.yaml"
    if entry["result"]is not None and (not config.is_file()or hashlib.sha256(config.read_bytes()).hexdigest()!=entry["result"].get("effective_config_sha256")):
        errors.append("effective_config_hash_mismatch")
    costs=Path(entry["path"]).parent/"model_costs.jsonl"
    cost_rows=rows(costs)if costs.exists()else[]
    terminal=trace[-1]if trace else{}
    if [x.get("call_id")for x in cost_rows]!=[x["call_id"]for x in trace if x["kind"]=="model_call"]:
        errors.append("model_cost_coverage_mismatch")
    if any(not isinstance(x.get("seconds"),(int,float))or not math.isfinite(x["seconds"])or x["seconds"]<0 for x in cost_rows):
        errors.append("invalid_model_cost")
    if not(Path(entry["path"]).parent/"host_cost.json").exists():errors.append("missing_host_cost")
    host_cost=load(Path(entry["path"]).parent/"host_cost.json")if(Path(entry["path"]).parent/"host_cost.json").exists()else None
    resource_path=domain/"resource_samples.jsonl"
    resources=rows(resource_path)if resource_path.exists()else[]
    start=(host_cost or {}).get("episode_started_monotonic");end=(host_cost or {}).get("episode_ended_monotonic")
    sampled=[x["used_mib"]for x in resources if "used_mib"in x and start is not None and end is not None and start<=x["monotonic"]<=end]
    return dict(status="VERIFIED"if not errors else"FAIL",errors=errors,token_text_verified=tokenizer is not None,
        sampled_total_gpu_peak_mib=max(sampled)if sampled else None,gpu_samples=len(sampled),
        reason_count=reasons,reason_max_streak=max_streak,parse_invalid=fallbacks,default_forward=fallbacks,
        forced_stop_count=sum(x["kind"]=="primitive_action"and x["action"]==0 and x.get("stop_source")!="model"for x in trace),
        model_calls=dict(main=sum(x["kind"]=="model_call"for x in trace),reader=0,grounder=0),
        tokens=dict(input=input_tokens,output=output_tokens),steps=terminal.get("steps"),
        path_length=terminal.get("native_metrics",{}).get("path_length"),
        collisions=sum(bool(x.get("after_evaluator_only",{}).get("collided"))for x in trace if x["kind"]=="primitive_action"),
        model_boundary_latency_seconds=_quantiles([x["seconds"]for x in cost_rows]),
        host_cost=host_cost)

def _audit_memory(domain,candidate):
    """Verify actual committed files and their000packet provenance,not summary labels."""
    from graphAdapter.map_memory.storage.store import load_episode,read_manifest,_verify_ref
    from graphAdapter.observation_packet import thaw
    from graphAdapter.observation_pose.alignment import array_hash
    packets=rows(domain/"worker/observation_pose/observation-packets.jsonl")if(domain/"worker/observation_pose/observation-packets.jsonl").exists()else[]
    grouped={}
    for p in packets:
        group=grouped.setdefault(p["episode_uid"],{})
        if p["frame_uid"]in group:raise ValueError("Duplicate000sourcepacket")
        group[p["frame_uid"]]=p
    flow_path=domain/"worker/observation_pose/flow_trace.jsonl"
    flow=rows(flow_path)if flow_path.exists()else[]
    raw={e["frame_uid"]:e for e in flow if e["kind"]=="raw_archive"}
    alignment={e["frame_uid"]:e for e in flow if e["kind"]=="alignment"}
    from .publications import index_publications
    published,publication_revisions=index_publications(flow,{p["frame_uid"]:p for p in packets})
    native_uids={x["scope"]["episode_uid"]for x in candidate.values()}
    summaries=[];errors=[]
    if [e["event_seq"]for e in flow]!=list(range(1,len(flow)+1)):errors.append("nonsequential_flow_trace")
    # index_publications rejects duplicate endpoint or snapshot identities.
    packet_events={e["frame_uid"]:e for e in flow if e["kind"]=="observation_packet"}
    for p in packets:
        event=packet_events.get(p["frame_uid"])
        if event is None or event["packet"]!=p or event["event_seq"]!=p["event_seq"]:errors.append("source_packet_commit_log_mismatch")
    for path in (domain/"worker/map_memory/episodes").glob("*/*/attempt_000/episode_summary.json"):
        summary=load(path);episode=summary["episode_uid"];root=path.parent
        if episode not in native_uids or(root/"FAILED.json").exists():errors.append("unexpected_or_failed_memory_episode:"+episode)
        reader=load_episode(root)
        try:
            verified=reader.verify(hashes=True,references=True)
            if verified["snapshot_id"]!=summary["snapshot_id"]:errors.append("memory_summary_current_mismatch")
            graph=reader._graph
            history={};verified_history_unique_files=0
            for revision in reader.iter_verified_history():
                sid=revision["snapshot_id"];history[sid]=revision
                manifest=revision;historical=revision["graph"]
                verified_history_unique_files=revision["verified_unique_files"]
                if len(historical["views"])!=manifest["cutoff"]["capture_seq"]:errors.append("historical_frame_coverage_gap")
                for old_view in historical["views"].values():
                    if old_view["capture_seq"]>manifest["cutoff"]["capture_seq"]or old_view["source_event_seq"]>manifest["cutoff"]["event_seq"]:
                        errors.append("future_historical_view")
                    if old_view["position_G"]is not None and old_view["pose_map_version"]!=manifest["versions"]["pose_map_version"]:
                        errors.append("mixed_historical_pose_revision")
            source=grouped.get(episode,{})
            if set(graph["views"])!=set(source):errors.append("memory_source_frame_membership_mismatch")
            eligible=geometry=perception=pose_valid=0
            for uid,view in graph["views"].items():
                record=reader.get_view(uid,include_images=True,include_depth=True)
                capture=thaw(record["capture"]);p=source.get(uid)
                if p is None:errors.append("unexpected_memory_frame:"+uid);continue
                if any(capture.get(k)!=v for k,v in p.items()):errors.append("memory_capture_packet_mismatch:"+uid)
                event=raw.get(uid,{})
                if (array_hash(record["raw_rgb"])if record["raw_rgb"]is not None else None)!=event.get("rgb_hash"):errors.append("memory_raw_rgb_hash_mismatch:"+uid)
                depths=record.get("depth",{})
                if "raw_depth"in depths and array_hash(depths["raw_depth"])!=event.get("depth_hash"):errors.append("memory_raw_depth_hash_mismatch:"+uid)
                if "aligned_depth"in depths and array_hash(depths["aligned_depth"])!=alignment.get(uid,{}).get("aligned_depth_hash"):
                    errors.append("memory_alignment_hash_mismatch:"+uid)
                pub=published.get(uid)
                if pub is None or pub["source_packet_event_seq"]!=p["event_seq"]or pub["cutoff_event_seq"]!=p["event_seq"]:
                    errors.append("memory_publication_source_missing_or_future:"+uid)
                else:
                    manifest=history.get(pub["snapshot_id"])
                    if manifest is None:errors.append("published_orphan_snapshot");continue
                    if manifest["cutoff"]!={"capture_seq":p["capture_seq"],"event_seq":p["event_seq"]}or manifest["versions"]!=pub["versions"]:
                        errors.append("memory_publication_cutoff_or_version_mismatch:"+uid)
                spatial=view["position_G"]is not None
                if spatial and view["pose_map_version"]!=graph["versions"]["pose_map_version"]:errors.append("mixed_pose_revision")
                pose_valid+=int(spatial)
                sensor=p["capture_seq"]>1 and record["raw_rgb"]is not None and "aligned_depth"in depths and p["K"]is not None and p["T_base_camera"]is not None
                eligible+=int(sensor);geometry+=int(sensor and view["geometry_fused"])
                perception+=int(record["raw_rgb"]is not None and view["perception_complete"])
            if (summary["frames"],summary["eligible_endpoints"],summary["geometry_fused"],summary["perception_complete"])!=(len(graph["views"]),eligible,geometry,perception):
                errors.append("memory_summary_counts_mismatch")
            episode_publications={sid:e for sid,e in publication_revisions.items() if e["frame_uid"] in source}
            for sid,event in episode_publications.items():
                manifest=history.get(sid)
                packet=source[event["frame_uid"]]
                if (manifest is None or manifest["cutoff"]!={"capture_seq":packet["capture_seq"],"event_seq":packet["event_seq"]}
                        or manifest["versions"]!=event["versions"]):
                    errors.append("correction_publication_cutoff_or_version_mismatch")
            if set(episode_publications)!=set(history):
                errors.append("publication_history_membership_mismatch")
            timing=rows(root/"execution.jsonl")if(root/"execution.jsonl").exists()else[]
            summary=dict(summary,pose_valid_count=pose_valid,reference_integrity=verified,
                verified_history_revisions=len(history),verified_unique_history_files=verified_history_unique_files,
                memory_prepare_latency_seconds=_quantiles([x["seconds"]for x in timing if x["kind"]=="memory_prepare"]),
                memory_commit_latency_seconds=_quantiles([x["seconds"]for x in timing if x["kind"]=="memory_commit"]))
            summaries.append(summary)
        finally:reader.close()
    if len(summaries)!=len(native_uids)or {x["episode_uid"]for x in summaries}!=native_uids:errors.append("missing_or_duplicate_memory_episode")
    return summaries,errors


def collect_shards(roots,out):
    """Metadata-only collection;keep raw traces/images/maps in their original attempts."""
    import shutil
    roots=[Path(x).resolve()for x in roots];out=Path(out).absolute()
    identities=[load(root/"run_identity.json")for root in roots]
    first=identities[0];count=first["shard"]["worker_count"]
    if first.get("partition")!="A"or first.get("stage")!="001":raise ValueError("Only stage001A collection is authorized")
    if type(count)is not int or count<1:raise ValueError("Invalid shard count")
    if len(roots)!=count or {x["shard"]["worker_index"]for x in identities}!=set(range(count)):
        raise ValueError("Missing/duplicate worker shards")
    for item in identities:
        for key in ("source_sha256","profile_sha256","registry_sha256","partition","smoke","hook_mode","method","sidecar_feature"):
            if item[key]!=first[key]:raise ValueError("Shard identity mismatch: "+key)
        if item["shard"]["worker_count"]!=count:raise ValueError("Shard worker count mismatch")
    for item in identities:
        if any(item.get(key)!=first.get(key)for key in ("selection_kind","selection_manifest_sha256")):
            raise ValueError("Shard random selection identity mismatch")
    out.mkdir(parents=True,exist_ok=False)
    domain_rows={}
    for dataset in ("r2r","rxr_us"):
        expected=16 if first["smoke"]else {"r2r":612,"rxr_us":407}[dataset]
        joined=[]
        for root,identity in zip(roots,identities):
            rows_=load(root/dataset/"registered_identities.json")
            worker=identity["shard"]["worker_index"]
            if any(x.get("selection_index",x["sealed_index"])%count!=worker for x in rows_):raise ValueError("Worker contains another sealed-index shard")
            joined.extend(rows_)
        joined.sort(key=lambda x:x.get("selection_index",x["sealed_index"]))
        if [x.get("selection_index",x["sealed_index"])for x in joined]!=list(range(expected)):
            raise ValueError("Shard union has missing/duplicate sealed members")
        if len({tuple(x["identity"])for x in joined})!=expected:raise ValueError("Shard identity overlap")
        if first.get("selection_kind")=="random32":
            from .selector import validate_registered_selection
            profile=load(roots[0]/"effective_config.json")
            selection=profile.get("random_validation",{})
            if selection.get("sha256")!=first.get("selection_manifest_sha256"):
                raise ValueError("Random profile/run selection mismatch")
            validate_registered_selection(joined,dataset,selection["file"],selection["sha256"])
        domain_rows[dataset]=joined
    manifest=dict(first,shard=dict(worker_count=count,collection=True),run_uid="collection-"+hashlib.sha256(
        json.dumps([x["run_uid"]for x in identities],sort_keys=True).encode()).hexdigest()[:24])
    (out/"run_identity.json").write_text(json.dumps(manifest,indent=2))
    entries=[]
    for root,item in zip(roots,identities):
        if not root.is_relative_to(out.parent.resolve()):raise ValueError("Shard collection escapes its run family")
        entries.append(dict(path=str(root),worker_index=item["shard"]["worker_index"],
            identity_sha256=hashlib.sha256((root/"run_identity.json").read_bytes()).hexdigest()))
    (out/"shards.json").write_text(json.dumps(dict(shards=entries),indent=2))
    for name in ("effective_config.json","acceptance_policy.json"):
        source=roots[0]/name;data=source.read_bytes()
        if any((root/name).read_bytes()!=data for root in roots):raise ValueError("Shard config/policy mismatch")
        (out/name).write_bytes(data)
    for dataset,joined in domain_rows.items():
        (out/dataset).mkdir()
        (out/dataset/"registered_identities.json").write_text(json.dumps(joined,indent=2))
    return dict(shards=count,members={k:len(v)for k,v in domain_rows.items()},raw_evidence_copied=False)

def domain_sources(root,dataset):
    root=Path(root);index=root/"shards.json"
    if not index.exists():return [root/dataset]
    entries=load(index)["shards"];sources=[];identity=load(root/"run_identity.json")
    for item in entries:
        shard=Path(item["path"]).resolve()
        if not shard.is_relative_to(root.parent.resolve()):raise ValueError("Shard source escaped run family")
        if hashlib.sha256((shard/"run_identity.json").read_bytes()).hexdigest()!=item["identity_sha256"]:
            raise ValueError("Shard run identity changed")
        actual=load(shard/"run_identity.json")
        for key in ("source_sha256","profile_sha256","registry_sha256","partition","smoke","hook_mode","method","sidecar_feature"):
            if actual[key]!=identity[key]:raise ValueError("Collected shard identity drift")
        if any(actual.get(key)!=identity.get(key)for key in ("selection_kind","selection_manifest_sha256")):
            raise ValueError("Collected shard selection identity drift")
        sources.append(shard/dataset)
    return sources

def variant_index(root,dataset):
    combined={}
    for domain in domain_sources(root,dataset):
        for member,entry in trace_index(domain).items():
            if member in combined:raise ValueError("Duplicate identity across raw shards")
            combined[member]=dict(entry,domain=str(domain))
    return combined


def paired_protocol(run,control,dataset):
    import yaml
    left,right=domain_sources(run,dataset),domain_sources(control,dataset)
    by_worker=lambda domains:{load(d.parent/"run_identity.json").get("shard",{}).get("worker_index",0):d for d in domains}
    a,b=by_worker(left),by_worker(right)
    if set(a)!=set(b):raise ValueError("Paired worker assignment mismatch")
    result=[]
    def config(domain):
        value=(domain/"worker/effective-config.yaml").read_text()
        return value.replace(str(domain.resolve())+"/","$DOMAIN/")
    for worker in a:
        lc,rc=a[worker]/"worker/effective-config.yaml",b[worker]/"worker/effective-config.yaml"
        if not lc.exists()or not rc.exists():result.append(dict(worker=worker,status="MISSING_CONFIG"));continue
        if config(a[worker])!=config(b[worker]):raise ValueError("Paired effective config/protocol mismatch")
        lm,rm=load(a[worker].parent/"run_identity.json"),load(b[worker].parent/"run_identity.json")
        if lm.get("resource_budget")!=rm.get("resource_budget"):raise ValueError("Paired CPU/GPU assignment differs")
        lp,rp=a[worker]/"worker/model-receipt.json",b[worker]/"worker/model-receipt.json"
        if not lp.exists()or not rp.exists():result.append(dict(worker=worker,status="MISSING_MODEL_RECEIPT"));continue
        lr,rr=load(lp),load(rp)
        required=("checkpoint","python","prefix","torch","transformers","model_class","mode_token_ids",
                  "tokenizer_size","dtype","num_video_frames","source_sha256")
        if any(k not in value or value[k]is None or value[k]==""for value in (lr,rr)for k in required):
            result.append(dict(worker=worker,status="INCOMPLETE_MODEL_RECEIPT"));continue
        keys=("checkpoint","python","prefix","torch","transformers","model_class","mode_token_ids",
              "tokenizer_size","tokenizer_source","llm_source","dtype","num_video_frames","source_sha256")
        if any(lr.get(k)!=rr.get(k)for k in keys):raise ValueError("Paired actual model/tokenizer receipt differs")
        result.append(dict(worker=worker,status="VERIFIED"))
    return result

def _engineering_acceptance(hard_errors,domains):
    return not hard_errors and all(
        domain["all_pairs_equal"]and domain["memory"]["availability_gate"]
        and all(domain[layer][variant]==domain["fixed_denominator"]
            for layer in ("native_execution_coverage","native_evidence_coverage")
            for variant in ("shadow","control"))
        for domain in domains)

def report(run,control,*,out=None,paired=True):
    run,control=Path(run),Path(control)
    out=Path(out)if out else run/"paired_report"
    out.mkdir(parents=True,exist_ok=False)
    left_identity,right_identity=load(run/"run_identity.json"),load(control/"run_identity.json")
    for key in ("source_sha256","profile_sha256","registry_sha256"):
        if left_identity[key]!=right_identity[key]:raise ValueError("Common-host identity mismatch: "+key)
    if left_identity.get("partition")!="A"or right_identity.get("partition")!="A":
        raise ValueError("This stage reads A results only")
    for identity,hook,feature in ((left_identity,"on","geometry_shadow"),(right_identity,"off","disabled")):
        if identity.get("stage")=="001"and(identity.get("method")!="baseline"or identity.get("hook_mode")!=hook
                or identity.get("sidecar_feature")!=feature):
            raise ValueError("Main-policy/sidecar pair classification mismatch")
    if any(left_identity.get(key)!=right_identity.get(key)for key in ("selection_kind","selection_manifest_sha256")):
        raise ValueError("Paired random selection identity mismatch")
    policy=None
    if (run/"acceptance_policy.json").exists():policy=load(run/"acceptance_policy.json")
    summaries=[];pairs=[];failures=[];episode_audits=[];hard_errors=[];image_cache={}
    for root,identity in ((run,left_identity),(control,right_identity)):
        config=root/"effective_config.json"
        if not config.exists():hard_errors.append("missing_effective_profile:"+str(root))
        elif hashlib.sha256(config.read_bytes()).hexdigest()!=identity["profile_sha256"]:
            # JSON serialization may differ;runner preserves the source bytes hash
            # separately and source freeze includes the actual profile.
            original=next((Path(x["path"])for x in identity.get("frozen_files",[])
                if Path(x["path"]).name=="000_geometry_shadow.json"),None)
            if original is None or load(original)!=load(config):hard_errors.append("effective_profile_drift")
        if config.exists():
            from .registry_binding import verify_frozen_json_copy,AuditError
            try:
                frozen_policy=load(config)
                if not frozen_policy.get("acceptance_policy")or not frozen_policy.get("acceptance_policy_sha256"):
                    raise AuditError("missing_frozen_policy_binding")
                verify_frozen_json_copy(Path(frozen_policy["acceptance_policy"]),
                    root/"acceptance_policy.json",frozen_policy["acceptance_policy_sha256"])
            except (AuditError,FileNotFoundError)as error:
                hard_errors.append("acceptance_policy_drift:"+str(error))
    tokenizer=None
    model=Path(__file__).resolve().parents[3]/"models/awarevln/llm"
    if model.is_dir()and any(list((domain/"worker/episodes").glob("*/trace.jsonl"))
            for dataset in ("r2r","rxr_us")for domain in domain_sources(run,dataset)):
        from transformers import AutoTokenizer
        tokenizer=AutoTokenizer.from_pretrained(str(model),local_files_only=True)
    frozen=left_identity.get("frozen_files",[])
    if not frozen:hard_errors.append("missing_frozen_source_identity")
    for item in frozen:
        path=Path(item["path"])
        if not path.is_file()or hashlib.sha256(path.read_bytes()).hexdigest()!=item["sha256"]:
            hard_errors.append("source_drift:"+str(path))
    for dataset,total in (("r2r",612),("rxr_us",407)):
        candidate,baseline=variant_index(run,dataset),variant_index(control,dataset)
        protocol=paired_protocol(run,control,dataset)
        if any(x["status"]!="VERIFIED"for x in protocol):hard_errors.append(dataset+":missing_model_or_protocol_evidence")
        expected_rows=load(run/dataset/"registered_identities.json")
        if left_identity.get("selection_kind")=="random32":
            from .selector import validate_registered_selection
            selection=load(run/"effective_config.json")["random_validation"]
            if selection["sha256"]!=left_identity.get("selection_manifest_sha256"):
                raise ValueError("Random profile/run selection mismatch")
            validate_registered_selection(expected_rows,dataset,selection["file"],selection["sha256"])
        expected=[tuple(x["identity"])for x in expected_rows]
        control_expected=[tuple(x["identity"])for x in load(control/dataset/"registered_identities.json")]
        if control_expected!=expected:raise ValueError("Control/candidate registered member order differs")
        if not set(candidate)<=set(expected)or not set(baseline)<=set(expected):raise ValueError("Unexpected executed member")
        for variant,root in (("shadow",run),("control",control)):
            for domain in domain_sources(root,dataset):
                execution=domain/"execution_result.json"
                if not execution.exists()or load(execution).get("exit_code")!=0:
                    hard_errors.append(dataset+":"+variant+":domain_execution_failed:"+str(domain))
        if len(expected)!=len(set(expected)):raise ValueError("Duplicate registered members")
        denominator=total if not left_identity["smoke"]else len(expected)
        if not left_identity["smoke"]and len(expected)!=total:raise ValueError("Fixed fullA coverage mismatch")
        success={"shadow":0,"control":0};coverage={"shadow":0,"control":0};metric_values={m:{"shadow":[],"control":[]}for m in ("sr","spl","ndtw","ne","sdtw")}
        transitions=dict(win=0,loss=0,tie_success=0,tie_failure=0);deltas=[];scenes=[]
        for member in expected:
            item=candidate.get(member);base=baseline.get(member)
            values=[]
            for label,entry in (("shadow",item),("control",base)):
                valid=_native_complete(entry)
                sr=float(entry["result"]["metrics"]["sr"])if valid else 0.
                success[label]+=int(sr>0);coverage[label]+=int(valid);values.append(int(sr>0))
                for metric in metric_values:
                    if valid and _metric_availability(metric,entry["result"]["metrics"].get(metric))=="finite":
                        metric_values[metric][label].append(float(entry["result"]["metrics"][metric]))
                if not valid:failures.append(dict(dataset=dataset,identity=member,variant=label,status="missing_or_exception",success=0))
            for label,entry,root in (("shadow",item,run),("control",base,control)):
                audit=_audit_host(entry,Path(entry["domain"])if entry else root/dataset,image_cache,tokenizer=tokenizer)
                if audit["status"]!="VERIFIED"or not audit.get("token_text_verified"):hard_errors.append(dataset+":"+label+":"+str(member)+":host_evidence")
                result=entry["result"]if entry else None
                episode_audits.append(dict(registered_identity_hash=hashlib.sha256(json.dumps(member,separators=(",",":")).encode()).hexdigest(),
                    identity=member,dataset=dataset,partition="A",variant=label,attempt=(entry["scope"].get("attempt_id")if entry else None),
                    status=audit["status"],success=values[0 if label=="shadow"else 1],
                    official_metrics=result.get("metrics")if result else None,native_result_validation=_native_result_audit(entry),behavior_cost=audit,
                    selected_refs=0,materialized_refs=0,host_used_memory_refs=0,scope="001shadow;memorynotinjected"))
            a,b=values;deltas.append(a-b);scenes.append(member[1])
            transitions["win"if a>b else"loss"if a<b else"tie_success"if a else"tie_failure"]+=1
            diff=first_difference(item["trace"],base["trace"])if item is not None and base is not None else dict(kind="missing_trace")
            pairs.append(dict(dataset=dataset,identity=member,shadow_trace=item["path"]if item else None,
                control_trace=base["path"]if base else None,shadow_success=a,control_success=b,
                earliest_difference=diff,inputs_outputs_actions_termination_equal=diff is None))
        rng=np.random.default_rng(77);delta=np.asarray(deltas,float)
        bootstrap=np.asarray([rng.choice(delta,size=len(delta),replace=True).mean()for _ in range(1000)])if len(delta)else np.asarray([np.nan])
        groups={scene:np.flatnonzero(np.asarray(scenes)==scene)for scene in sorted(set(scenes))}
        keys=list(groups);cluster=[]
        if keys:
            for _ in range(1000):
                sample=rng.choice(keys,size=len(keys),replace=True)
                cluster.append(np.concatenate([delta[groups[key]]for key in sample]).mean())
        memory=[];memory_errors=[]
        for domain in domain_sources(run,dataset):
            scoped={k:v for k,v in candidate.items()if Path(v["domain"])==domain}
            values,errors_=_audit_memory(domain,scoped);memory.extend(values);memory_errors.extend(errors_)
        hard_errors.extend(dataset+":"+e for e in memory_errors)
        by_uid={x["episode_uid"]:x for x in memory}
        for audit in episode_audits:
            if audit["dataset"]!=dataset:continue
            if audit["variant"]=="shadow":
                entry=candidate.get(tuple(audit["identity"]));uid=entry["scope"]["episode_uid"]if entry else None
                data=by_uid.get(uid)
                audit.update(episode_uid=uid,memory_status="VERIFIED"if data else"MISSING",
                    archive_frame_count=data["frames"]if data else 0,
                    pose_valid_count=data.get("pose_valid_count")if data else 0,
                    fused_count=data["geometry_fused"]if data else 0,
                    perception_complete=data["perception_complete"]if data else 0,
                    snapshot_versions={"pose_map_version":data["pose_map_version"]}if data else None,
                    memory_evidence=data)
                if data is None:audit["status"]="INCOMPLETE_MEMORY"
            else:audit.update(memory_status="DISABLED_CONTROL",archive_frame_count=0,pose_valid_count=0,fused_count=0,
                              perception_complete=0,snapshot_versions=None,memory_evidence=None)
        total_frames=sum(x["frames"]for x in memory);eligible=sum(x["eligible_endpoints"]for x in memory)
        geometry=sum(x["geometry_fused"]for x in memory);perception=sum(x["perception_complete"]for x in memory)
        semantic=sum(x["semantic_contribution_frames"]for x in memory)
        rates=dict(geometry=geometry/eligible if eligible else 0,perception=perception/total_frames if total_frames else 0,
                   semantic_world_contribution=semantic/eligible if eligible else 0)
        receipts={}
        for variant,root in (("shadow",run),("control",control)):
            receipts[variant]=[load(domain/"worker/hook-load.json")for domain in domain_sources(root,dataset)]
        genuine_off=all(off["completed"]and not off["hook_enabled"]and not off["broker_supplied"]
            and not off.get("memory_broker_supplied",False)and not off.get("memory_worker_started",False)
            and not off["loaded_graph_modules"]for off in receipts["control"])
        if not genuine_off:raise ValueError("Control is not genuinely hook/memory off")
        for receipt in receipts["shadow"]:
            if not(receipt.get("completed")and receipt.get("hook_enabled")and receipt.get("memory_worker_started")):
                hard_errors.append(dataset+":missing_shadow_hook_or_memory_receipt")
        if policy is not None:
            usable=(rates["geometry"]>=policy["geometry_completion_min"]
               and rates["perception"]>=policy["perception_completion_min"]
               and rates["semantic_world_contribution"]>=policy["semantic_world_contribution_ratio_min"])
        else:usable=False
        summaries.append(dict(dataset=dataset,fixed_denominator=denominator,paired_protocol=protocol,native_execution_coverage={label:sum(_native_result_audit(entry)["execution_complete"]for entry in index.values())for label,index in (("shadow",candidate),("control",baseline))},
            native_evidence_coverage=coverage,
            successes=success,SR={k:v/denominator for k,v in success.items()},
            delta_SR_count=success["shadow"]-success["control"],transitions=transitions,
            paired_episode_bootstrap_delta_SR_95CI=np.quantile(bootstrap,[.025,.975]).tolist(),
            paired_scene_cluster_delta_SR_95CI=np.quantile(cluster,[.025,.975]).tolist()if cluster else None,
            native_metrics={m:{label:dict(mean=statistics.mean(v)if v else None,coverage=len(v),fixed_N=denominator)
              for label,v in by.items()}for m,by in metric_values.items()},
            memory=dict(episodes=len(memory),frames=total_frames,eligible=eligible,geometry_fused=geometry,
                perception_complete=perception,semantic_frames=semantic,rates=rates,availability_gate=usable),
            genuine_off=True,all_pairs_equal=all(x["earliest_difference"]is None for x in pairs if x["dataset"]==dataset)))
    engineering=_engineering_acceptance(hard_errors,summaries)
    profile=load(run/"effective_config.json")if(run/"effective_config.json").exists()else{}
    headroom=profile.get("full_A_storage_headroom",1.5)
    domain_costs=[];forecast=0.;forecast_by_variant={"shadow":0.,"control":0.}
    for summary in summaries:
        dataset=summary["dataset"];n=summary["fixed_denominator"]
        by_variant={}
        for label,root in (("shadow",run),("control",control)):
            total_bytes=sum(p.stat().st_size for domain in domain_sources(root,dataset)for p in domain.rglob("*")if p.is_file())
            by_variant[label]=total_bytes
            if n:
                projected=total_bytes/n*{"r2r":612,"rxr_us":407}[dataset]
                forecast+=projected;forecast_by_variant[label]+=projected
        domain_costs.append(dict(dataset=dataset,episodes=n,actual_total_bytes=by_variant))
    import shutil
    free=shutil.disk_usage(run).free
    reserve=profile.get("map_memory",{}).get("resources",{}).get("minimum_filesystem_free_bytes",512*1024**3)
    resource_forecast=dict(scope="FullA paired-run linear disk forecast from actual smoke;not a worst-case guarantee",
        headroom_multiplier=headroom,estimated_additional_bytes=int(forecast*headroom),
        estimated_additional_by_variant_bytes={k:int(v*headroom)for k,v in forecast_by_variant.items()},
        measured_free_bytes=free,reserve_bytes=reserve,
        status="ADMITTED"if free>=forecast*headroom+reserve else"INSUFFICIENT_SPACE",
        actual_domain_costs=domain_costs)
    result=dict(report_schema_version=2,status="PASS_ENGINEERING"if engineering else"FAIL_OR_INCOMPLETE_ENGINEERING",
        full_A_resource_forecast=resource_forecast,
        scope="A-only shared-host geometry shadow;no memory decisions/no expected SR gain",
        source_sha256=left_identity["source_sha256"],profile_sha256=left_identity["profile_sha256"],
        registry_sha256=left_identity["registry_sha256"],domains=summaries,pairs=len(pairs),
        failed_or_missing_count=len(failures),hard_contract_errors=hard_errors,effect_status="NOT_AN_EFFECT_CLAIM",
        fixed_failure_rule="Missing/exception countsSR0;other metricsNA withcoverage;no failed denominator removal")
    for name,data in (("paired_report.json",result),("paired_episodes.json",pairs),("failure_inventory.json",failures),("per_episode_audit.json",episode_audits),
                      ("memory_cost_and_behavior.json",dict(episodes=episode_audits,memory=[x["memory"]for x in summaries],
                         note="Null means unmeasured;memorymodelsareadditionalRGB-D-sidecompute;nomemoryinputin001"))):
        (out/name).write_text(json.dumps(data,indent=2))
    with(out/"per_episode.jsonl").open("x")as stream:
        for item in episode_audits:stream.write(json.dumps(item)+"\n")
    return result
