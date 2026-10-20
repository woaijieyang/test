"""Reconstruct ordinal CE reference provenance without selecting new target points.

Stable episode identity plus equal path length supports an ordinal correspondence
hypothesis. CE references do not carry viewpoint IDs; preserve that limitation.
"""
from collections import Counter,defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path

from oracle.common.offline_audit import identity
from .ledger import canonical_id
from .occurrences import align_with_source_connectors


def correspond(raw,ce):
    key=raw['split']+':'+canonical_id(raw['instruction_id'])
    if ce is None:return dict(task_key=key,status='NO_MATCHED_CE_IDENTITY',occurrences=[])
    if (raw['split']!=ce['split'] or canonical_id(raw['instruction_id'])!=canonical_id(ce['instruction_id'])
        or canonical_id(raw['path_id'])!=canonical_id(ce['path_id'])
        or raw['scan']!=ce['scene'] or raw['language']!=ce['language']):
        return dict(task_key=key,status='IDENTITY_MISMATCH',occurrences=[])
    if len(raw['path'])!=len(ce['reference_path']):
        return dict(task_key=key,status='REFERENCE_LENGTH_MISMATCH',occurrences=[])
    points=ce['reference_path']
    if any(len(p)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) for x in p) for p in points):
        return dict(task_key=key,status='NONFINITE_OR_INVALID_REFERENCE',occurrences=[])
    alignment=align_with_source_connectors(raw['path'],raw['sub_paths'])
    return dict(task_key=key,status='IDENTITY_AND_ORDINAL_REFERENCE_ACCOUNTED',
        episode_id=canonical_id(ce['episode_id']),scene=raw['scan'],path_id=canonical_id(raw['path_id']),
        source_alignment=alignment.status,subpath_intervals=[list(x) for x in alignment.intervals],
        occurrences=[dict(index=i,viewpoint_id=n,position=p) for i,(n,p) in enumerate(zip(raw['path'],points))],
        repeated_ids=len(raw['path'])-len(set(raw['path'])),
        consecutive_zero_length=sum(a==b for a,b in zip(points,points[1:])),
        semantic_limit='Ordinal correspondence; CE reference positions lack explicit viewpoint IDs and per-node conversion receipts')


def audit(case_root,output):
    startup=identity();root=Path(case_root).resolve();output=Path(output).resolve()
    if output.exists() or not output.is_relative_to(root/'outputs/oracleAdapter'):
        raise ValueError('New case-owned evidence directory required')
    cache=root/'outputs/oracleAdapter/reference-cache/graph-audit-inputs'
    rawpath=cache/'raw-landmark-paths.json.gz';cepath=cache/'ce-reference-projection.json.gz'
    raw=json.loads(gzip.decompress(rawpath.read_bytes()));ce=json.loads(gzip.decompress(cepath.read_bytes()))
    lookup={}
    for row in ce['records']:
        key=row['split']+':'+canonical_id(row['instruction_id'])
        if key in lookup:raise ValueError('Ambiguous CE identity')
        lookup[key]=row
    oldpath=cache/'native-mapping.json';old=json.loads(oldpath.read_bytes())
    old_nodes={(r['scene'],r['node']):r for r in old['nodes']}
    missingpath=cache/'viewpoints461.json';missing=json.loads(missingpath.read_bytes())
    missing_ids={(r['scene'],r['source_viewpoint_id']) for r in missing}
    counts=Counter();nodes=defaultdict(dict);missing_provenance=defaultdict(list);records=[];keys=set()
    for row in raw['records']:
        key=row['split']+':'+canonical_id(row['instruction_id'])
        if key in keys:raise ValueError('Duplicate raw identity')
        keys.add(key);rec=correspond(row,lookup.get(key));counts[rec['status']]+=1
        for occurrence in rec['occurrences']:
            node=(row['scan'],occurrence['viewpoint_id']);point=tuple(occurrence['position'])
            prov=dict(task_key=key,episode_id=rec['episode_id'],reference_index=occurrence['index'],position=list(point))
            slot=nodes[node].setdefault(point,dict(first_source=prov,occurrence_count=0));slot['occurrence_count']+=1
            if node in missing_ids:missing_provenance[node].append(prov)
        records.append(rec)
    if len(records)!=33954:raise ValueError('Landmark denominator changed')
    compared=[]
    for key,groups in sorted(nodes.items()):
        prior={tuple(p) for p in old_nodes.get(key,{}).get('native_candidates',[])}
        actual=set(groups)
        compared.append(dict(scene=key[0],viewpoint_id=key[1],distinct_official_ordinal_positions=len(actual),
            prior_native_candidates=len(prior),all_positions_exactly_match_prior=actual==prior,
            new_positions_not_in_prior=[list(p) for p in sorted(actual-prior)],
            prior_positions_not_reconstructed=[list(p) for p in sorted(prior-actual)],
            position_sources=[dict(position=list(p),**e) for p,e in groups.items()]))
    missing_records=[]
    for key in sorted(missing_ids):
        missing_records.append(dict(scene=key[0],viewpoint_id=key[1],
            source_type='STABLE_IDENTITY_PLUS_ORDERED_REFERENCE_INDEX' if key in nodes else 'NO_MATCHED_CE_REFERENCE_OCCURRENCE',
            distinct_positions=len(nodes[key]) if key in nodes else 0,
            occurrences=missing_provenance[key],adopted_new_target=False))
    summary=dict(status='CONTINUOUS_REFERENCE_LINEAGE_AUDIT_NOT_MAPPING_OR_MOTION_ACCEPTANCE',startup=startup,
        records=len(records),counts=dict(counts),official_reference_nodes=len(nodes),
        exact_prior_node_sets=sum(r['all_positions_exactly_match_prior'] for r in compared),
        nodes_with_multiple_positions=sum(r['distinct_official_ordinal_positions']>1 for r in compared),
        prior_nodes_not_reconstructed=len(set(old_nodes)-set(nodes)),
        newly_reconstructed_nodes=len(set(nodes)-set(old_nodes)),
        missing461_with_reference=sum(r['distinct_positions']>0 for r in missing_records),
        missing461_without_reference=sum(r['distinct_positions']==0 for r in missing_records),
        repeated_id_tasks=sum(r.get('repeated_ids',0)>0 for r in records),
        tasks_with_zero_length_reference_segments=sum(r.get('consecutive_zero_length',0)>0 for r in records),
        raw_sources=raw['sources'],ce_sources=ce['sources'],
        inputs_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [rawpath,cepath,oldpath,missingpath]},
        limits=['CE does not embed original viewpoint ID per reference coordinate; equal length and stable identities do not supply missing conversion code.',
                'No nearest-point matching, new coordinate selection, navigation, resets or geometry changes.',
                'A zero-length continuous reference does not delete the corresponding source occurrences or instructions.',
                'Native candidate equality is a provenance consistency check, not body feasibility or physical identity proof.'])
    output.mkdir(parents=True)
    for name,data in [('all33954-reference-lineage.json',records),('all-official-node-sources.json',compared),('viewpoints461-reference-sources.json',missing_records)]:
        (output/name).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    summary['outputs_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob('*.json')}
    (output/'validation.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    return summary
