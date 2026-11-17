"""Source geometry check of five original and privately corrected native steps."""
import os,sys,json,math,struct,ast,datetime
from pathlib import Path
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
import numpy as np
source=R/'outputs/connectivity/r2r-offmesh-patched-replay-v1/validation.json'
v=json.loads(source.read_text())
catalog_path=R/'outputs/landmark-connectivity/native-source-catalog-v1/catalog.json'
catalog={r['scene']:r for r in json.loads(catalog_path.read_text())['scenes']}
helper=R/'tests/landmark_diagnostics/audit_prb_step_interpretations.py'
binding=json.loads((R/'outputs/landmark-connectivity/pRb-original-trace-step-interpretation-v1/validation.json').read_text())
assert digest(helper)==binding['script_sha256']
nodes=[n for n in ast.parse(helper.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='sweep'];assert len(nodes)==1
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(helper),'exec'),globals())
reports=[]
for scene in sorted({r['scene'].split('/')[1] for r in v['records']}):
    item=catalog[scene];rp=Path(item['receipt_path']);receipt=json.loads(rp.read_text());assert receipt['scene']==scene
    path=Path(receipt['native_geometry_path']);assert digest(path)==receipt['native_geometry_sha256']
    raw=path.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);assert len(raw)==8+12*nv+12*nt
    vertices=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3)
    indices=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3)
    tri=vertices[indices].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);cache={};regions={}
    for r in v['records']:
        if r['scene'].split('/')[1]!=scene:continue
        before=r['before']['position'];original=r['actual'];patched=r['one_step_replayed_position']
        reports.append({'task_key':r['task_key'],'native_geometry_sha256':digest(path),'native_geometry_receipt_sha256':digest(rp),
                        'before_body_contact':sweep(before,before),'original_body_contact':sweep(original,original),
                        'patched_body_contact':sweep(patched,patched),'original_chord_contact':sweep(before,original),
                        'patched_chord_contact':sweep(before,patched),'patched_vertical_m':abs(patched[1]-before[1])})
output=R/'outputs/connectivity/pathfinder-height-boundary-source-v1.json';assert not output.exists()
atomic_json(output,{'status':'COMPLETE_FIVE_STEP_SOURCE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE','records':reports,
                   'patched_body_contact_count':sum(r['patched_body_contact'] is not None for r in reports),
                   'patched_chord_contact_count':sum(r['patched_chord_contact'] is not None for r in reports),
                   'input_sha256':digest(source),'catalog_sha256':digest(catalog_path),'sweep_traversal_sha256':digest(helper),
                   'script_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat(),
                   'limits':'Five failure steps only. Exact straight swept body1.5m/radius.1m, unchanged foot/radial tolerance. No invented internal step curves and no full model acceptance.'})
print([(r['task_key'],r['patched_body_contact'] is not None,r['patched_chord_contact'] is not None) for r in reports])

