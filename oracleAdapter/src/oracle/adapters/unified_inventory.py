"""Complete identity-bound input inventory; no navigation or new coordinates.

The output is deliberately not an executable manifest. The full-run compiler
must bind its frozen source, method selection, native preflight and budget.
"""
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path

from oracle.adapters.landmark_rxr.ledger import canonical_id
from oracle.adapters.landmark_rxr.occurrences import align_with_source_connectors
from oracle.common.artifacts import content_digest,digest,write_json
from oracle.common.coordinates import heading_quaternion_xyzw
from oracle.verification.motion import orientation_error


def finite_point(p):
    return isinstance(p,(list,tuple)) and len(p)==3 and all(type(x) in (int,float) and math.isfinite(x) for x in p)


def pose_relation(task,source,position_tolerance,angle_tolerance):
    if source is None:return {'status':'NO_MATCHED_OFFICIAL_CE_EPISODE','numeric_initial_pose_match':False}
    if not task['targets'] or not finite_point(task['targets'][0]):
        return {'status':'SOURCE_MAPPING_HAS_NO_FINITE_INITIAL_POSITION','numeric_initial_pose_match':False}
    position=math.dist(task['targets'][0],source['start_position'])
    angle=orientation_error(task['start_rotation'],source['quaternion_xyzw'])
    same=position<=position_tolerance and angle<=angle_tolerance
    return {'status':'POSE_NUMERICALLY_MATCHED_REFERENCE_STILL_REQUIRES_NATIVE_VALIDATION' if same else 'OFFICIAL_INITIAL_POSE_DIFFERS_DO_NOT_OVERWRITE_TASK',
            'numeric_initial_pose_match':same,'position_difference_m':position,'rotation_difference_rad':angle,
            'source_episode_id':source.get('episode_id'),'source_annotation_sha256':source.get('source_sha256'),
            'scope':'Availability/pose accounting only, not equivalence of dynamics or adoption of a cached PASS'}


def landmark_template(raw,legacy):
    key=raw['split']+':'+canonical_id(raw['instruction_id'])
    if (legacy['task_key']!=key or legacy['scene']!=raw['scan'] or legacy['heading']!=raw['heading']
        or legacy['original_viewpoint_path']!=raw['path']):raise ValueError('Legacy mapping changed source identity/heading/path')
    if len(legacy['targets'])!=len(raw['path']):raise ValueError('Reference target cardinality changed')
    alignment=align_with_source_connectors(raw['path'],raw['sub_paths'])
    if alignment.status not in {'EXACT_ORDERED_OCCURRENCES','ORDERED_WITH_EXPLICIT_SOURCE_CONNECTORS'}:
        raise ValueError('Source occurrences are not uniquely accounted')
    if len(raw['sub_paths'])!=len(raw['sub_instructions']) or len(raw['headings'])!=len(raw['sub_paths']):
        raise ValueError('Lost source subinstruction/heading')
    segments=[{'index':i,'start':a,'end':b,'heading':raw['headings'][i],
               'instruction_sha256':content_digest(raw['sub_instructions'][i])} for i,(a,b) in enumerate(alignment.intervals)]
    return {'task_key':key,'dataset':'landmark_rxr','split':raw['split'],'language':raw['language'],
        'instruction_id':canonical_id(raw['instruction_id']),'path_id':canonical_id(raw['path_id']),
        'scene':raw['scan'],'targets':legacy['targets'],'start_rotation':list(heading_quaternion_xyzw(raw['heading'])),
        'raw_heading':raw['heading'],'raw_subpath_headings':raw['headings'],
        'initial_pose_source':'Original Landmark heading, not substituted Guide/CE heading',
        'original_viewpoint_path':raw['path'],'source_record_sha256':content_digest(raw),
        'source_record_hash_encoding':'canonical sorted compact JSON, ensure_ascii=True',
        'legacy_source_record_sha256':legacy['source_record_sha256'],'legacy_static_errors':legacy['static_errors'],
        'target_scope':'all_original_reference_occurrences_including_landmark_boundaries',
        'landmark_target_indices':[end for _,end in alignment.intervals],
        'segments':segments,'source_occurrence_alignment':asdict(alignment),
        'coordinates_complete':all(finite_point(p) for p in legacy['targets']),
        'purpose':'landmark_order_execution','objective':'visit_landmark_occurrences_in_order',
        'scope_note':'Stronger supplied full-reference sequence, not only annotated landmark endpoints or original paper A metrics',
        'privileges':['true_pose','navigation_mesh','goal','reference_path','source_geometry','landmark_annotations']}


def audit(case_root,config,output):
    root=Path(case_root).resolve();output=Path(output).resolve()
    if not output.is_relative_to(root/'outputs/oracleAdapter') or output.exists():raise ValueError('Fresh owned inventory required')
    ep_run=root/config['endpoint_run'];ep_m=json.loads((ep_run/'manifest.json').read_text());ep_v=json.loads((ep_run/'validation.json').read_text())
    ep_manifest_sha=digest(ep_run/'manifest.json')
    if not ep_v['coverage_complete'] or ep_v['manifest_sha256']!=ep_manifest_sha:raise ValueError('Endpoint source receipt mismatch')
    lm_path=root/config['landmark_manifest'];lm=json.loads(lm_path.read_text());legacy={t['task_key']:t for t in lm['tasks']}
    lm_manifest_sha=digest(lm_path)
    identity_root=root/config['identity_run'];identity=json.loads((identity_root/'validation.json').read_text())
    heading_root=root/config['heading_run'];heading_v=json.loads((heading_root/'validation.json').read_text())
    heading_path=heading_root/'all33954-heading-ledger.json'
    if digest(heading_path)!=heading_v['ledger_sha256']:raise ValueError('Heading correspondence changed')
    ce={r['task_key']:r.get('ce') for r in json.loads(heading_path.read_text())}
    if len(legacy)!=config['expected']['landmark_rxr'] or len(legacy)!=len(lm['tasks']):raise ValueError('Landmark metadata denominator mismatch')
    catalog=root/config['geometry_catalog'];catalog_sha=digest(catalog)
    scenes={r['scene'] for r in json.loads(catalog.read_text())['scenes']}
    protocol=json.loads((Path(__file__).resolve().parents[1]/config['protocol_config']).read_text())
    for manifest in (ep_m,lm):
        if digest(manifest['profile_path'])!=manifest['profile_sha256']:raise ValueError('Frozen profile changed')
    output.mkdir(parents=True,exist_ok=False);partial=output/'tasks.partial.jsonl';index=[];seen=set();counts=Counter();availability=Counter();relations=Counter();raw_sources=[]
    with partial.open('xb') as stream:
        def emit(task,profile,source):
            key=task['task_key']
            if key in seen:raise ValueError('Duplicate input identity')
            seen.add(key);task.update(profile_path=profile['profile_path'],profile_sha256=profile['profile_sha256'],
                geometry_catalog_sha256=catalog_sha,source_binding=source,
                inventory_scope='Unmodified mapping/annotation source; native static and motion gates not yet run',
                execution_source_binding_pending=True)
            task['geometry_catalog_present']=task['scene'] in scenes
            coordinates=bool(task['targets']) and task.get('coordinates_complete',all(finite_point(p) for p in task['targets']))
            task['coordinates_complete']=coordinates
            task['reference_action_pose_relation']=pose_relation(task,task.pop('_ce',None),protocol['maximum_prediction_error_m'],protocol['maximum_orientation_error_rad'])
            if task['dataset']=='r2r':task['reference_action_pose_relation']={'status':'R2R_ACTION_PRIOR_NOT_CONFIGURED_REFERENCE_TARGETS_RETAINED','numeric_initial_pose_match':False}
            status='INPUT_COORDINATES_AVAILABLE_PENDING_NATIVE_GATES' if coordinates and task['geometry_catalog_present'] else 'INPUT_INCOMPLETE_PRESERVED'
            task['input_status']=status;encoded=(json.dumps(task,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode()
            offset=stream.tell();stream.write(encoded)
            index.append({'task_key':key,'dataset':task['dataset'],'offset':offset,'bytes':len(encoded),'sha256':hashlib.sha256(encoded).hexdigest(),'input_status':status})
            counts[task['dataset']]+=1;availability[task['dataset']+':'+status]+=1;relations[task['dataset']+':'+task['reference_action_pose_relation']['status']]+=1
        for row in ep_v['results']:
            key=row['task_key'];p=ep_run/'inputs'/(hashlib.sha256(key.encode()).hexdigest()[:24]+'.json');old=json.loads(p.read_text());parts=key.split('|')
            if old['task_key']!=key or old['dataset']!=parts[0]:raise ValueError('Endpoint task identity mismatch')
            task={**old,'split':parts[1],'language':parts[2],'episode_id':parts[4],'instruction_id':None if parts[5]=='-' else parts[5],
                  'initial_pose_source':'Frozen endpoint115 source input, unchanged',
                  'target_scope':'ordered_endpoint115_reference_targets', 'purpose':'reference_execution','objective':'visit_reference_in_order',
                  'privileges':['true_pose','navigation_mesh','goal','reference_path','source_geometry']}
            task['_ce']=ce.get(parts[1]+':'+parts[5]) if parts[0]=='rxr' else None
            emit(task,ep_m,{'path':str(p),'sha256':digest(p),'manifest_sha256':ep_manifest_sha})
        for source in identity['sources']:
            p=Path(source['path'])
            if not p.name.startswith('LandmarkRxR_'):continue
            if digest(p)!=source['sha256']:raise ValueError('Original Landmark source changed')
            raw_sources.append(source)
            for raw in json.loads(p.read_text()):
                key=raw['split']+':'+canonical_id(raw['instruction_id']);task=landmark_template(raw,legacy[key]);task['_ce']=ce[key]
                emit(task,lm,{'original_annotation':str(p),'original_annotation_sha256':source['sha256'],
                              'legacy_mapping_manifest':str(lm_path),'legacy_mapping_manifest_sha256':lm_manifest_sha,
                              'legacy_mapping_record_sha256':content_digest(legacy[key])})
        stream.flush();os.fsync(stream.fileno())
    if dict(counts)!=config['expected'] or len(index)!=sum(config['expected'].values()):raise ValueError('Complete expected denominator mismatch')
    final=output/'tasks.jsonl';partial.rename(final)
    write_json(output/'index.json',index)
    summary={'status':'FULL_INPUT_INVENTORY_NOT_NATIVE_VALIDATION','records':len(index),'datasets':dict(counts),
        'input_availability':dict(availability),'reference_action_pose_relations':dict(relations),
        'all_records_retained':True,'native_actions':0,'original_data_modified':False,
        'targets_file_sha256':digest(final),'index_sha256':digest(output/'index.json'),
        'endpoint_manifest_sha256':ep_manifest_sha,'landmark_manifest_sha256':lm_manifest_sha,
        'original_landmark_sources':raw_sources,'geometry_catalog_sha256':catalog_sha,
        'limits':'No static failure is dropped or converted to PASS. Existing target coordinates remain unchanged. Landmark raw heading is preserved; Guide pose differences are only accounted. Full static/motion/trace/replay gates and final method/source binding remain required.'}
    write_json(output/'validation.json',summary);return summary
