"""Explicit task, privilege, action, budget and proof contracts."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class Purpose(str, Enum):
    GOAL = "goal_navigation"
    REFERENCE = "reference_execution"
    LANDMARK = "landmark_order_alignment"
    LANDMARK_EXECUTION = "landmark_order_execution"
    EXPERT = "expert_action_generation"
    FEASIBILITY = "feasibility_verification"


class Privilege(str, Enum):
    OBSERVATION = "current_observation"
    HISTORY = "observation_history"
    POSE = "true_pose"
    MAP = "global_map"
    NAVMESH = "navigation_mesh"
    GOAL = "goal"
    REFERENCE = "reference_path"
    ACTIONS = "official_actions"
    LANDMARK = "landmark_annotations"
    GEOMETRY = "source_geometry"


class Objective(str, Enum):
    TRANSITION_CHECK = "validate_native_transition"
    GOAL_ONLY = "reach_goal_only"
    REFERENCE_ORDER = "visit_reference_in_order"
    LANDMARK_ORDER = "visit_landmark_occurrences_in_order"
    RECOVER_REFERENCE = "recover_to_reference"


class Failure(str, Enum):
    NONE = "none"
    IDENTITY_MISSING = "identity_or_adaptation_missing"
    TOPOLOGY = "topology_mapping_error"
    NATIVE_ACTION = "native_action_illegal"
    SOURCE_CONTACT = "source_geometry_contact"
    SEARCH_BUDGET = "search_budget_exhausted"
    FRONTIER = "search_frontier_exhausted"
    INFRASTRUCTURE = "infrastructure_error"
    UNKNOWN = "unknown"


class Proof(str, Enum):
    NONE = "no_route_proof"
    CANDIDATE_PLAN = "candidate_action_plan_not_execution_proof"
    NATIVE_TRACE = "executed_native_trace_not_source_geometry_proof"
    VERIFIED_TRACE = "executed_and_verified_trace_under_named_protocol"


@dataclass(frozen=True)
class TaskContract:
    task_key: str
    purpose: Purpose
    objective: Objective
    privileges: frozenset[Privilege]
    protocol_id: str
    task_sha256: str
    reset_policy: str

    def to_record(self):
        """Canonical evidence encoding; immutable privilege sets stay explicit."""
        return {"task_key": self.task_key, "purpose": self.purpose.value,
                "objective": self.objective.value,
                "privileges": sorted(p.value for p in self.privileges),
                "protocol_id": self.protocol_id, "task_sha256": self.task_sha256,
                "reset_policy": self.reset_policy}

    def __post_init__(self):
        if not isinstance(self.purpose, Purpose) or not isinstance(self.objective, Objective):
            raise ValueError("Purpose and objective must be explicit enum values")
        if any(not isinstance(p, Privilege) for p in self.privileges):
            raise ValueError("Privileges must be explicit enum values")
        if not self.task_key or not self.protocol_id or len(self.task_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.task_sha256):
            raise ValueError("Task identity and explicit protocol are required")
        if self.reset_policy not in {"initial_only", "paper_reinitialization_diagnostic"}:
            raise ValueError("Unknown reset policy")
        if self.purpose == Purpose.GOAL and self.objective != Objective.GOAL_ONLY:
            raise ValueError("A goal-only teacher cannot claim reference fidelity")
        if self.objective == Objective.LANDMARK_ORDER and Privilege.LANDMARK not in self.privileges:
            raise ValueError("Ordered landmarks require explicit annotation privilege")


@dataclass(frozen=True)
class MotionContract:
    body_height_m: float
    body_radius_m: float
    forward_m: float
    turn_degrees: float
    goal_radius_m: float
    acceptance_protocol: str
    allow_sliding: bool

    def __post_init__(self):
        numbers = (self.body_height_m, self.body_radius_m, self.forward_m,
                   self.turn_degrees, self.goal_radius_m)
        if any(not math.isfinite(x) or x <= 0 for x in numbers):
            raise ValueError("Motion parameters must be finite and positive")
        if not self.acceptance_protocol:
            raise ValueError("No implicit physical verification protocol")
        if type(self.allow_sliding) is not bool:
            raise ValueError("Sliding behavior must be explicitly declared")


@dataclass(frozen=True)
class Budget:
    max_expansions: int
    max_transition_calls: int
    max_plan_actions: int
    wall_seconds: float

    def __post_init__(self):
        if min(self.max_expansions, self.max_transition_calls, self.max_plan_actions) <= 0:
            raise ValueError("Budgets must be positive")
        if not math.isfinite(self.wall_seconds) or self.wall_seconds <= 0:
            raise ValueError("Finite wall budget required")
