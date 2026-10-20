"""Priority-only occupancy hint inspired by soft duplicate detection.

This is not the paper's subtree-overlap implementation or an equivalence test.
All exact states, cost/depth labels, native transitions and validators remain.
"""
import math


def validate_config(cfg):
    if set(cfg)!={'position_cell_m','yaw_cell_degrees','maximum_priority_weight'}:
        raise ValueError('Explicit soft-priority configuration required; no pruning switch')
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in cfg.values()):
        raise ValueError('Finite positive soft-priority parameters required')
    if cfg['maximum_priority_weight']<1 or cfg['yaw_cell_degrees']>180:
        raise ValueError('Invalid priority hint limits')
    bins=360/cfg['yaw_cell_degrees']
    if abs(round(bins)-bins)>1e-7:raise ValueError('Angular cells must tile360degrees')


def pose_bucket(state,cfg):
    yaw=math.degrees(2*math.atan2(state.quaternion_xyzw[1],state.quaternion_xyzw[3]))%360
    return tuple(round(v/cfg['position_cell_m']) for v in state.position)+(round(yaw/cfg['yaw_cell_degrees'])%round(360/cfg['yaw_cell_degrees']),)
