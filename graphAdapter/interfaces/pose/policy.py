"""Explicit project execution policy; no simulator APIs or native backend startup."""
SIMULATOR_SOURCE='simulator_ground_truth'
PLANNED_STAGES=frozenset(f'{stage:03d}' for stage in range(7))

def _require_endpoint_source(profile):
    if not isinstance(profile,dict):raise ValueError('Simulator profile must be an object')
    if profile.get('pose_provider')!=SIMULATOR_SOURCE:
        raise ValueError('Current project execution requires explicit SimulatorAdapter; no automatic native fallback')
    if profile.get('stage') not in PLANNED_STAGES or profile.get('simulator_pose_diagnostic') is not True:
        raise ValueError('Explicit planned stage and simulator pose diagnostic/source acknowledgement required')
    if profile.get('pose_sampling','primitive_endpoints')!='primitive_endpoints':
        raise ValueError('Simulator sampling must use primitive endpoints')


def require_simulator_mapping_profile(memory):
    _require_endpoint_source(memory)
    if memory.get('pose_input_mode')!='provider_pose':
        raise ValueError('Simulator mapping requires explicit provider_pose configuration')
    correction=memory.get('background_correction',{})
    if not isinstance(correction,dict) or correction.get('enabled',False) is not False:
        raise ValueError('Simulator mapping cannot enable native background correction')
    return SIMULATOR_SOURCE


def require_simulator_profile(profile):
    _require_endpoint_source(profile)
    memory=profile.get('map_memory',{})
    if not isinstance(memory,dict) or type(memory.get('enabled',False)) is not bool:
        raise ValueError('map_memory must declare a boolean enabled switch')
    if memory.get('enabled'):
        require_simulator_mapping_profile(memory)
        if memory['stage']!=profile['stage']:
            raise ValueError('Active host and mapping stages differ')
    return SIMULATOR_SOURCE
