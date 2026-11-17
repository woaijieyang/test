"""Separate-process native replay and a rational geometry cross-check."""
import json
import math
from pathlib import Path
import time

from oracle.adapters.habitat.assets import resolve
from oracle.adapters.habitat.native import NativeAdapter, NativeState
from oracle.common.artifacts import content_digest, digest, write_json
from oracle.contracts import MotionContract
from oracle.verification.motion import native_violation, orientation_error
from oracle.verification.source_scene import SourceScene
from oracle.verification.execution_evidence import initial_contract_errors,check_trace_stream


def official_expansion_for_audit(actions):
    """Independent source-primitive reconstruction; do not import the teacher."""
    if not actions or actions[-1] != 0 or any(type(a) is not int for a in actions) or actions.count(0) != 1:
        raise ValueError("Invalid source STOP/type contract")
    result=[];indices=[]
    for i,a in enumerate(actions[:-1]):
        if a == 1: values=(1,)
        elif a == 2: values=(2,2)
        elif a == 3: values=(3,3)
        else: raise ValueError("Unsupported official primitive")
        result.extend(values);indices.extend([i]*len(values))
    return result,indices


def audit_prefix_origins(task, record):
    policy=record['method'].get('official_policy','none')
    if policy=='none':return []
    expanded,indices=official_expansion_for_audit(task['official_demonstration']['actions'])
    n=record['official_primitives_consumed'];actions=record['actions'];origins=record['action_origins']
    source_indices=record['official_source_action_indices'];issues=[]
    if (not 0<=n<=len(actions) or len(origins)!=len(actions) or len(source_indices)!=len(actions)
        or actions[:n]!=expanded[:n] or origins[:n]!=['official_suggestion']*n
        or source_indices[:n]!=indices[:n] or any(x=='official_suggestion' for x in origins[n:])
        or any(x is not None for x in source_indices[n:]) or record['official_policy']!=policy):
        issues.append('official_prefix_action_provenance')
    switches=[e for e in record['events'] if e['kind']=='official_prefix_stopped']
    if len(switches)>1 or (len(actions)>n and (len(switches)!=1 or switches[0]['actual_action_index']!=n)):
        issues.append('official_prefix_switch_provenance')
    if policy=='guard_only' and len(actions)!=n:issues.append('guard_only_executed_fallback')
    return issues


def audit_progress_queries(task,record,geodesic):
    """Recompute policy arithmetic independently; no planner guard import."""
    cfg=record['method'].get('reference_progress_guard')
    if cfg is None:return []
    queries=record.get('reference_progress_queries',[]);n=record['official_primitives_consumed']
    if len(queries) not in (n,n+1):return ['progress_query_coverage']
    issues=[];reference=None;best=None;stalled=0
    tolerance=record['protocol']['maximum_prediction_error_m']
    for i,q in enumerate(queries):
        j=q['action_index'];k=q['reference_index']
        expected_ref=1+sum(b['action_index']<=j for b in record['boundaries'])
        if j!=i or k!=expected_ref or not 1<=k<len(task['targets']):
            issues.append('progress_reference_occurrence');continue
        before=geodesic(record['positions'][j],task['targets'][k])
        after=geodesic(q['proposed_position'],task['targets'][k])
        if not math.isfinite(before) or not math.isfinite(after):
            issues.append('progress_nonfinite_distance');continue
        if abs(before-q['before_distance_m'])>tolerance or abs(after-q['after_distance_m'])>tolerance:
            issues.append('progress_distance_binding')
        if reference!=k:reference=k;best=before;stalled=0
        best=min(best,before);reason=None
        if after>best+cfg['max_excess_distance_m']:reason='reference_distance_excursion'
        else:
            if after<best:best=after;stalled=0
            else:stalled+=1
            if stalled>=cfg['max_nonprogress_actions']:reason='reference_progress_stalled'
        if q['reason']!=reason:issues.append('progress_policy_verdict')
        if q['monitor']!={'reference_index':k,'best_distance_m':best,'nonprogress_actions':stalled}:
            issues.append('progress_monitor_state')
        if i<n:
            if reason is not None or q['proposed_action']!=record['actions'][i] or math.dist(q['proposed_position'],record['positions'][i+1])>tolerance:
                issues.append('progress_accepted_action_binding')
        elif reason is None:issues.append('progress_rejection_missing')
    return issues


def audit(case_root, task, result_path, output):
    started = time.perf_counter()
    result_path, output = Path(result_path), Path(output)
    record = json.loads(result_path.read_text())
    if record["task_key"] != task["task_key"] or record["task_sha256"] != content_digest(task):
        raise RuntimeError("Replay task identity mismatch")
    if record["initialization_count"] != 1:
        raise RuntimeError("Uninterrupted route contains resets")
    raw_stream = check_trace_stream(record, result_path.with_name("executed.jsonl"))
    protocol = record["protocol"]
    motion = MotionContract(**{k: protocol[k] for k in MotionContract.__dataclass_fields__})
    asset, geometry = resolve(case_root, task)
    scene = SourceScene(geometry["receipt_path"], geometry["receipt_sha256"], protocol, catalog=geometry)
    simulator = NativeAdapter(asset["navmesh_path"], asset["navmesh_sha256"], motion)
    if len(record["positions"]) != len(record["actions"]) + 1 or len(record["rotations"]) != len(record["positions"]):
        raise RuntimeError("Incomplete primitive trace")
    if len(record["actions"]) > record["method"]["max_task_actions"]:
        raise RuntimeError("Actual action budget violated")
    initial = NativeState(tuple(task["targets"][0]), tuple(task["start_rotation"]))
    simulator.restore(initial)
    states = [simulator.snapshot()]
    issues, physical_alerts = audit_prefix_origins(task, record), []
    maximum_error = math.dist(states[0].position, record["positions"][0])
    maximum_angle = orientation_error(states[0].quaternion_xyzw, record["rotations"][0])
    try:
        issues.extend(initial_contract_errors(initial,states[0],protocol))
        initial_contact = scene.contact(states[0].position, states[0].position, arithmetic="rational_hull")
        if initial_contact:
            physical_alerts.append({"index": 0, "kind": "initial_source_contact", "contact": initial_contact})
        for index, action in enumerate(record["actions"], 1):
            before = states[-1]
            following = simulator.step(action)
            states.append(following)
            maximum_error = max(maximum_error, math.dist(following.position, record["positions"][index]))
            maximum_angle = max(maximum_angle, orientation_error(following.quaternion_xyzw, record["rotations"][index]))
            native = native_violation(simulator, before, following, action, protocol)
            if native:
                physical_alerts.append({"index": index, "kind": native})
            hit = scene.contact(before.position, following.position, arithmetic="rational_hull")
            if hit:
                physical_alerts.append({"index": index, "kind": "rational_source_contact", "contact": hit})
        if maximum_error > protocol["maximum_replay_error_m"] or maximum_angle > protocol["maximum_orientation_error_rad"]:
            issues.append("native_replay_mismatch")
        issues.extend(audit_progress_queries(task,record,simulator.geodesic_distance))
        guard_probe_actions=0
        rejected=[q for q in record.get('reference_progress_queries',[]) if q['reason'] is not None]
        if rejected:
            probe=NativeAdapter(asset['navmesh_path'],asset['navmesh_sha256'],motion)
            try:
                for q in rejected:
                    j=q['action_index'];probe.restore(states[j]);following=probe.step(q['proposed_action']);guard_probe_actions+=1
                    if (math.dist(following.position,q['proposed_position'])>protocol['maximum_prediction_error_m']
                            or orientation_error(following.quaternion_xyzw,q['proposed_rotation'])>protocol['maximum_orientation_error_rad']):
                        issues.append('rejected_progress_preview_not_native_reproducible')
            finally:probe.close()
        previous = 0
        for expected_index, boundary in enumerate(record["boundaries"], 1):
            index = boundary["action_index"]
            if boundary["reference_index"] != expected_index or not previous <= index < len(states):
                raise RuntimeError("Reference ordering/boundary corruption")
            if index - previous > record["method"]["max_actions_per_reference"]:
                raise RuntimeError("Reference action budget violated")
            distance = simulator.geodesic_distance(states[index].position, task["targets"][expected_index])
            if not math.isfinite(distance) or distance > motion.goal_radius_m:
                issues.append("mandatory_reference_not_reached")
            previous = index
        complete = record["status"] == "EXECUTED_PENDING_INDEPENDENT_AUDIT"
        if complete and (record["failure"] != "none" or len(record["boundaries"]) != len(task["targets"]) - 1):
            issues.append("false_execution_completion")
        if physical_alerts and record["failure"] not in {"native_action_illegal", "source_geometry_contact"}:
            issues.append("execution_verification_disagreement")
        accepted = complete and not issues and not physical_alerts
        report = {"status": "PASS_ORDERED_NATIVE_AND_RATIONAL_REPLAY" if accepted else "AUDIT_DISAGREEMENT" if issues else "FAILURE_PRESERVED",
                  "task_key": task["task_key"], "cohort": task["cohort"],
                  "source_result_sha256": digest(result_path), "task_sha256": content_digest(task),
                  "worker_failure": record["failure"], "worker_detail": record["detail"],
                  "full_route_accepted": accepted, "executed_actions_replayed": len(record["actions"]),
                  "max_position_error_m": maximum_error, "max_orientation_error_rad": maximum_angle,
                  "issues": issues, "physical_alerts": physical_alerts,
                  "raw_stream_binding": raw_stream,
                  "replay_explicit_initialization_count": simulator.restore_calls,
                  "verification_arithmetic": "rational_hull_and_certificate_check",
                  "geometry_shared_assumptions": "Same native-exported input, height slab and broadphase as planning; not complete physical-model independence.",
                  "source_queries": scene.queries, "triangle_checks": scene.triangle_checks,
                  "progress_policy_recomputed":record['method'].get('reference_progress_guard') is not None,
                  "unexecuted_progress_proposals_independently_probed":guard_probe_actions,
                  "wall_seconds": time.perf_counter() - started,
                  "actual_auditor_path": __file__, "auditor_sha256": digest(__file__),
                  "scope": "Separate-process full ordered-route replay; no model score, no failure exclusion."}
        write_json(output, report)
        return report
    finally:
        simulator.close()
