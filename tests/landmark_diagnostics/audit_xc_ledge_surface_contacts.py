"""Cross-check recorded support-plane identities and collision witnesses with sweep primitive."""
import os,sys,json,struct,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
import numpy as np
O=R/'outputs/landmark-connectivity/native-stage-trace-xc-v3';D=O/'ledge-source-surfaces-v1';p=D/'validation.json';x=json.loads(p.read_text());data=(O/'native-1.bin').read_bytes();nv,nt=struct.unpack('<ii',data[:8]);vertices=np.frombuffer(data,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);indices=np.frombuffer(data,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=vertices[indices].astype(float);cs,ch=json.loads((O/'validation.json').read_text())['native_build_config'][:2];checked=0;issues=[]
for row in x['rows']:
 c=np.array(row['center'])
 for point in row['candidates']:
  q=np.array(point['position']);a,b,d=tri[point['support_triangle']];uv,*_=np.linalg.lstsq(np.column_stack((b-a,d-a)),q-a,rcond=None);err=np.linalg.norm(a+uv[0]*(b-a)+uv[1]*(d-a)-q)
  assert err<1e-7 and min(uv)>=-1e-7 and sum(uv)<=1+1e-7
  assert abs(q[0]-c[0])<=cs/2+1e-10 and abs(q[2]-c[2])<=cs/2+1e-10 and abs(q[1]-c[1])<=ch+1e-10
  assert not point['source_body_clear'];hit=point['first_contact'];dist=triangle_linear_sweep_distance(tri[hit['triangle']],q,q)
  if dist>=.1-1e-6:issues.append({'raw_index':row['raw_index'],'position':q.tolist(),'prior':hit,'sweep_distance':dist})
  checked+=1
assert checked==70 and len(x['rows'])==13
atomic_json(D/'contact-crosscheck.json',{'status':'PASS_RECORDED_CONTACT_AND_SUPPORT_IDENTITY' if not issues else 'FAILED','cells':13,'candidates_checked':checked,'issues':issues,'input_sha256':digest(p),'script_sha256':digest(__file__),'sweep_helper_sha256':digest(R/'tests/landmark_diagnostics/swept_cylinder_reference.py'),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Second clipping/sweep route checks each recorded witness and barycentric support identity. Shares exact projected-distance primitive. Finite candidate negatives, not whole-cell infeasibility proof or task acceptance.'});assert not issues;print('PASS',checked)
