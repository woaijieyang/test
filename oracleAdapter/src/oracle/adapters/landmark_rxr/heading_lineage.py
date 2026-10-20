"""Preserve Landmark heading fields and distinguish them from Guide/CE starts."""
from collections import Counter
import json
import math
from pathlib import Path
from oracle.adapters.landmark_rxr.ledger import canonical_id
from oracle.common.artifacts import digest,write_json


def heading_facts(raw,guide_heading):
    h=raw.get('heading');heads=raw.get('headings',[])
    finite=lambda v:type(v) in (float,int) and math.isfinite(v)
    valid=finite(h) and isinstance(heads,list) and all(finite(x) for x in heads)
    first=heads[0] if isinstance(heads,list) and heads else None
    return {'landmark_heading':h if finite(h) else None,'landmark_heading_source_repr':repr(h),
            'guide_heading':guide_heading,'landmark_headings':[x if finite(x) else None for x in heads] if isinstance(heads,list) else None,
            'headings_finite':valid,'headings_count':len(heads) if isinstance(heads,list) else None,
            'subpath_count':len(raw['sub_paths']),'subinstruction_count':len(raw['sub_instructions']),
            'one_heading_per_subpath':isinstance(heads,list) and len(heads)==len(raw['sub_paths']),
            'header_exactly_equal_to_first_subheading':h==first if finite(h) and finite(first) else None,
            'header_first_subheading_difference_if_radians':abs(math.atan2(math.sin(h-first),math.cos(h-first))) if finite(h) and finite(first) else None,
            'header_exactly_equal_to_guide':h==guide_heading if finite(h) else None,
            'circular_difference_if_both_are_radians':abs(math.atan2(math.sin(h-guide_heading),math.cos(h-guide_heading))) if finite(h) else None,
            'automatic_heading_replacement':False,
            'frame_semantics':'Numeric field accounting only; equality/range does not prove the author collection UI frame convention.'}


def audit(case_root,config,output):
    root=Path(case_root).resolve();output=Path(output).resolve()
    if not output.is_relative_to(root/'outputs/oracleAdapter') or output.exists():raise ValueError('Fresh owned output required')
    heading_run=root/config['guide_heading_run'];summary=json.loads((heading_run/'validation.json').read_text())
    ledger_path=heading_run/'all33954-heading-ledger.json'
    if digest(ledger_path)!=summary['ledger_sha256']:raise ValueError('Guide/CE heading ledger changed')
    guide={r['task_key']:r for r in json.loads(ledger_path.read_text())}
    historical_path=root/config['historical_manifest']
    historical=json.loads(historical_path.read_text())
    historical_tasks={r['task_key']:r for r in historical['tasks']}
    if len(historical['tasks'])!=len(historical_tasks) or set(historical_tasks)!=set(guide):raise ValueError('Historical metadata scope mismatch')
    identity=json.loads((root/config['identity_run']/'validation.json').read_text())
    rows=[];sources=[]
    for source in identity['sources']:
        path=Path(source['path'])
        if not path.name.startswith('LandmarkRxR_'):continue
        if digest(path)!=source['sha256']:raise ValueError('Original Landmark annotation changed')
        for raw in json.loads(path.read_text()):
            key=raw['split']+':'+canonical_id(raw['instruction_id']);original=guide[key]
            if raw['scan']!=original['scene']:raise ValueError('Source identity mismatch')
            rows.append({'task_key':key,'scene':raw['scan'],'landmark_source_sha256':source['sha256'],
                         'guide_source_sha256':original['source_sha256'],'guide_source_line':original['source_line'],
                         'old_manifest_heading':historical_tasks[key].get('heading'),
                         'old_manifest_heading_equals_raw':historical_tasks[key].get('heading')==raw.get('heading'),
                         'guide_to_ce_heading_status':original['status'],**heading_facts(raw,original['heading_radians'])})
        sources.append(source)
    if len(rows)!=config['expected_records'] or len({r['task_key'] for r in rows})!=len(rows) or {r['task_key'] for r in rows}!=set(guide):
        raise ValueError('Full heading lineage coverage mismatch')
    output.mkdir(parents=True,exist_ok=False);write_json(output/'all33954-landmark-heading-lineage.json',rows)
    result={'status':'FULL_HEADING_FIELD_LINEAGE_ACCOUNTED_NOT_FRAME_REPLACEMENT_AUTHORIZATION','records':len(rows),
        'numeric_header_equals_guide':dict(Counter(str(r['header_exactly_equal_to_guide']) for r in rows)),
        'numeric_header_equals_first_subheading':dict(Counter(str(r['header_exactly_equal_to_first_subheading']) for r in rows)),
        'circular_header_guide_equivalent_if_radians':dict(Counter(str(r['circular_difference_if_both_are_radians']<=config['comparison_angle_radians']) if r['circular_difference_if_both_are_radians'] is not None else 'unknown' for r in rows)),
        'circular_header_first_subheading_equivalent_if_radians':dict(Counter(str(r['header_first_subheading_difference_if_radians']<=config['comparison_angle_radians']) if r['header_first_subheading_difference_if_radians'] is not None else 'unknown' for r in rows)),
        'one_heading_per_subpath':dict(Counter(str(r['one_heading_per_subpath']) for r in rows)),
        'all_heading_fields_finite':dict(Counter(str(r['headings_finite']) for r in rows)),
        'old_manifest_heading_equals_raw':dict(Counter(str(r['old_manifest_heading_equals_raw']) for r in rows)),
        'total_subpaths':sum(r['subpath_count'] for r in rows),'total_heading_values':sum(r['headings_count'] or 0 for r in rows),
        'max_circular_difference_if_radians':max((r['circular_difference_if_both_are_radians'] for r in rows if r['circular_difference_if_both_are_radians'] is not None),default=None),
        'sources':sources,'guide_heading_validation_sha256':digest(heading_run/'validation.json'),
        'historical_manifest_sha256':digest(historical_path),
        'ledger_sha256':digest(output/'all33954-landmark-heading-lineage.json'),
        'limits':'Landmark and Guide numeric heading differences are preserved, not automatically labelled annotation errors. Historical manifest comparison checks intended metadata, not every historical executed rotation. Official-demo controls use explicit Guide/CE initial-state lineage and are not full Landmark initial-state evaluation. No original data or gates changed.'}
    write_json(output/'validation.json',result);return result
