"""Only implemented capabilities are registered; no algorithm-name promises."""
from dataclasses import asdict, dataclass
from oracle.contracts import Purpose, Objective, Privilege, Proof


@dataclass(frozen=True)
class Method:
    name: str
    purposes: tuple[Purpose, ...]
    objectives: tuple[Objective, ...]
    privileges: tuple[Privilege, ...]
    output: Proof | str
    implementation: str
    evidence_level: str


METHODS = {
    "guarded_official_reference_portfolio": Method(
        "guarded_official_reference_portfolio", (Purpose.REFERENCE,), (Objective.REFERENCE_ORDER,),
        (Privilege.POSE, Privilege.NAVMESH, Privilege.GOAL, Privilege.REFERENCE, Privilege.GEOMETRY, Privilege.ACTIONS),
        Proof.NATIVE_TRACE, "oracle.teachers.ordered:execute",
        "Existing reference-purpose prefix policy, including compatible RxR tasks; distinct from Landmark annotation privilege. No new controller or acceptance protocol"),
    "guarded_official_prefix_portfolio": Method(
        "guarded_official_prefix_portfolio", (Purpose.LANDMARK_EXECUTION,), (Objective.LANDMARK_ORDER,),
        (Privilege.POSE, Privilege.NAVMESH, Privilege.GOAL, Privilege.REFERENCE, Privilege.GEOMETRY, Privilege.LANDMARK, Privilege.ACTIONS),
        Proof.NATIVE_TRACE, "oracle.teachers.ordered:execute",
        "Explicit guard_only or guard_then_search config; one-way pre-execution switch, common total ceilings, independent audit required"),
    "ordered_reference_teacher": Method(
        "ordered_reference_teacher", (Purpose.REFERENCE,), (Objective.REFERENCE_ORDER,),
        (Privilege.POSE, Privilege.NAVMESH, Privilege.GOAL, Privilege.REFERENCE, Privilege.GEOMETRY),
        Proof.NATIVE_TRACE, "oracle.teachers.ordered:execute",
        "Fixed native greedy/bounded action search with explicit key configuration; separate route audit required"),
    "ordered_landmark_teacher": Method(
        "ordered_landmark_teacher", (Purpose.LANDMARK_EXECUTION,), (Objective.LANDMARK_ORDER,),
        (Privilege.POSE, Privilege.NAVMESH, Privilege.GOAL, Privilege.REFERENCE, Privilege.GEOMETRY, Privilege.LANDMARK),
        Proof.NATIVE_TRACE, "oracle.teachers.ordered:execute",
        "Ordered occurrences with no midroute reset; bounded failure is not unreachability"),
    "official_landmark_demonstration": Method(
        "official_landmark_demonstration", (Purpose.LANDMARK_EXECUTION,), (Objective.LANDMARK_ORDER,),
        (Privilege.POSE, Privilege.NAVMESH, Privilege.GOAL, Privilege.REFERENCE, Privilege.GEOMETRY, Privilege.LANDMARK, Privilege.ACTIONS),
        Proof.NATIVE_TRACE, "oracle.teachers.official:execute",
        "Source-bound plan reexecution; explicit official action privilege and initial-state lineage, separate strict audit required"),
    "archived_alias_native_probe": Method(
        "archived_alias_native_probe", (Purpose.FEASIBILITY,), (Objective.TRANSITION_CHECK,),
        (Privilege.POSE, Privilege.NAVMESH, Privilege.GOAL, Privilege.REFERENCE, Privilege.GEOMETRY),
        Proof.NATIVE_TRACE, "oracle.verification.alias_probe:run",
        "Native transition and positive-contact checks only; no complete-route or novelty claim"),
    "bounded_native_action_search": Method(
        "bounded_native_action_search", (Purpose.GOAL,),
        (Objective.GOAL_ONLY,),
        (Privilege.POSE, Privilege.NAVMESH, Privilege.GOAL),
        Proof.CANDIDATE_PLAN, "oracle.planners.action_space:search",
        "CPU contract tests and integration through ordered teachers; search itself supplies no native/source acceptance"),
    "exact_landmark_occurrences": Method(
        "exact_landmark_occurrences", (Purpose.LANDMARK,), (Objective.LANDMARK_ORDER,),
        (Privilege.LANDMARK, Privilege.REFERENCE), "ordered_source_index_intervals",
        "oracle.adapters.landmark_rxr.occurrences:align_subpaths",
        "Discrete identity alignment only, not continuous motion proof"),
}


def describe():
    return [asdict(v) for v in METHODS.values()]


def validate_contract(name, task):
    method = METHODS[name]
    if task.purpose not in method.purposes or task.objective not in method.objectives:
        raise ValueError("Method purpose/objective does not match the task")
    if task.privileges != frozenset(method.privileges):
        raise ValueError("Different privileged information requires a separate declared method")
    return method
