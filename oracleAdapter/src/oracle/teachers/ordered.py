"""Uninterrupted ordered-reference execution with a controlled search-key choice."""
from collections import Counter
from dataclasses import asdict
import json
import math
from pathlib import Path
import time

from oracle.adapters.habitat.assets import resolve
from oracle.adapters.habitat.native import NativeAdapter, NativeState
from oracle.common.artifacts import content_digest, digest, runtime_identity, write_json
from oracle.common.identity import Context, exact_state_key
from oracle.contracts import Budget, Failure, MotionContract, Objective, Privilege, Purpose, TaskContract
from oracle.planners.action_space import search
from oracle.planners.soft_duplicate import pose_bucket
from oracle.verification.motion import native_violation, orientation_error
from oracle.verification.source_scene import SourceScene
from oracle.verification.execution_evidence import initial_contract_errors


class BudgetStop(RuntimeError):
    pass


def rounded_pose_key(state):
    x, y, z, w = state.quaternion_xyzw
    yaw = (2 * math.atan2(y, w)) % (2 * math.pi)
    return tuple(round(v * 100) for v in state.position) + (round(yaw * 1800 / math.pi) % 3600,)


def require_task_contract(task, protocol, method=None):
    soft=(method or {}).get('soft_duplicate_priority')
    if soft is not None:
        from oracle.planners.soft_duplicate import validate_config
        validate_config(soft)
        if (method or {}).get('state_key')!='lossless_pose' or (method or {}).get('search_priority_weight',1.)!=1.:
            raise ValueError('Soft-priority study retains exact keys and base priority1')
    weight=(method or {}).get('search_priority_weight',1.)
    if type(weight) not in (int,float) or not math.isfinite(weight) or weight < 1.:
        raise ValueError('Finite search priority weight >=1 required')
    contract = TaskContract(task["task_key"], Purpose(task["purpose"]), Objective(task["objective"]),
                            frozenset(Privilege(x) for x in task["privileges"]),
                            protocol["protocol_id"], content_digest(task), "initial_only")
    if contract.purpose not in {Purpose.REFERENCE, Purpose.LANDMARK_EXECUTION}:
        raise ValueError("Ordered execution is not a goal-only or expert-label task")
    required = {Privilege.POSE, Privilege.NAVMESH, Privilege.GOAL, Privilege.REFERENCE, Privilege.GEOMETRY}
    if contract.purpose == Purpose.LANDMARK_EXECUTION:
        required.add(Privilege.LANDMARK)
    policy = (method or {}).get("official_policy", "none")
    if policy not in {"none", "guard_only", "guard_then_search"}:
        raise ValueError("Unknown official prefix policy")
    if policy != "none":
        required.add(Privilege.ACTIONS)
    expected_objective = Objective.LANDMARK_ORDER if contract.purpose == Purpose.LANDMARK_EXECUTION else Objective.REFERENCE_ORDER
    if contract.privileges != frozenset(required) or contract.objective != expected_objective:
        raise ValueError("Teacher objective/privileges mismatch")
    return contract


def execute(case_root, task, method, protocol, output):
    """Both arms share this controller, budgets and verifier; only key differs.

    This is a new controlled implementation, not a byte-identical replay of
    historical RobustOracle. Cost/depth Pareto dominance is common to both arms.
    """
    output = Path(output)
    import resource
    output.mkdir(parents=True, exist_ok=False)
    started, cpu_started = time.perf_counter(), time.process_time()
    contract = require_task_contract(task, protocol, method)
    prefix = None
    source_action_indices = []
    prefix_switch_recorded = False
    if method.get("official_policy", "none") != "none":
        from oracle.teachers.official import expand_actions
        from oracle.portfolio.guarded_prefix import GuardedPrefix
        official = task["official_demonstration"]
        if content_digest(official["actions"]) != official["actions_sha256"] or method["source_turn_degrees"] != 30 or protocol["turn_degrees"] != 15:
            raise ValueError("Official action/angle identity mismatch")
        expanded, source_action_indices = expand_actions(official["actions"])
        prefix = GuardedPrefix(expanded)
    asset, geometry = resolve(case_root, task)
    motion = MotionContract(**{k: protocol[k] for k in MotionContract.__dataclass_fields__})
    source = SourceScene(geometry["receipt_path"], geometry["receipt_sha256"], protocol, catalog=geometry)
    execution = NativeAdapter(asset["navmesh_path"], asset["navmesh_sha256"], motion)
    planner = NativeAdapter(asset["navmesh_path"], asset["navmesh_sha256"], motion)
    env = runtime_identity()
    initial = NativeState(tuple(task["targets"][0]), tuple(task["start_rotation"]))
    execution.restore(initial)
    positions = [list(execution.snapshot().position)]
    rotations = [list(execution.snapshot().quaternion_xyzw)]
    actions, boundaries, attempts, events = [], [], [], []
    action_origins, official_source_indices = [], []
    rejections = Counter()
    deadline = started + method["max_task_wall_seconds"]
    planned_calls_start = planner.native_calls
    planning_started = time.perf_counter()
    greedy_calls = 0
    failure, detail = Failure.NONE, None
    last_rejection = None
    context = Context(geometry["scene_sha256"], task["profile_sha256"], content_digest(asdict(motion)),
                      content_digest(task), content_digest(protocol), task["module_source_sha256"],
                      content_digest(env), "native_xyz_quaternion_xyzw")
    planning_source = source
    if method.get("planning_query_cache") is not None:
        from oracle.planners.collision_queries import CachedSourceQueries
        planning_source = CachedSourceQueries(source, context_digest=context.digest(),
                                              **method["planning_query_cache"])
    progress_guard = None
    if method.get("reference_progress_guard") is not None:
        if prefix is None or method["official_policy"] != "guard_then_search":
            raise ValueError("Reference progress fallback requires explicit official prefix portfolio")
        from oracle.portfolio.reference_progress import ReferenceProgressGuard
        progress_guard = ReferenceProgressGuard(**method["reference_progress_guard"])
    progress_queries = []
    trace = (output / "executed.jsonl").open("x", encoding="utf-8")
    trace.write(json.dumps({"kind": "initial", "position": positions[0], "rotation": rotations[0]}) + "\n")
    trace.flush()

    def check_budget():
        if time.perf_counter() >= deadline:
            raise BudgetStop("task_wall_seconds")
        if planner.native_calls - planned_calls_start >= method["max_native_preview_calls"]:
            raise BudgetStop("native_preview_calls")

    try:
        actual_initial = execution.snapshot()
        initial_errors = initial_contract_errors(initial, actual_initial, protocol)
        if initial_errors:
            failure, detail = Failure.NATIVE_ACTION, ",".join(initial_errors)
        elif source.contact(actual_initial.position, actual_initial.position, certificate=True):
            failure, detail = Failure.SOURCE_CONTACT, "initial_source_contact"
        elif not execution.is_navigable(actual_initial.position):
            failure, detail = Failure.NATIVE_ACTION, "initial_offmesh"
        else:
            for reference_index, target in enumerate(task["targets"][1:], 1):
                segment_actions = 0
                pending = []
                visits = Counter()
                follower = execution.sim.make_greedy_follower(goal_radius=motion.goal_radius_m,
                           stop_key=0, forward_key=1, left_key=2, right_key=3)

                def distance(state):
                    return planner.geodesic_distance(state.position, target)

                def transition(state, action):
                    nonlocal last_rejection
                    last_rejection = None
                    check_budget()
                    planner.restore(state)
                    following = planner.step(action)
                    reason = native_violation(planner, state, following, action, protocol)
                    if reason:
                        rejections[reason] += 1
                        last_rejection = {"reason": reason, "before": list(state.position), "after": list(following.position)}
                        return None
                    if not math.isfinite(distance(following)):
                        rejections["target_disconnected"] += 1
                        last_rejection = {"reason": "target_disconnected", "before": list(state.position), "after": list(following.position)}
                        return None
                    hit = planning_source.contact(state.position, following.position)
                    if hit:
                        rejections["source_contact"] += 1
                        last_rejection = {"reason": "source_contact", "before": list(state.position), "after": list(following.position), "contact": hit}
                        return None
                    return following

                def state_key(state):
                    if method["state_key"] == "lossless_pose":
                        return exact_state_key(state.key_values(), reference_index, context)
                    if method["state_key"] == "rounded_pose_forward_bit":
                        return rounded_pose_key(state) + (transition(state, 1) is not None,)
                    raise ValueError("Unregistered state-key strategy")

                while True:
                    check_budget()
                    current = execution.snapshot()
                    remaining_distance = distance(current)
                    if not math.isfinite(remaining_distance):
                        failure, detail = Failure.TOPOLOGY, "current_target_disconnected"
                        break
                    if remaining_distance <= motion.goal_radius_m:
                        boundaries.append({"reference_index": reference_index, "action_index": len(actions),
                                           "distance_m": remaining_distance})
                        trace.write(json.dumps({"kind": "boundary", **boundaries[-1]}) + "\n")
                        trace.flush()
                        break
                    if segment_actions >= method["max_actions_per_reference"] or len(actions) >= method["max_task_actions"]:
                        raise BudgetStop("actual_action_limit")
                    action, predicted = None, None
                    action_origin, source_action_index = None, None
                    monitor_key = rounded_pose_key(current)
                    visits[monitor_key] += 1
                    if prefix is not None and prefix.reason is None:
                        def accept_progress(proposed, following):
                            if progress_guard is None:
                                return None
                            after_distance=distance(following)
                            reason=progress_guard.check(reference_index,remaining_distance,after_distance)
                            progress_queries.append({"reference_index":reference_index,"action_index":len(actions),
                                "proposed_action":proposed,"before_distance_m":remaining_distance,
                                "after_distance_m":after_distance,"proposed_position":list(following.position),
                                "proposed_rotation":list(following.quaternion_xyzw),"reason":reason,
                                "monitor":progress_guard.record()})
                            return reason
                        proposal = prefix.propose(lambda proposed: transition(current, proposed),accept_progress)
                        if proposal is not None:
                            action, predicted = proposal
                            action_origin = "official_suggestion"
                            source_action_index = source_action_indices[prefix.consumed - 1]
                        elif not prefix_switch_recorded:
                            events.append({"kind": "official_prefix_stopped", "reason": prefix.reason,
                                           "expanded_source_primitives_consumed": prefix.consumed, "reference_index": reference_index,
                                           "actual_action_index": len(actions), "rejection": last_rejection,
                                           "execution_state": {"position": list(current.position), "rotation": list(current.quaternion_xyzw)},
                                           "next_stage": "failure" if method["official_policy"] == "guard_only" else "native_greedy_and_bounded_search"})
                            prefix_switch_recorded = True
                    if prefix is not None and prefix.reason is not None and method["official_policy"] == "guard_only":
                        reason = (last_rejection or {}).get("reason")
                        failure = Failure.SOURCE_CONTACT if reason == "source_contact" else Failure.NATIVE_ACTION if reason not in (None, "target_disconnected") else Failure.TOPOLOGY if reason == "target_disconnected" else Failure.UNKNOWN
                        detail = "unexecuted_official_proposal_" + (reason or prefix.reason)
                        break
                    if action is None and pending:
                        proposed = pending.pop(0)
                        predicted = transition(current, proposed)
                        if predicted is not None:
                            action = proposed
                            action_origin = "local_search"
                        else:
                            events.append({"kind": "plan_rejected", "reference_index": reference_index,
                                           "action_index": len(actions)})
                            pending = []
                    if action is None and visits[monitor_key] < method["greedy_visit_threshold"]:
                        try:
                            greedy_calls += 1
                            proposed = follower.next_action_along(target)
                        except execution.habitat_sim.errors.GreedyFollowerError:
                            proposed = None
                        if execution.snapshot() != current:
                            failure, detail = Failure.UNKNOWN, "follower_mutated_execution_state"
                            break
                        if proposed in (1, 2, 3):
                            predicted = transition(current, int(proposed))
                            if predicted is not None:
                                action = int(proposed)
                                action_origin = "native_greedy"
                    if action is None:
                        if len(attempts) >= method["max_searches_per_task"]:
                            raise BudgetStop("search_count")
                        remaining_actions = min(method["max_actions_per_reference"] - segment_actions,
                                                method["max_task_actions"] - len(actions))
                        attempt = {"reference_index": reference_index, "failure": "RUNNING", "expansions": 0,
                                   "transition_calls": 0, "frontier_peak": 1}
                        attempts.append(attempt)
                        search_started = time.perf_counter()
                        def observe(expansions, transition_calls, frontier_peak):
                            attempt.update(expansions=expansions, transition_calls=transition_calls, frontier_peak=frontier_peak)
                        result = search(current, actions=(1, 2, 3), transition=transition, key=state_key,
                                        reached=lambda s: distance(s) <= motion.goal_radius_m,
                                        heuristic=lambda s: distance(s) / motion.forward_m,
                                        action_costs={int(k): v for k, v in method["action_costs"].items()},
                                        budget=Budget(method["max_expansions_per_search"], method["max_transition_calls_per_search"],
                                                      remaining_actions, min(method["max_search_wall_seconds"], max(.000001, deadline - time.perf_counter()))), progress=observe,
                                        priority_weight=method.get('search_priority_weight',1.),
                                        soft_duplicate_key=(lambda s: pose_bucket(s,method['soft_duplicate_priority'])) if method.get('soft_duplicate_priority') is not None else None,
                                        soft_duplicate_weight=method.get('soft_duplicate_priority',{}).get('maximum_priority_weight',2.))
                        attempt.update(failure=result.failure.value, expansions=result.expansions,
                                       transition_calls=result.transition_calls, frontier_peak=result.frontier_peak,
                                       wall_seconds=result.elapsed_seconds, plan_actions=len(result.actions),
                                       stop_reason=result.stop_reason,search_diagnostics=result.diagnostics,
                                       priority_weight=method.get('search_priority_weight',1.))
                        if method.get('soft_duplicate_priority') is not None:
                            attempt['soft_duplicate_priority']=method['soft_duplicate_priority']
                        if result.failure != Failure.NONE:
                            failure, detail = result.failure, "bounded_search_did_not_find_plan"
                            break
                        pending = list(result.actions)
                        if not pending:
                            failure, detail = Failure.UNKNOWN, "empty_plan_before_goal"
                            break
                        action = pending.pop(0)
                        action_origin = "local_search"
                        predicted = transition(current, action)
                        if predicted is None:
                            failure, detail = Failure.UNKNOWN, "new_plan_first_transition_not_reproducible"
                            break
                    actual = execution.step(action)
                    actions.append(action)
                    action_origins.append(action_origin)
                    official_source_indices.append(source_action_index)
                    positions.append(list(actual.position))
                    rotations.append(list(actual.quaternion_xyzw))
                    segment_actions += 1
                    trace.write(json.dumps({"kind": "action", "index": len(actions), "action": action,
                                            "action_origin": action_origin, "official_source_action_index": source_action_index,
                                            "position": positions[-1], "rotation": rotations[-1]}) + "\n")
                    trace.flush()
                    violation = native_violation(execution, current, actual, action, protocol)
                    if violation:
                        failure, detail = Failure.NATIVE_ACTION, violation
                        break
                    contact = source.contact(current.position, actual.position, certificate=True)
                    if contact:
                        events.append({"kind": "actual_source_contact", "action_index": len(actions), "contact": contact})
                        failure, detail = Failure.SOURCE_CONTACT, "actual_linear_source_contact"
                        break
                    if math.dist(predicted.position, actual.position) > protocol["maximum_prediction_error_m"] or orientation_error(predicted.quaternion_xyzw, actual.quaternion_xyzw) > protocol["maximum_orientation_error_rad"]:
                        failure, detail = Failure.UNKNOWN, "prediction_actual_mismatch"
                        break
                if failure != Failure.NONE:
                    break
    except BudgetStop as error:
        failure, detail = Failure.SEARCH_BUDGET, str(error)
        if attempts and attempts[-1]["failure"] == "RUNNING":
            attempts[-1].update(failure=failure.value, detail=detail, wall_seconds=time.perf_counter() - search_started)
    finally:
        trace.close()
        execution.close()
        planner.close()
    success = failure == Failure.NONE and len(boundaries) == len(task["targets"]) - 1
    result = {"status": "EXECUTED_PENDING_INDEPENDENT_AUDIT" if success else "FAILURE_PRESERVED",
              "task_key": task["task_key"], "cohort": task["cohort"], "task_sha256": content_digest(task),
              "task_contract": contract.to_record(), "method": method, "method_sha256": content_digest(method),
              "protocol": protocol, "profile_sha256": task["profile_sha256"], "geometry_sha256": source.geometry_sha256,
              "environment": env, "actual_teacher_path": __file__, "teacher_sha256": digest(__file__),
              "failure": failure.value, "detail": detail, "initialization_count": execution.restore_calls,
              "trace_sha256": digest(output / "executed.jsonl"),
              "initialization_count_scope": "Actual explicit NativeAdapter.restore calls on execution adapter; planner restores are separate",
              "actions": actions, "positions": positions, "rotations": rotations,
              "boundaries": boundaries, "search_attempts": attempts, "events": events,
              "official_policy": method.get("official_policy", "none"),
              "official_primitives_consumed": prefix.consumed if prefix is not None else 0,
              "action_origins": action_origins, "official_source_action_indices": official_source_indices,
              "reference_progress_queries": progress_queries,
              "planning_query_cache_metrics": getattr(planning_source,"metrics",None),
              "rejected_planner_transitions": dict(rejections),
              "cost": {"total_wall_seconds": time.perf_counter() - started,
                       "planning_and_execution_wall_seconds": time.perf_counter() - planning_started,
                       "cpu_seconds": time.process_time() - cpu_started, "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                       "native_preview_calls": planner.native_calls, "actual_native_calls": len(actions),
                       "greedy_calls": greedy_calls, "greedy_internal_native_probes": "NOT_INSTRUMENTED",
                       "source_queries": source.queries + (planning_source.queries if planning_source is not source else 0),
                       "triangle_checks": source.triangle_checks + (planning_source.triangle_checks if planning_source is not source else 0),
                       "search_expansions": sum(r["expansions"] for r in attempts)},
              "limits": "Ordered-reference research teacher; no intermediate execution reset. Independent replay is still required. Legacy-like control and lossless arm share this new controller, not historical byte-identical code. Finite failure is not physical impossibility."}
    write_json(output / "result.json", result)
    return result
