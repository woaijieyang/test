"""Whitelist-only host wiring; preserve RGB if independent sensor metadata/depth fails."""
import time
from case1_runtime.observations import policy_rgb

def _endpoint(envs,index):
    errors=[];depth=stamp=collision=None
    try:
        raw=envs.call_at(index,"graph_raw_depth_endpoint")
    except Exception as error:
        raw=None
        errors.append("graph_raw_depth_endpoint "+type(error).__name__+": "+str(error))
    if raw is not None:
        for key in ("depth","capture_monotonic_ns","collision"):
            try:
                value=raw[key]
                if key=="depth":depth=value
                elif key=="capture_monotonic_ns":stamp=value
                else:collision=value
            except Exception as error:
                errors.append("graph_raw_depth_endpoint."+key+" "+type(error).__name__+": "+str(error))
    return depth,stamp,collision,errors,time.monotonic_ns()

def reset_from_environment(hook,envs,index,observation,scope):
    depth,stamp,_,errors,received=_endpoint(envs,index)
    try:spec=envs.call_at(index,"graph_static_sensor_spec")
    except Exception as error:
        spec=None;errors.append("static_sensor_spec "+type(error).__name__+": "+str(error))
    return hook.reset(scope["episode_uid"],spec,policy_rgb(observation),depth,stamp,
                      identity=scope,sensor_errors=errors,received_monotonic_ns=received,
                      capture_clock_source="endpoint" if stamp is not None else "missing_endpoint")

def capture_from_environment(hook,envs,index,observation,*,action_id,terminal):
    depth,stamp,collision,errors,received=_endpoint(envs,index)
    return hook.capture(policy_rgb(observation),depth,stamp,action_id=action_id,terminal=terminal,
                        collision=collision,acquisition_errors=errors,received_monotonic_ns=received,
                        capture_clock_source="endpoint" if stamp is not None else "missing_endpoint")

def sample_before_environment_step(hook,envs,index,action_id):
    if not getattr(hook,'release4',False) or action_id==0:return
    if action_id not in (1,2,3):raise ValueError('Unknown release4 host primitive')
    try:
        batch=envs.call_at(index,'graph_pose_subframes',dict(action_id=action_id,samples=12))
        if batch.get('sampling_error')=='native_subframes_disabled':
            raise PermissionError('Native subframe sampler disabled by the environment pose policy')
        if (batch.get('action_id')!=action_id or batch.get('samples')!=12 or
            batch.get('restoration_exact')is not True or batch.get('cached_endpoint_unchanged')is not True or len(batch['rows'])!=11):
            raise RuntimeError('Private sampler contract failed')
        hook.pose_subframes(action_id,batch['rows'])
    except Exception as error:
        hook.abort_before_step(action_id,error)
