"""Bound a suggestion stage's detour; never change goals or feasibility gates."""
import math


class ReferenceProgressGuard:
    def __init__(self, *, max_excess_distance_m, max_nonprogress_actions):
        if (not math.isfinite(max_excess_distance_m) or max_excess_distance_m <= 0
                or type(max_nonprogress_actions) is not int or max_nonprogress_actions < 1):
            raise ValueError('Explicit finite progress policy required')
        self.max_excess_distance_m = max_excess_distance_m
        self.max_nonprogress_actions = max_nonprogress_actions
        self.reference_index = None
        self.best_distance = None
        self.nonprogress_actions = 0

    def check(self, reference_index, before_distance, proposed_distance):
        if (type(reference_index) is not int or reference_index < 1
                or not all(math.isfinite(v) and v >= 0 for v in (before_distance, proposed_distance))):
            raise ValueError('Finite ordered reference distances required')
        if self.reference_index is not None and reference_index < self.reference_index:
            raise ValueError('Reference occurrence moved backwards')
        if reference_index != self.reference_index:
            self.reference_index = reference_index
            self.best_distance = before_distance
            self.nonprogress_actions = 0
        self.best_distance = min(self.best_distance, before_distance)
        if proposed_distance > self.best_distance + self.max_excess_distance_m:
            return 'reference_distance_excursion'
        if proposed_distance < self.best_distance:
            self.best_distance = proposed_distance
            self.nonprogress_actions = 0
        else:
            self.nonprogress_actions += 1
        if self.nonprogress_actions >= self.max_nonprogress_actions:
            return 'reference_progress_stalled'
        return None

    def record(self):
        return dict(reference_index=self.reference_index,best_distance_m=self.best_distance,
                    nonprogress_actions=self.nonprogress_actions)
