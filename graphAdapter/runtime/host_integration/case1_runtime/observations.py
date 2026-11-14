"""Actual policy observation boundary: access only RGB without inspecting other fields."""
def policy_rgb(observation):
    return observation["rgb"]

def policy_observations(observations):
    return [{"rgb":policy_rgb(observation)} for observation in observations]


def graph_hook_enabled(environment):
    return environment.get('CASE2_HOOK_MODE','off')=='on'


def native_subframes_enabled(environment):
    """Authorize the legacy sampler at the VectorEnv receiver before accessing Habitat."""
    if not graph_hook_enabled(environment):return False
    import json
    from pathlib import Path
    profile_path=environment.get('CASE2_POSE_PROFILE')
    if not profile_path:return False
    try:
        with Path(profile_path).open(encoding='utf-8') as stream:profile=json.load(stream)
    except (OSError,ValueError):return False
    # Native release4 profiles predate the explicit provider field.
    if not isinstance(profile,dict):return False
    memory=profile.get('map_memory',{})
    if not isinstance(memory,dict) or type(memory.get('enabled',False)) is not bool:return False
    if memory.get('enabled') and (memory.get('pose_provider','cuvslam_rtabmap_rgbd')!='cuvslam_rtabmap_rgbd'
            or memory.get('pose_input_mode')=='provider_pose' or memory.get('simulator_pose_diagnostic',False) is not False):
        return False
    return (profile.get('pose_sampling')=='release4_12'
            and profile.get('pose_provider','cuvslam_rtabmap_rgbd')=='cuvslam_rtabmap_rgbd'
            and profile.get('simulator_pose_diagnostic',False) is False)


def resolve_graph_hook_switch(environment):
    """The master switch is authoritative; profile presence never enables it."""
    mode=environment.get('CASE2_HOOK_MODE','off')
    if mode not in ('on','off'):raise ValueError('CASE2_HOOK_MODE must be explicit on or off')
    inherited_profile=bool(environment.get('CASE2_POSE_PROFILE'))
    ignored=[]
    if not graph_hook_enabled(environment):
        for key in ('CASE2_POSE_PROFILE','POSEADAPTER_BROKER','POSEADAPTER_BROKER_PID','GRAPH_MEMORY_BROKER','GRAPH_MEMORY_BROKER_PID'):
            if key in environment:ignored.append(key);environment.pop(key)
        path=None
    else:
        path=environment.get('CASE2_POSE_PROFILE')
        if not isinstance(path,str) or not path:raise ValueError('Enabled GraphAdapter requires an explicit profile')
    environment['CASE2_HOOK_MODE']=mode
    return path,dict(effective_mode=mode,inherited_profile_present=inherited_profile,
                     ignored_graph_environment_keys=ignored)

