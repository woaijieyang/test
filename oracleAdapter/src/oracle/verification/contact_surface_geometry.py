"""Read-only triangle/foot interpretation; never changes collision acceptance."""
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import struct
import time
from oracle.common.artifacts import digest,owned_output,write_json,package_sources,freeze_sources


def describe_triangle(triangle,foot):
    if len(triangle)!=3 or any(len(p)!=3 for p in [*triangle,foot]):raise ValueError('xyz triangle and foot required')
    if not all(math.isfinite(v) for p in [*triangle,foot] for v in p):raise ValueError('Finite inputs required')
    a,b,c=[[Fraction(float(v)) for v in p] for p in triangle];f=[Fraction(float(v)) for v in foot]
    u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
    n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
    norm=math.sqrt(sum(float(x)**2 for x in n))
    if norm==0:raise ValueError('Degenerate source triangle')
    normal=[float(x)/norm for x in n];bary=None;gap=None;inside=None
    den=u[0]*v[2]-u[2]*v[0]
    if den:
        dx,dz=f[0]-a[0],f[2]-a[2]
        beta=(dx*v[2]-dz*v[0])/den;gamma=(u[0]*dz-u[2]*dx)/den;alpha=1-beta-gamma
        bary=[alpha,beta,gamma];gap=sum(w*p[1] for w,p in zip(bary,[a,b,c]))-f[1];inside=all(0<=x<=1 for x in bary)
    return dict(normal_xyz=normal,slope_degrees=math.degrees(math.acos(min(1.,abs(normal[1])))),
        triangle_y_range_m=[min(p[1] for p in triangle),max(p[1] for p in triangle)],
        plane_height_at_center_minus_foot_m=float(gap) if gap is not None else None,
        plane_height_gap_exact=[gap.numerator,gap.denominator] if gap is not None else None,
        center_projection_inside_triangle=inside,
        center_barycentric_exact=[[v.numerator,v.denominator] for v in bary] if bary is not None else None,
        legal_support_proven=False,meaning='Plane orientation and exact projected barycentrics only; not support semantics, floor labeling or a replacement body test.')


def run(case_root,output,all209=False):
    import resource,signal
    if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected read-only source access required')
    resource.setrlimit(resource.RLIMIT_CPU,(119,120))
    def expired(*_):raise TimeoutError('Read-only120second wall cap')
    signal.signal(signal.SIGALRM,expired);signal.alarm(120)
    started=time.process_time();root=Path(case_root).resolve();out=owned_output(root,output);package,sources=package_sources()
    cfg_path=package/('configs/experiments/contact_surface_geometry209_v1.json' if all209 else 'configs/experiments/contact_surface_geometry_v1.json');cfg=json.loads(cfg_path.read_text())
    parent=root/cfg['parent_run'];assert digest(parent/'manifest.json')==cfg['parent_manifest_sha256']
    catalog_path=root/cfg['catalog'];assert digest(catalog_path)==cfg['catalog_sha256']
    catalog={r['scene']:r for r in json.loads(catalog_path.read_text())['scenes']}
    spec=root/cfg['contacts'];cases=json.loads(spec.read_text());assert len(cases)==cfg.get('expected_contacts',7) and len({x['scene'] for x in cases})==7
    grouped=parent/'grouped-report';gr=json.loads((grouped/'validation.json').read_text());assert digest(grouped/'task-costs.json')==gr['outputs_sha256']['task-costs.json']
    results={x['task_key']:x for x in json.loads((grouped/'task-costs.json').read_text())}
    out.mkdir();freeze_sources(out,sources);reports=[];geometry_hashes={};covered=set()
    for case in cases:
        entry=results[case['task_key']];receipt=parent/entry['evidence']['receipt'];assert digest(receipt)==entry['evidence']['receipt_sha256']
        preflight=receipt.parent.parent/'execute/preflight.json';pre=json.loads(preflight.read_text());contact=pre['points'][case['reference_index']]['source_contact']
        assert contact==case['contact'] and case['foot']==contact['witness']['foot'] and case['source_point']==contact['witness']['source_point']
        for occurrence in case.get('covered_occurrences',[{'task_key':case['task_key'],'reference_index':case['reference_index']}]):
            identity=(occurrence['task_key'],occurrence['reference_index'])
            if identity in covered:raise ValueError('Duplicate occurrence in contact coverage')
            covered.add(identity)
            row=results[identity[0]];receipt2=parent/row['evidence']['receipt'];assert digest(receipt2)==row['evidence']['receipt_sha256']
            point=json.loads((receipt2.parent.parent/'execute/preflight.json').read_text())['points'][identity[1]]
            assert point['source_contact']==contact
        geo=catalog[case['scene']];path=Path(geo['native_geometry_path'])
        if str(path) not in geometry_hashes:geometry_hashes[str(path)]=digest(path)
        actual_geo=geometry_hashes[str(path)]
        assert geo['native_geometry_sha256']==contact['geometry_sha256']==actual_geo
        with path.open('rb') as f:
            nv,nt=struct.unpack('<ii',f.read(8));index=contact['triangle'];assert 0<=index<nt
            f.seek(8+12*nv+12*index);ids=struct.unpack('<iii',f.read(12));triangle=[]
            for i in ids:
                assert 0<=i<nv;f.seek(8+12*i);triangle.append(list(struct.unpack('<fff',f.read(12))))
        report={**case,'source_triangle_vertices':triangle,'description':describe_triangle(triangle,case['foot']),
            'source_preflight':str(preflight),'source_preflight_sha256':digest(preflight),'native_geometry_sha256':actual_geo}
        reports.append(report)
    assert len(covered)==cfg.get('expected_occurrences',7)
    summary=dict(status='SOURCE_TRIANGLE_INTERPRETATION_NOT_REPAIR',records=len(cases),examined_occurrences=len(covered),affected_records=209,
        config_sha256=digest(cfg_path),contacts_sha256=digest(spec),catalog_sha256=digest(catalog_path),reports=reports,
        native_simulator_queries=0,native_movement_actions=0,targets_modified=0,collision_gates_modified=False,
        reserved_cpu_seconds=120,process_cpu_seconds=time.process_time()-started)
    write_json(out/'validation.json',summary);signal.alarm(0);return summary
