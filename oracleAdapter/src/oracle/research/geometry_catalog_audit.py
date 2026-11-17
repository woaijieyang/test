"""All-scene schema/byte controls before resuming native tasks; no motion."""
from collections import Counter
import json
from pathlib import Path
import gc
from oracle.common.artifacts import digest,owned_output,write_json,package_sources,freeze_sources
from oracle.common.offline_audit import identity
from oracle.verification.source_scene import SourceScene


def audit(case_root,output):
    startup=identity();root=Path(case_root).resolve();output=owned_output(root,output)
    if output.exists():raise FileExistsError(output)
    path=root/'outputs/landmark-connectivity/native-source-catalog-v1/catalog.json'
    if digest(path)!='6178cf2da73f31ff2cf0be5f53ff9eabf49ce6fba5bb49399c37df51dcf16727':raise ValueError('Frozen geometry catalog changed')
    catalog=json.loads(path.read_text());protocol_path=Path(__file__).resolve().parents[1]/'configs/protocols/current_linear.json'
    protocol=json.loads(protocol_path.read_text());output.mkdir();rows=[]
    for row in catalog['scenes']:
        p=Path(row['receipt_path']);raw=Path(row['native_geometry_path'])
        if not p.resolve().is_relative_to(root) or not raw.resolve().is_relative_to(root):raise ValueError('Geometry receipt/data escapes case')
        if digest(p)!=row['receipt_sha256'] or digest(raw)!=row['native_geometry_sha256']:raise ValueError('Geometry identity differs')
        receipt=json.loads(p.read_text());candidate=SourceScene(p,row['receipt_sha256'],protocol,catalog=row)
        canonical=output/'canonical-controls'/f'{row["scene"]}.json'
        write_json(canonical,{k:row[k] for k in ('native_geometry_path','native_geometry_sha256','scene_sha256')})
        control=SourceScene(canonical,digest(canonical),protocol)
        equal=all(getattr(candidate,k).tobytes()==getattr(control,k).tobytes() for k in ('triangles','low','high'))
        if not equal:raise ValueError('Canonical geometry array control differs')
        rows.append(dict(scene=row['scene'],schema=candidate.receipt_schema,receipt_sha256=digest(p),
            geometry_sha256=digest(raw),scene_sha256=candidate.scene_sha256,
            triangles=len(candidate.triangles),canonical_control_sha256=digest(canonical),arrays_byte_identical=equal))
        del candidate,control;gc.collect()
    if len(rows)!=71 or len({r['scene'] for r in rows})!=71:raise ValueError('All-scene coverage differs')
    _,sources=package_sources();freeze_sources(output,sources)
    result=dict(status='ALL71_NATIVE_GEOMETRY_SCHEMA_AND_BYTE_CONTROLS_PASS_NOT_MOTION',startup=startup,scenes=71,
        schemas=dict(Counter(r['schema'] for r in rows)),records=rows,catalog_sha256=digest(path),protocol_sha256=digest(protocol_path),
        native_actions=0,original_receipts_modified=False,scene_geometry_modified=False,
        limits='Only receipt adaptation and decoded-array identity; does not certify route feasibility or change collision predicates.')
    write_json(output/'validation.json',result);return result
