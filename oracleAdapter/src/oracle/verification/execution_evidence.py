"""Input-pose and raw execution stream checks, distinct from route replay."""
import json
import math
from pathlib import Path
from oracle.common.artifacts import digest
from oracle.verification.motion import orientation_error


def initial_contract_errors(expected,actual,protocol):
    errors=[]
    if math.dist(expected.position,actual.position)>protocol['maximum_prediction_error_m']:
        errors.append('initial_position_mismatch')
    if orientation_error(expected.quaternion_xyzw,actual.quaternion_xyzw)>protocol['maximum_orientation_error_rad']:
        errors.append('initial_orientation_mismatch')
    return errors


def check_trace_stream(record,path,require_hash=True):
    path=Path(path);sha=digest(path);claimed=record.get('trace_sha256')
    if require_hash and claimed is None:raise ValueError('Producer did not bind the raw trace')
    if claimed is not None and claimed!=sha:raise ValueError('Raw trace digest differs')
    actions=[];positions=[];rotations=[];boundaries=[];origins=[];source_indices=[]
    with path.open(encoding='utf-8') as stream:
        for line_number,line in enumerate(stream,1):
            if not line.strip():raise ValueError('Unexpected empty trace event')
            event=json.loads(line);kind=event.get('kind')
            if kind=='initial':
                if line_number!=1 or positions:raise ValueError('Duplicate or late initialization')
                positions.append(event['position']);rotations.append(event['rotation'])
            elif kind=='action':
                if not positions or event['index']!=len(actions)+1:raise ValueError('Action sequence discontinuity')
                actions.append(event['action']);positions.append(event['position']);rotations.append(event['rotation'])
                origins.append(event.get('action_origin'));source_indices.append(event.get('official_source_action_index'))
            elif kind=='boundary':
                if not positions or event['action_index']!=len(actions):raise ValueError('Boundary moved to a different action state')
                boundaries.append({k:v for k,v in event.items() if k!='kind'})
            else:raise ValueError('Unknown event or hidden reset in execution trace')
    if (actions!=record['actions'] or positions!=record['positions'] or rotations!=record['rotations']
            or boundaries!=record['boundaries']):raise ValueError('Result arrays disagree with raw execution stream')
    if 'action_origins' in record and origins!=record['action_origins']:raise ValueError('Raw action origins differ')
    if 'official_source_action_indices' in record and source_indices!=record['official_source_action_indices']:raise ValueError('Raw source action indices differ')
    return {'trace_sha256':sha,'producer_hash_present':claimed is not None,'actions':len(actions),
            'initial_events':1 if positions else 0,'boundaries':len(boundaries),
            'scope':'Current stream/result consistency; retrospective missing producer hash is not original-time hash attestation'}
