"""Exact-ID discrete graph provenance; never supplies a replacement floor point."""
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
import zipfile

from oracle.common.coordinates import matterport_to_habitat
from oracle.common.offline_audit import identity


def graph_index(rows):
    ids = [r['image_id'] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate original viewpoint identity')
    result = {}
    for i, row in enumerate(rows):
        pose = row['pose']
        links = row['unobstructed']
        if (len(pose) != 16 or not all(math.isfinite(x) for x in pose)
                or len(links) != len(rows) or any(type(x) is not bool for x in links)
                or type(row['included']) is not bool):
            raise ValueError('Invalid original pose or adjacency schema')
        result[ids[i]] = dict(
            included=row['included'], source_pose=pose,
            source_camera_xyz=[pose[3], pose[7], pose[11]],
            habitat_camera_xyz=list(matterport_to_habitat([pose[3], pose[7], pose[11]])),
            included_neighbors=[ids[j] for j, clear in enumerate(links)
                                if clear and rows[j]['included']],
            asymmetric_neighbors=[ids[j] for j, clear in enumerate(links)
                                  if clear != rows[j]['unobstructed'][i]],
            height_metadata=row.get('height'),
        )
    return result


def viewpoint_record(scene, identity, original, published, legacy=None):
    node = original.get(identity)
    row = dict(scene=scene, source_viewpoint_id=identity,
               original_same_id_present=node is not None,
               published_same_id_present=identity in published,
               alias_evidence='NOT_ESTABLISHED', replacement_identity=None,
               native_reachability='NOT_TESTED_BY_DISCRETE_GRAPH_AUDIT')
    if node is None:
        row['category'] = 'ABSENT_FROM_FROZEN_ORIGINAL_GRAPH'
        return row
    row.update(original=node)
    row['category'] = ('ORIGINAL_INCLUDED_ID_ABSENT_FROM_PUBLISHED_GRAPH'
                       if node['included'] and identity not in published else
                       'ORIGINAL_EXCLUDED_ID' if not node['included'] else 'SAME_ID_IN_BOTH_GRAPHS')
    row['original_neighbors_present_in_published'] = [n for n in node['included_neighbors'] if n in published]
    # This is only a check of an old camera-axis transform, not camera-to-ground geometry.
    old_camera = None if legacy is None else legacy.get('camera_position')
    row['legacy_camera_max_axis_difference_m'] = (None if old_camera is None else
        max(abs(a-b) for a,b in zip(node['habitat_camera_xyz'], old_camera)))
    if identity in published:
        point = published[identity]
        if len(point) != 3 or not all(math.isfinite(x) for x in point):
            raise ValueError('Invalid published point')
        row['published_position'] = point
        row['camera_to_published_vector_m'] = [b-a for a,b in zip(node['habitat_camera_xyz'], point)]
    return row


def audit(case_root, config_path, output):
    startup=identity()
    root, config_path, output = Path(case_root).resolve(), Path(config_path).resolve(), Path(output).resolve()
    if not output.is_relative_to(root/'outputs/oracleAdapter') or output.exists():
        raise ValueError('Require a new case-owned evidence directory')
    config_raw = config_path.read_bytes(); config = json.loads(config_raw)
    paths = {}
    for key in ('fetch_receipt', 'original_cache', 'published_archive', 'missing_ledger', 'legacy_nodes'):
        path = (root/config[key]).resolve()
        if not path.is_relative_to(root): raise ValueError('Reference input escapes case1')
        paths[key] = path
    receipt_raw = paths['fetch_receipt'].read_bytes(); receipt = json.loads(receipt_raw)
    archive_raw = paths['published_archive'].read_bytes()
    if hashlib.sha256(archive_raw).hexdigest() != config['published_archive_sha256']:
        raise ValueError('Published archive changed')
    if receipt['commit'] != config['original_commit']:
        raise ValueError('Original commit differs')
    original, published, sources = {}, {}, []
    with zipfile.ZipFile(paths['published_archive']) as archive:
        for ref in receipt['records']:
            scene = ref['scene']
            if scene in original: raise ValueError('Duplicate scene')
            raw = (paths['original_cache']/ref['file']).read_bytes()
            blob = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            sha = hashlib.sha256(raw).hexdigest()
            if blob != ref['git_blob_sha1'] or sha != ref['sha256'] or len(raw) != ref['bytes']:
                raise ValueError('Original graph changed: '+scene)
            original[scene] = graph_index(json.loads(raw))
            entry = 'habitat_mp3d_connectivity_graphs/'+scene+'.json'
            pub_raw = archive.read(entry); published[scene] = json.loads(pub_raw)
            sources.append(dict(scene=scene,original_git_blob_sha1=blob,original_sha256=sha,
                                published_member=entry,published_sha256=hashlib.sha256(pub_raw).hexdigest()))
    missing_raw = paths['missing_ledger'].read_bytes(); missing = json.loads(missing_raw)
    legacy_raw = paths['legacy_nodes'].read_bytes(); legacy = json.loads(legacy_raw)['nodes']
    legacy_index = {(r['scene'],r['node']):r for r in legacy}
    keys = [(r['scene'],r['source_viewpoint_id']) for r in missing]
    if len(keys) != config['expected_missing'] or len(set(keys)) != len(keys):
        raise ValueError('Missing viewpoint denominator changed')
    records = [viewpoint_record(s,n,original[s],published[s]['nodes'],legacy_index.get((s,n))) for s,n in keys]
    if any(r['published_same_id_present'] for r in records):
        raise ValueError('Legacy missing identity contradicts actual published archive')
    all_required = [viewpoint_record(r['scene'],r['node'],original[r['scene']],
                    published[r['scene']]['nodes'],r) for r in legacy]
    scene = config['known_edge']['scene']; a,b = config['known_edge']['nodes']
    edges = [dict(edge_id=k,**v) for k,v in published[scene]['edges'].items() if set(v['nodes']) == {a,b}]
    edge = dict(scene=scene,nodes=[a,b],published_edges=edges,
                original_forward_edge=b in original[scene][a]['included_neighbors'],
                original_reverse_edge=a in original[scene][b]['included_neighbors'],
                endpoints=[viewpoint_record(scene,n,original[scene],published[scene]['nodes']) for n in (a,b)],
                interpretation='Discrete adjacency and positions only; not strict native motion evidence')
    summary = dict(status='SOURCE_IDENTITY_AUDITED_NOT_CONTINUOUS_REPAIR',startup=startup,scenes=len(original),
        missing_viewpoints=len(records),categories=dict(Counter(r['category'] for r in records)),
        required_legacy_nodes=len(all_required),
        required_original_absent=sum(not r['original_same_id_present'] for r in all_required),
        required_original_excluded=sum(r.get('original',{}).get('included') is False for r in all_required),
        legacy_camera_exact=sum(r.get('legacy_camera_max_axis_difference_m') == 0 for r in all_required),
        legacy_camera_max_difference_m=max((r.get('legacy_camera_max_axis_difference_m') or 0 for r in all_required),default=0),
        original_asymmetric_arcs=sum(len(n['asymmetric_neighbors']) for g in original.values() for n in g.values()),
        known_edge=dict(original_forward=edge['original_forward_edge'],original_reverse=edge['original_reverse_edge'],published_matches=len(edges)),
        inputs_sha256={k:hashlib.sha256(v).hexdigest() for k,v in dict(config=config_raw,fetch_receipt=receipt_raw,
            published_archive=archive_raw,missing_ledger=missing_raw,legacy_nodes=legacy_raw).items()},
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limits=['No spatial nearest identity substitution; rename/merge provenance remains unknown.',
                'Original camera positions do not establish legal floor positions or body clearance.',
                'Required node set comes from preserved legacy ledger, not new raw annotation extraction.',
                'No original annotation, continuous mapping, navmesh, running task or acceptance gate changed.'])
    output.mkdir(parents=True)
    for name,data in [('viewpoints461.json',records),('required-nodes.json',all_required),('known-edge.json',edge),('sources.json',sources)]:
        (output/name).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    summary['outputs_sha256'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob('*.json')}
    (output/'validation.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    return summary
