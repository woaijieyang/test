"""Experimental conservative collision response; not installed in any formal runtime.

Only accepts the original native endpoint or returns the unchanged start on a
verified collision/gate violation. It never invents an intermediate pose and
never reads instruction, goal, reference path, score, or model output.
"""
import math


class SourceCollisionFilter:
    def __init__(self, native_filter, is_navigable, source_sweep):
        self.native_filter = native_filter
        self.is_navigable = is_navigable
        self.source_sweep = source_sweep
        self.events = []

    def __call__(self, start, requested):
        before = [float(x) for x in start]
        if not all(math.isfinite(x) for x in before) or not self.is_navigable(start):
            raise RuntimeError('invalid_initial_native_state')
        if self.source_sweep(before, before) is not None:
            raise RuntimeError('invalid_initial_source_body')
        proposed = self.native_filter(start, requested)
        candidate = [float(x) for x in proposed]
        reason = None
        contact = None
        if not all(math.isfinite(x) for x in candidate):
            reason = 'native_nonfinite'
        elif not self.is_navigable(proposed):
            reason = 'native_offmesh'
        elif abs(candidate[1] - before[1]) > .5:
            reason = 'native_vertical_gate'
        else:
            contact = self.source_sweep(before, candidate)
            if contact is not None:
                reason = 'exact_source_swept_contact'
        self.events.append({'before': before, 'requested': [float(x) for x in requested],
                            'native_candidate': candidate, 'rejected_reason': reason,
                            'source_contact': contact})
        return start if reason is not None else proposed

