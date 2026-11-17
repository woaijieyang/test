"""Exact source contact witnesses for every saved shortest-corridor contact."""
import datetime,json,math,os,struct,sys
from pathlib import Path
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from swept_cylinder_witness import linear_sweep_witness,verify_witness
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
import numpy as np
B=R/'outputs/landmark-connectivity';source=B/'D7-phasehalf-new90-native-corridors-v1/validation.json';v=json.loads(source.read_text());m=json.loads((B/'full-source-guard-D7-tiled-phasehalf-v1/guarded/manifest.json').read_text());receipt=json.loads(Path(m['native_geometry']['receipt_path']).read_text());path=Path(receipt['native_geometry_path']);assert digest(path)==receipt['native_geometry_sha256'];raw=path.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);vertices=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);indices=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=vertices[indices].astype(float)
records=[];high_paths=set();cache={}
for path_id,p in v['paths'].items():
    points=p['points_with_projection_connectors']
    for contact in p['segment_contacts']:
        i=contact['index'];j=contact['native_triangle'];a,b=points[i],points[i+1];key=(j,tuple(a),tuple(b))
        if key not in cache:
            witness=linear_sweep_witness(tri[j],a,b);assert witness is not None and verify_witness(tri[j],a,b,witness)
            upper=linear_sweep_witness(tri[j],a,b,foot_epsilon=.3)
            if upper is not None and not verify_witness(tri[j],a,b,upper,foot_epsilon=.3):upper=None
            normal=np.cross(tri[j,1]-tri[j,0],tri[j,2]-tri[j,0]);norm=float(np.linalg.norm(normal))
            cache[key]={'native_triangle':j,'vertices':tri[j].tolist(),'start':a,'end':b,'contact':witness,'at_or_above_0p3m_contact':upper,'absolute_normal_y':None if norm==0 else abs(float(normal[1]))/norm,'note':'0.3m is only a diagnostic height band; original complete body contact remains failure.'}
        witness=cache[key]
        if witness['at_or_above_0p3m_contact'] is not None:high_paths.add(path_id)
        records.append({'path_id':path_id,'segment_index':i,**witness})
assert len(records)==sum(len(p['segment_contacts']) for p in v['paths'].values())
output=B/'D7-phasehalf-new90-native-corridors-v1/exact-contact-certificates.json';assert not output.exists();summary={'saved_segment_contacts':len(records),'unique_segment_contacts':len(cache),'certified_contacts':len(records),'unique_paths':len(v['paths']),'paths_with_certified_contact_at_or_above_0p3m':len(high_paths),'tasks_nominal_high_contact':sum(r['nominal_path_id'] in high_paths for r in v['records']),'tasks_remaining_high_contact':sum(r['remaining_path_id'] in high_paths for r in v['records'])}
atomic_json(output,{'status':'PASS_ALL_SAVED_CONTACT_WITNESSES_EXACT_RATIONAL','summary':summary,'records':records,'source_receipt_sha256':digest(source),'geometry_sha256':digest(path),'witness_helper_sha256':digest(R/'tests/landmark_diagnostics/swept_cylinder_witness.py'),'script_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat(),'limits':'Exact rational certificates reconstruct a source-triangle point and time on the unchanged straight chord. Certifies positive savedcontacts only, not all negative geometry or all alternative paths. Heightband probes do not alter admission, body or motion.'});print(summary)

