"""Stable-ID source heading to CE xyzw audit; no target or motion changes."""
from collections import Counter
import gzip
import json
import math
from pathlib import Path

from oracle.adapters.landmark_rxr.ledger import canonical_id
from oracle.common.artifacts import digest,write_json
from oracle.common.coordinates import matterport_to_habitat,habitat_to_matterport,heading_quaternion_xyzw,quaternion_forward,direction_error


def audit(case_root,config,output):
    root=Path(case_root).resolve();output=Path(output).resolve()
    if not output.is_relative_to(root/'outputs/oracleAdapter') or output.exists():raise ValueError('Fresh owned output required')
    identity=root/config['identity_run']
    baseline=json.loads((identity/'validation.json').read_text());identities=json.loads((identity/'all33954-identities.json').read_text())
    wanted={(r['split'],r['instruction_id']):r for r in identities}
    if len(wanted)!=config['expected_records']:raise ValueError('Source scope changed')
    raw_receipt=root/config['raw_guide_source_receipt'];raw_sources=json.loads(raw_receipt.read_text())
    headings={};sources=[]
    for source in raw_sources['files']:
        path=Path(source['path']).resolve()
        if not path.is_relative_to(root/'outputs/oracleAdapter/reference-cache') or digest(path)!=source['sha256']:raise ValueError('Original Guide drift')
        with gzip.open(path,'rt',encoding='utf-8') as stream:
            for lineno,line in enumerate(stream,1):
                if not line.strip():continue
                r=json.loads(line);key=(r['split'],canonical_id(r['instruction_id']))
                if key not in wanted:continue
                known=wanted[key]
                if key in headings or r['scan']!=known['scene'] or canonical_id(r['path_id'])!=known['path_id'] or r['language']!=known['language']:
                    raise ValueError('Ambiguous or incompatible stable source identity')
                headings[key]={'heading_radians':r['heading'],'source_sha256':source['sha256'],'source_line':lineno}
        sources.append({'path':str(path),'sha256':source['sha256']})
    if set(headings)!=set(wanted):raise ValueError('Original Guide heading coverage missing')
    continuous={}
    for source in baseline['sources']:
        path=Path(source['path'])
        if not path.name.endswith('_guide.json.gz'):continue
        if digest(path)!=source['sha256']:raise ValueError('CE annotation drift')
        with gzip.open(path,'rt') as stream:episodes=json.load(stream)['episodes']
        for episode in episodes:
            key=(path.parent.name,canonical_id(episode['instruction']['instruction_id']))
            if key not in wanted:continue
            if key in continuous:raise ValueError('Duplicate CE instruction identity')
            continuous[key]={'quaternion_xyzw':episode['start_rotation'],'start_position':episode['start_position'],
                             'scene':Path(episode['scene_id']).parent.name,'path_id':canonical_id(episode['trajectory_id']),
                             'source_sha256':source['sha256'],'episode_id':canonical_id(episode['episode_id'])}
        del episodes
        sources.append({'path':str(path),'sha256':source['sha256']})
    import habitat_sim
    native_axes={'up':list(map(float,habitat_sim.geo.UP)),'front':list(map(float,habitat_sim.geo.FRONT))}
    if native_axes!={'up':[0.,1.,0.],'front':[0.,0.,-1.]}:raise ValueError('Installed native axes disagree with documented convention')
    rows=[]
    for key,known in sorted(wanted.items()):
        raw=headings[key];heading=raw['heading_radians']
        candidate=heading_quaternion_xyzw(heading)
        source_direction=(math.sin(heading),math.cos(heading),0.)
        rotated=matterport_to_habitat(source_direction)
        round_trip=habitat_to_matterport(rotated)
        if round_trip!=source_direction:raise ValueError('Axis round trip failed')
        row={'task_key':known['task_key'],'scene':known['scene'],**raw,
             'heading_derived_quaternion_xyzw':candidate,'source_forward':source_direction,'rotated_forward':rotated,
             'synthetic_rotation_consistency_error_rad':direction_error(rotated,quaternion_forward(candidate)),
             'camera_height_offset_applied':False,'annotations_modified':False}
        ce=continuous.get(key)
        if ce is None:
            row['status']='SOURCE_HEADING_ACCOUNTED_NO_CE_ORIENTATION'
        else:
            if ce['scene']!=known['scene'] or ce['path_id']!=known['path_id']:raise ValueError('CE correspondence changed')
            error=direction_error(rotated,quaternion_forward(ce['quaternion_xyzw']))
            row.update(ce=ce,ce_forward_error_rad=error,
                       status='CE_HEADING_CONVENTION_MATCH' if error<=config['comparison_angle_radians'] else 'CE_HEADING_DIFFERENCE_REQUIRES_SOURCE_EXPLANATION')
        rows.append(row)
    output.mkdir(parents=True,exist_ok=False);write_json(output/'all33954-heading-ledger.json',rows)
    summary={'status':'COORDINATE_HEADING_ACCOUNTING_NOT_CAMERA_FLOOR_OR_MOTION_ACCEPTANCE','records':len(rows),
             'counts':dict(Counter(r['status'] for r in rows)),
             'max_matched_CE_direction_error_rad':max((r['ce_forward_error_rad'] for r in rows if 'ce_forward_error_rad' in r),default=None),
             'native_runtime_version':habitat_sim.__version__,'installed_axes':native_axes,
             'sources':sources,'raw_receipt_sha256':digest(raw_receipt),
             'ledger_sha256':digest(output/'all33954-heading-ledger.json'),
             'limits':'Checks stable-ID headings and a right-handed axis rotation with no fitted offsets/sign changes. Does not establish camera extrinsic matrix direction, source camera-to-floor offsets, missing CE paths or physical reachability.'}
    write_json(output/'validation.json',summary);return summary
