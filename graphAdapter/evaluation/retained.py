"""Retained episode audit/report after raw owned work has been reclaimed."""
from pathlib import Path
import json,math,statistics,hashlib
from .report import _native_result_audit,_parser_functions,paired_protocol
from graphAdapter.map_memory.storage.lifecycle import (
    EpisodeLifecycle,LifecycleError,audit_pair,json_rows,sha,atomic_json,canonical)

def audit_memory_materials(root,packets_path,flow_path,out,*,required_sampling=False,frozen_source_sha256=None):
    """Verify current plus immutable history before ordinary source deletion."""
    from graphAdapter.map_memory.storage.store import load_episode
    from graphAdapter.observation_pose.alignment import array_hash
    from graphAdapter.observation_packet import thaw
    from graphAdapter.map_memory.service import GraphMapCorrectionConsumer
    from graphAdapter.observation_pose.production import audit_samples
    packets={}
    for packet in json_rows(packets_path):
        uid=packet['frame_uid']
        if uid in packets:
            raise LifecycleError('Duplicate retained observation packet')
        packets[uid]=packet
    from .publications import index_publications
    flow=list(json_rows(flow_path))
    try:published,publication_revisions=index_publications(flow,packets)
    except ValueError as error:raise LifecycleError(str(error)) from error
    raw={};alignment={}
    for row in flow:
        uid=row.get("frame_uid")
        if row["kind"]=="raw_archive":raw[uid]=row
        elif row["kind"]=="alignment":alignment[uid]=row

    reader=load_episode(root,cache_bytes=16*1024**2)
    revisions=0;views=0;errors=[]
    try:
        verified=reader.verify(hashes=True,references=True)
        graph=reader._graph
        if set(graph["views"])!=set(packets):raise LifecycleError("Source/map membership differs")
        archive_only=all(v.get("execution_mode")=="archive_only"for v in graph["views"].values())
        legacy_sources={'f137ea88e19336ea3822aeeb9da85c6f5227cbdbe223fd77df88bce99f6ffbc3',
            'b08e5198c20aa7cd37503d086405f393154d4838366c745e7809d3d75451d39c',
            '970024b65946ad0286d6038177c16b212920784543abe934e18181bea57634e7'}
        if graph.get('pose_provider')=='simulator_ground_truth':
            if required_sampling:raise LifecycleError('Simulator pose cannot satisfy native release4 sampling acceptance')
            from graphAdapter.observation_pose.provider_contract import audit_simulator_endpoints
            sampling_audit=audit_simulator_endpoints(list(packets.values()),flow)
        else:
            sampling_audit=audit_samples(packets_path,flow_path,required=required_sampling,
                allow_legacy=archive_only or frozen_source_sha256 in legacy_sources)
        consumer=GraphMapCorrectionConsumer(reader.identity["episode_uid"])
        for uid,view in graph["views"].items():
            record=reader.get_view(uid,include_images=True,include_depth=True)
            capture=thaw(record["capture"]);packet=packets[uid]
            if any(capture.get(k)!=v for k,v in packet.items()):raise LifecycleError("Consumed map packet differs")
            if array_hash(record["raw_rgb"])!=raw[uid]["rgb_hash"]:raise LifecycleError("Raw RGB consumption differs")
            depths=record.get("depth",{})
            if "raw_depth"in depths and array_hash(depths["raw_depth"])!=raw[uid]["depth_hash"]:
                raise LifecycleError("Raw depth consumption differs")
            if "aligned_depth"in depths and array_hash(depths["aligned_depth"])!=alignment[uid]["aligned_depth_hash"]:
                raise LifecycleError("Aligned depth consumption differs")
            if "valid_mask"in depths and alignment[uid].get("valid_mask_typed_hash")and array_hash(depths["valid_mask"])!=alignment[uid]["valid_mask_typed_hash"]:
                raise LifecycleError("Valid mask consumption differs")
            pub=published.get(uid)
            if not pub or pub["source_packet_event_seq"]!=packet["event_seq"]:raise LifecycleError("Published source identity differs")
            if not archive_only:
                resolved=consumer.resolve(capture,graph["pose_bindings"])
                if resolved is None:
                    if view["position_G"]is not None:raise LifecycleError("Unverified geometry invented")
                elif canonical(resolved["T_G_cv"])!=canonical(view["T_G_cv"]):
                    import numpy as np
                    if not np.allclose(resolved["T_G_cv"],view["T_G_cv"],atol=1e-10,rtol=1e-10):
                        raise LifecycleError("Per-keyframe geometry differs")
            views+=1
        with Path(out).open("x")as stream:
            # Independent raw-page audit budget; image/metadata caches remain at 16 MiB.
            for revision in reader.iter_verified_history(page_cache_bytes=64*1024**2):
                historical=revision["graph"];cutoff=revision["cutoff"]
                event=publication_revisions.get(revision["snapshot_id"])
                if event is None:raise LifecycleError("Committed map has no publication event")
                packet=packets[event["frame_uid"]]
                if cutoff!={"capture_seq":packet["capture_seq"],"event_seq":packet["event_seq"]} or revision["versions"]!=event["versions"]:
                    raise LifecycleError("Correction publication identity differs from committed state")
                if len(historical["views"])!=cutoff["capture_seq"]:raise LifecycleError("Historical frame coverage")
                for view in historical["views"].values():
                    if view["capture_seq"]>cutoff["capture_seq"]or view.get("source_event_seq",0)>cutoff["event_seq"]:
                        raise LifecycleError("Future material in published snapshot")
                    if view["position_G"]is not None and view["pose_map_version"]!=revision["versions"]["pose_map_version"]:
                        raise LifecycleError("Mixed historical pose revision")
                stream.write(json.dumps(dict(snapshot_id=revision["snapshot_id"],versions=revision["versions"],
                    cutoff=cutoff,graph_sha256=hashlib.sha256(canonical(historical)).hexdigest()))+"\n")
                revisions+=1
        if revisions!=len(publication_revisions):raise LifecycleError("Uncommitted publication event")
    finally:reader.close()
    return dict(status="VERIFIED",frames=views,history_revisions=revisions,current=verified,pose_sampling=sampling_audit,
                execution_mode="archive_only"if archive_only else"live")

def report_retained(root,out):
    root,out=Path(root),Path(out);plan=json.loads((root/"retention_plan.json").read_bytes())
    require_release4=plan.get('production_schema')=='release4_endpoint_v1'
    digest=sha(root/"retention_plan.json");out.mkdir(parents=True,exist_ok=False)
    evaluations=list((root/"control/evaluations").glob("*.json"))
    manifests=[json.loads(p.read_bytes())for p in evaluations]
    hard=[];pairs=[];rows=[];domains=[]
    # Only actual evaluator manifests can qualify navigation.
    if not manifests:hard.append("no_actual_evaluator_manifests")
    else:
        identities=[row['manifest']for row in manifests]
        for key in('source_sha256','profile_sha256','registry_sha256'):
            if len({row.get(key)for row in identities})!=1:hard.append('evaluator_identity_mismatch:'+key)
        grouped={}
        for row in manifests:
            key=(row['manifest']['shard']['worker_index'],row['manifest'].get('execution_segment'))
            target=grouped.setdefault(key,{})
            if row['side']in target:raise LifecycleError('Duplicate evaluator segment/side')
            target[row['side']]=row
        for worker,pair in grouped.items():
            if set(pair)!={'shadow','control'}:hard.append('missing_worker_pair:'+str(worker));continue
            if pair['shadow']['manifest'].get('execution_ranges')!=pair['control']['manifest'].get('execution_ranges'):
                raise LifecycleError('Paired execution segment ranges differ')
            for dataset in sorted({entry['member'][0]for entry in plan['entries']}):
                ranges=pair['shadow']['manifest'].get('execution_ranges')or{}
                if ranges.get(dataset)==[0,0]:continue
                protocol=paired_protocol(pair['shadow']['path'],pair['control']['path'],dataset)
                if not protocol or any(row['status']!='VERIFIED'for row in protocol):hard.append('unverified_host_protocol:'+str(worker)+':'+dataset)
    for dataset in sorted({e["member"][0]for e in plan["entries"]}):
        entries=[e for e in plan["entries"]if e["member"][0]==dataset]
        success={"shadow":0,"control":0};complete={"shadow":0,"control":0};memory_totals=dict(frames=0,eligible=0,geometry=0,perception=0,semantic=0)
        values={key:{"shadow":[],"control":[]}for key in ["sr","spl","ndtw","ne"]}
        for item in entries:
            sides={}
            for side in ("shadow","control"):
                path=root/"results"/item["key"]/side
                attempts=sorted(p for p in path.glob("*")if p.is_dir()and(p/"retention.json").exists())
                if not attempts:
                    hard.append("missing:"+item["key"]+":"+side);continue
                # Predeclared first complete valid attempt;all failures remain indexed.
                chosen=next((p for p in attempts if json.loads((p/"retention.json").read_bytes())["summary"].get("status")=="completed"),attempts[0])
                ep=EpisodeLifecycle(root,item["key"],side,chosen.name,plan_sha256=digest)
                trace=list(json_rows(chosen/"trace.jsonl.gz"));retention=json.loads((chosen/"retention.json").read_bytes())
                result=retention["summary"];audit=_native_result_audit(dict(trace=trace,result=result))
                if trace and trace[-1].get("native_metrics",{}).get("scope")=="synthetic_host_contract":
                    hard.append("synthetic_terminal_not_navigation:"+item["key"])
                if result.get("trace_sha256")!=retention["trace"]["raw_sha256"]:audit["errors"].append("native_trace_sha")
                inspect,_=_parser_functions();protocol_errors,_=inspect(trace)
                audit["errors"].extend(protocol_errors)
                good=audit["native_evidence_matched"]and not audit["errors"]
                complete[side]+=int(good)
                metrics=result.get("metrics")or{}
                for key in values:
                    value=metrics.get(key)
                    if isinstance(value,(int,float))and math.isfinite(value):values[key][side].append(value)
                success[side]+=int(good and metrics.get("sr")==1)
                if side=='shadow':
                    mem=result.get('map_memory',{});checked=result.get('memory_material_audit',{})
                    if mem.get('execution_mode')=='archive_only'or checked.get('execution_mode')=='archive_only':
                        hard.append('archive_only_not_navigation_geometry:'+item['key'])
                    if checked.get('status')!='VERIFIED':hard.append('missing_memory_material_audit:'+item['key'])
                    if require_release4:
                        sampling=checked.get('pose_sampling',{})
                        steps=[e for e in trace if e['kind']=='primitive_action']
                        expected_samples=1+sum(1 if e['action']==0 else 12 for e in steps)
                        if (sampling.get('mode')!='release4_12' or sampling.get('status')!='VERIFIED' or
                            sampling.get('samples')!=expected_samples or sampling.get('host_endpoints')!=len(steps)+1):
                            hard.append('release4_sampling_missing_or_incomplete:'+item['key'])
                    for target,source in [('frames','frames'),('eligible','eligible_endpoints'),('geometry','geometry_fused'),('perception','perception_complete'),('semantic','semantic_contribution_frames')]:
                        memory_totals[target]+=mem.get(source,0)
                sides[side]=ep
                rows.append(dict(member=item["member"],side=side,attempt=chosen.name,
                    native_audit=audit,status=result.get("status"),metrics=metrics,
                    retained_capabilities=retention["capabilities"]))
            if len(sides)==2:
                compared=audit_pair(sides["shadow"],sides["control"]);pairs.append(compared)
                if not compared["complete_execution_equivalent"]:hard.append("pair_incomplete_or_different:"+item["key"])
        policy_path=root/'control/acceptance_policy.json'
        if not policy_path.exists():hard.append('missing_frozen_geometry_acceptance_policy')
        else:
            policy=json.loads(policy_path.read_bytes())
            ratios=dict(geometry=memory_totals['geometry']/max(1,memory_totals['eligible']),
                perception=memory_totals['perception']/max(1,memory_totals['frames']),
                semantic=memory_totals['semantic']/max(1,memory_totals['eligible']))
            if (ratios['geometry']<policy['geometry_completion_min']or ratios['perception']<policy['perception_completion_min']or ratios['semantic']<policy['semantic_world_contribution_ratio_min']):
                hard.append('geometry_availability_gate:'+dataset)
        domains.append(dict(dataset=dataset,fixed_denominator=len(entries),successes=success,memory=memory_totals,
            SR={s:success[s]/len(entries)for s in success},native_complete=complete,
            metrics={k:{s:dict(mean=statistics.mean(v)if v else None,coverage=len(v))for s,v in by.items()}for k,by in values.items()}))
    result=dict(status="PASS_RETAINED_NATIVE_AUDIT"if not hard else"FAIL_OR_INCOMPLETE_RETAINED_AUDIT",
        domains=domains,hard_contract_errors=hard,pairs=len(pairs),
        scope="Native metrics/fixed denominators and causal receipts;not geometry availability or kernel-quota acceptance")
    atomic_json(out/"retained_report.json",result);atomic_json(out/"per_episode_audit.json",rows)
    return result
