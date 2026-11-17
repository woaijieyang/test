"""Primitive constraints shared by execution, with independent replay checks."""
import math


def native_violation(adapter, before, after, action, protocol):
    if not adapter.is_navigable(after.position):
        return "offmesh"
    horizontal = math.hypot(after.position[0] - before.position[0], after.position[2] - before.position[2])
    maximum = protocol["forward_m"] if action == 1 else 0.
    if horizontal > maximum + protocol["horizontal_tolerance_m"]:
        return "horizontal_limit"
    if abs(after.position[1] - before.position[1]) > protocol["maximum_vertical_transition_m"]:
        return "vertical_limit"
    if action == 1 and math.dist(before.position, after.position) < protocol["minimum_forward_motion_m"]:
        return "no_forward_progress"
    return None


def orientation_error(a, b):
    # q and -q represent the same rotation; used for evidence comparison only,
    # never to merge planning states.
    dot = abs(sum(x * y for x, y in zip(a, b)))
    norm = math.sqrt(sum(x * x for x in a) * sum(x * x for x in b))
    return 2 * math.acos(min(1., max(-1., dot / norm)))
