"""Bounded A* over adapter-provided native transitions.

Standard A* is prior art. Lossless labels are a hypothesis to test against
the archived quantized-key counterexamples, not a claimed new algorithm.
"""
from dataclasses import dataclass
import heapq
import itertools
import math
import time
from typing import Callable, Hashable, Any

from oracle.contracts import Budget, Failure, Proof


@dataclass(frozen=True)
class SearchResult:
    actions: tuple[int, ...]
    states: tuple[Any, ...]
    failure: Failure
    proof: Proof
    expansions: int
    transition_calls: int
    elapsed_seconds: float
    frontier_peak: int
    cost: float | None
    stop_reason: str
    diagnostics: dict[str, int]


def search(initial, *, actions, transition: Callable, key: Callable,
           reached: Callable, heuristic: Callable, action_costs,
           budget: Budget, progress: Callable | None = None,
           priority_weight: float = 1., audit_sink: Callable | None = None,
           soft_duplicate_key: Callable | None = None, soft_duplicate_weight: float = 2.) -> SearchResult:
    """No simulation state mutation is performed by this planner itself.

    A caller-provided heuristic may be inadmissible; this interface makes no
    optimality or physical-unreachability claim. Transition rejection comes
    from a separate feasibility predicate in the adapter/verification layer.
    """
    if (type(priority_weight) not in (int,float) or not math.isfinite(priority_weight)
            or priority_weight < 1.):
        raise ValueError('Explicit finite priority weight >=1 required')
    if soft_duplicate_key is not None and (not callable(soft_duplicate_key)
            or type(soft_duplicate_weight) not in (int,float) or not math.isfinite(soft_duplicate_weight)
            or soft_duplicate_weight<priority_weight):
        raise ValueError('Soft priority must be finite and no smaller than base priority')
    actions = tuple(actions)
    if not actions or len(set(actions)) != len(actions):
        raise ValueError("Explicit unique primitive actions required")
    if set(actions) != set(action_costs) or any(
        not math.isfinite(c) or c <= 0 for c in action_costs.values()
    ):
        raise ValueError("Every primitive needs a finite positive cost")
    started = time.perf_counter()
    counter = itertools.count()
    nodes = [(initial, None, None, 0)]
    h = float(heuristic(initial))
    if not math.isfinite(h) or h < 0:
        raise ValueError("Heuristic must be finite and nonnegative")
    soft_seen=set()
    soft_counts=dict(soft_novel_labels=0,soft_repeated_labels=0)
    def ranked_h(state,value):
        if soft_duplicate_key is None:return priority_weight*value
        hint=soft_duplicate_key(state)
        repeated=hint in soft_seen
        soft_seen.add(hint)
        soft_counts['soft_repeated_labels' if repeated else 'soft_novel_labels']+=1
        return (soft_duplicate_weight if repeated else priority_weight)*value
    queue = [(ranked_h(initial,h), 0.0, next(counter), 0)]
    audit_h = [h] if audit_sink is not None else None
    audit_expanded = [] if audit_sink is not None else None
    # Under an action-count cap, cost alone is not a sufficient dominance
    # relation: a cheaper but longer label can have too little budget left.
    expanded = calls = 0
    peak = 1
    depth_limited = False
    counters = dict(dominated_candidates=0,retired_labels=0,stale_queue_pops=0,
                    maximum_labels_per_key=1)

    def emit():
        if progress is not None:
            progress(expanded, calls, peak)

    emit()
    labels: dict[Hashable, list[tuple[float, int, int]]] = {key(initial): [(0., 0, 0)]}
    active_labels = {0}

    def result(failure, index=None, cost=None, reason='unknown'):
        emit()
        plan, states = [], []
        while index is not None:
            state, parent, action, _ = nodes[index]
            states.append(state)
            if action is not None:
                plan.append(action)
            index = parent
        answer = SearchResult(tuple(reversed(plan)), tuple(reversed(states)),
                            failure, Proof.CANDIDATE_PLAN if failure == Failure.NONE else Proof.NONE, expanded, calls,
                            time.perf_counter() - started, peak, cost, reason,
                            {**counters,'unique_state_keys':len(labels),'generated_labels':len(nodes),
                             **(soft_counts if soft_duplicate_key is not None else {})})
        if audit_sink is not None:
            # Terminal observation only: no extra transition/heuristic calls,
            # and no influence on queue order, dominance or goal checks.
            # Serialization cost is charged by the caller, outside search time.
            audit_sink(dict(nodes=tuple(nodes), heuristics=tuple(audit_h),
                            expanded_indices=tuple(audit_expanded),
                            frontier=tuple(queue), active_indices=tuple(sorted(active_labels))))
        return answer

    while queue:
        if time.perf_counter() - started >= budget.wall_seconds:
            return result(Failure.SEARCH_BUDGET,reason='wall_limit')
        _, cost, _, index = heapq.heappop(queue)
        state, _, _, depth = nodes[index]
        if index not in active_labels:
            counters['stale_queue_pops']+=1
            continue
        if reached(state):
            return result(Failure.NONE, index, cost, 'goal_reached')
        if expanded >= budget.max_expansions:
            return result(Failure.SEARCH_BUDGET,reason='expansion_limit')
        if depth >= budget.max_plan_actions:
            depth_limited = True
            continue
        expanded += 1
        if audit_expanded is not None:
            audit_expanded.append(index)
        emit()
        for action in actions:
            if calls >= budget.max_transition_calls:
                return result(Failure.SEARCH_BUDGET,reason='transition_limit')
            if time.perf_counter() - started >= budget.wall_seconds:
                return result(Failure.SEARCH_BUDGET,reason='wall_limit')
            calls += 1
            emit()
            candidate = transition(state, action)
            if candidate is None:
                continue
            candidate_key = key(candidate)
            candidate_cost = cost + action_costs[action]
            candidate_depth = depth + 1
            prior = labels.get(candidate_key, [])
            if any(g <= candidate_cost and d <= candidate_depth for g, d, _ in prior):
                counters['dominated_candidates']+=1
                continue
            h = float(heuristic(candidate))
            if not math.isfinite(h) or h < 0:
                raise ValueError("Heuristic changed to an invalid value")
            survivors = []
            for g, d, old_index in prior:
                if candidate_cost <= g and candidate_depth <= d:
                    active_labels.discard(old_index)
                    counters['retired_labels']+=1
                else:
                    survivors.append((g, d, old_index))
            new_index = len(nodes)
            survivors.append((candidate_cost, candidate_depth, new_index))
            counters['maximum_labels_per_key']=max(counters['maximum_labels_per_key'],len(survivors))
            labels[candidate_key] = survivors
            active_labels.add(new_index)
            nodes.append((candidate, index, action, candidate_depth))
            if audit_h is not None:
                audit_h.append(h)
            heapq.heappush(queue, (candidate_cost + ranked_h(candidate,h), candidate_cost,
                                  next(counter), new_index))
            peak = max(peak, len(queue))
    return result(Failure.SEARCH_BUDGET if depth_limited else Failure.FRONTIER,
                  reason='plan_action_limit' if depth_limited else 'frontier_exhausted')
