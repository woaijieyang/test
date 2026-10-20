"""Execute a source-bound official demonstration under the unchanged target gate.

This controller is not an optimizer and offers no fallback or reachability proof.
Native replay is required even for source demonstrations previously reported PASS.
"""
import json
import math
from pathlib import Path
import time

from oracle.adapters.habitat.assets import resolve
from oracle.adapters.habitat.native import NativeAdapter, NativeState
from oracle.common.artifacts import content_digest, digest, runtime_identity, write_json
from oracle.contracts import Failure, MotionContract, Objective, Privilege, Purpose, TaskContract
from oracle.verification.motion import native_violation, orientation_error
from oracle.verification.source_scene import SourceScene


def expand_actions(actions):
    if (not actions or any(type(a) is not int or a not in (0, 1, 2, 3) for a in actions)
            or actions[-1] != 0 or actions.count(0) != 1):
        raise ValueError("Only complete terminal-STOP 0/1/2/3 source action sequences are supported")
    expanded, indices = [], []
    for index, action in enumerate(actions[:-1]):
        expanded.extend([action] * (2 if action in (2, 3) else 1))
        indices.extend([index] * (2 if action in (2, 3) else 1))
    return expanded, indices


def advance_boundaries(targets, next_index, action_index, distance, radius):
    boundaries = []
    while next_index < len(targets):
        value = distance(targets[next_index])
        if not math.isfinite(value) or value > radius:
            break
        boundaries.append({"reference_index": next_index, "action_index": action_index, "distance_m": value})
        next_index += 1
    return boundaries


def execute(case_root, task, method, protocol, output):
    import resource
    started, cpu_started = time.perf_counter(), time.process_time()
    expected = {Privilege.POSE, Privilege.NAVMESH, Privilege.GOAL, Privilege.REFERENCE,
                Privilege.GEOMETRY, Privilege.LANDMARK, Privilege.ACTIONS}
    contract = TaskContract(task["task_key"], Purpose(task["purpose"]), Objective(task["objective"]),
                            frozenset(Privilege(p) for p in task["privileges"]), protocol["protocol_id"],
                            content_digest(task), "initial_only")
    if contract.purpose != Purpose.LANDMARK_EXECUTION or contract.objective != Objective.LANDMARK_ORDER or contract.privileges != expected:
        raise ValueError("Official ordered demonstration contract mismatch")
    if method["source_turn_degrees"] != 30 or protocol["turn_degrees"] != 15:
        raise ValueError("Unverified angle translator")
    original = task["official_demonstration"]["actions"]
    if content_digest(original) != task["official_demonstration"]["actions_sha256"]:
        raise ValueError("Official action source drift")
    proposed, source_indices = expand_actions(original)
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    asset, geometry = resolve(case_root, task)
    motion = MotionContract(**{k: protocol[k] for k in MotionContract.__dataclass_fields__})
    source = SourceScene(geometry["receipt_path"], geometry["receipt_sha256"], protocol, catalog=geometry)
    simulator = NativeAdapter(asset["navmesh_path"], asset["navmesh_sha256"], motion)
    environment = runtime_identity()
    initial = NativeState(task["targets"][0], task["start_rotation"])
    simulator.restore(initial)
    initial_actual = simulator.snapshot()
    positions, rotations = [list(initial_actual.position)], [list(initial_actual.quaternion_xyzw)]
    actions, boundaries, events = [], [], []
    failure, detail = Failure.NONE, None
    planning_started = time.perf_counter()
    trace = (output / "executed.jsonl").open("x", encoding="utf-8")
    def log(value):
        trace.write(json.dumps(value) + "\n"); trace.flush()
    def reached():
        point = simulator.snapshot().position
        new = advance_boundaries(task["targets"], len(boundaries) + 1, len(actions),
                    lambda goal: simulator.geodesic_distance(point, goal), motion.goal_radius_m)
        boundaries.extend(new)
        for row in new: log({"kind": "boundary", **row})
    log({"kind": "initial", "position": positions[0], "rotation": rotations[0]})
    try:
        if math.dist(initial.position, initial_actual.position) > protocol["maximum_prediction_error_m"] or orientation_error(initial.quaternion_xyzw, initial_actual.quaternion_xyzw) > protocol["maximum_orientation_error_rad"]:
            failure, detail = Failure.NATIVE_ACTION, "initial_reset_mismatch"
        elif not simulator.is_navigable(initial_actual.position):
            failure, detail = Failure.NATIVE_ACTION, "initial_offmesh"
        elif source.contact(initial_actual.position, initial_actual.position, certificate=True):
            failure, detail = Failure.SOURCE_CONTACT, "initial_source_contact"
        else:
            reached()
            for source_offset, action in enumerate(proposed):
                if len(boundaries) == len(task["targets"]) - 1: break
                if time.perf_counter() - started >= method["max_task_wall_seconds"]:
                    failure, detail = Failure.SEARCH_BUDGET, "official_replay_wall_budget"; break
                previous_boundary = boundaries[-1]["action_index"] if boundaries else 0
                if len(actions) >= method["max_task_actions"] or len(actions) - previous_boundary >= method["max_actions_per_reference"]:
                    failure, detail = Failure.SEARCH_BUDGET, "actual_action_limit"; break
                before = simulator.snapshot()
                after = simulator.step(action)
                actions.append(action); positions.append(list(after.position)); rotations.append(list(after.quaternion_xyzw))
                log({"kind": "action", "index": len(actions), "action": action,
                     "official_source_action_index": source_indices[source_offset], "position": positions[-1], "rotation": rotations[-1]})
                reason = native_violation(simulator, before, after, action, protocol)
                if reason:
                    failure, detail = Failure.NATIVE_ACTION, reason; break
                contact = source.contact(before.position, after.position, certificate=True)
                if contact:
                    events.append({"kind": "actual_source_contact", "action_index": len(actions), "contact": contact})
                    failure, detail = Failure.SOURCE_CONTACT, "actual_linear_source_contact"; break
                reached()
            if failure == Failure.NONE and len(boundaries) != len(task["targets"]) - 1:
                failure, detail = Failure.UNKNOWN, "official_actions_exhausted_before_required_targets"
    finally:
        trace.close(); simulator.close()
    success = failure == Failure.NONE and len(boundaries) == len(task["targets"]) - 1
    result = {"status": "EXECUTED_PENDING_INDEPENDENT_AUDIT" if success else "FAILURE_PRESERVED",
        "task_key": task["task_key"], "cohort": task["cohort"], "task_sha256": content_digest(task),
        "task_contract": contract.to_record(), "method": method, "method_sha256": content_digest(method),
        "protocol": protocol, "profile_sha256": task["profile_sha256"], "geometry_sha256": source.geometry_sha256,
        "environment": environment, "actual_teacher_path": __file__, "teacher_sha256": digest(__file__),
        "failure": failure.value, "detail": detail, "initialization_count": simulator.restore_calls,
        "trace_sha256": digest(output / "executed.jsonl"),
        "initialization_count_scope": "Actual explicit NativeAdapter.restore calls on execution adapter",
        "actions": actions, "positions": positions, "rotations": rotations, "boundaries": boundaries,
        "search_attempts": [], "events": events,
        "official_actions_source_sha256": task["official_demonstration"]["actions_sha256"],
        "source_initial_to_task_start_distance_m": math.dist(task["official_demonstration"]["start_position"], task["targets"][0]),
        "cost": {"total_wall_seconds": time.perf_counter()-started, "planning_and_execution_wall_seconds": time.perf_counter()-planning_started,
                 "cpu_seconds": time.process_time()-cpu_started, "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                 "native_preview_calls": 0, "actual_native_calls": len(actions), "greedy_calls": 0,
                 "greedy_internal_native_probes": "NOT_USED", "source_queries": source.queries,
                 "triangle_checks": source.triangle_checks, "search_expansions": 0},
        "limits": "Source demonstration reexecution with original historical demonstration initial orientation and mapping. No midroute resets or fallback. Different source body/sliding; only actual current execution can pass. Not an algorithm gain over the prior different-start Oracle."}
    write_json(output / "result.json", result)
    return result
