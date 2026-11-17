"""Independently verify cell-cover certificates and the eight measured supported points."""
import os,sys,json,math,struct
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
sys.path[:0]=[str(Path.cwd()/'scripts'),str(Path.cwd()/'tests/landmark_diagnostics')]
from workspace import ROOT,atomic_json,digest
from projected_distance_reference import projected_distance
import numpy as np
O=ROOT/'outputs/landmark-connectivity/native-stage-trace-xc-v3';p=O/'frontier-subcell-analysis.json';d=json.loads(p.read_text());raw=(O/'native-1.bin').read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);v=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);idx=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=v[idx].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);cs=d['cell_size'];ch=json.loads((O/'validation.json').read_text())['native_build_config'][1]
helper=ROOT/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';s=helper.read_text();exec(s[s.index('def clip('):s.index('records=[]')]);blocked=clear=leafcount=0
for r in d['records']:
 center=np.array(r['center'])
 if r['status']=='FIXED_HEIGHT_CELL_CERTIFIED_BLOCKED':
  blocked+=1;certs=r['blocked_certificates'];assert r['pending_subcells']==0 and r['uncertain_leaves']==0;assert abs(sum((2*c['half_width'])**2 for c in certs)-cs*cs)<1e-12
  for i,c in enumerate(certs):
   q=np.array(c['center']);h=c['half_width'];assert abs(q[0]-center[0])+h<=cs/2+1e-12 and abs(q[2]-center[2])+h<=cs/2+1e-12 and q[1]==center[1]
   poly=clip(list(tri[c['triangle']]),q[1]+1e-5,True);poly=clip(poly,q[1]+1.5,False);assert len(poly)>=3;dist=projected_distance(poly,q);assert abs(dist-c['distance'])<1e-10 and dist+math.sqrt(2)*h<.1-1e-6
   for c2 in certs[:i]:
    q2=np.array(c2['center']);h2=c2['half_width'];assert abs(q[0]-q2[0])>=h+h2-1e-12 or abs(q[2]-q2[2])>=h+h2-1e-12
  leafcount+=len(certs)
 else:
  assert r['status']=='SOURCE_CLEAR_SUPPORTED_POINT_FOUND';clear+=1;c=r['candidate'];q=np.array(c['position']);assert abs(q[0]-center[0])<=cs/2+1e-12 and abs(q[2]-center[2])<=cs/2+1e-12 and q[1]==center[1]
  ids=np.flatnonzero((lo[:,0]<q[0]+.1)&(hi[:,0]>q[0]-.1)&(lo[:,2]<q[2]+.1)&(hi[:,2]>q[2]-.1)&(lo[:,1]<q[1]+1.5)&(hi[:,1]>q[1]+1e-5))
  for j in ids:
   poly=clip(list(tri[j]),q[1]+1e-5,True)
   if len(poly)<3:continue
   poly=clip(poly,q[1]+1.5,False)
   if len(poly)>=3:assert projected_distance(poly,q)>=.1-1e-6
  a,b,c3=tri[c['support_triangle']];u=b[[0,2]]-a[[0,2]];w=c3[[0,2]]-a[[0,2]];x=q[[0,2]]-a[[0,2]];den=u[0]*w[1]-u[1]*w[0];t=(x[0]*w[1]-x[1]*w[0])/den;z=(u[0]*x[1]-u[1]*x[0])/den;assert min(t,z)>=-1e-8 and t+z<=1+1e-8;y=float(a[1]+t*(b[1]-a[1])+z*(c3[1]-a[1]));normal=np.cross(b-a,c3-a);assert abs(normal[1])/np.linalg.norm(normal)>=math.cos(math.pi/4)-1e-9;assert abs(y-c['support_y'])<1e-10 and q[1]-ch-1e-5<=y<=q[1]+1e-5
assert (blocked,clear)==(11,8)
atomic_json(O/'frontier-subcell-independent-audit.json',{'status':'PASS_RESTRICTED_CELL_CERTIFICATES','fixed_height_cells_fully_blocked':blocked,'body_clear_supported_points':clear,'nonoverlapping_cover_leaves':leafcount,'input_sha256':digest(p),'native_geometry_sha256':digest(O/'native-1.bin'),'script_sha256':digest(__file__),'limits':'11 cell certificates concern the fixed compact height only;8 points are path-planning candidates, not moved landmarks or executed episode trajectories. No global impossibility or recovery claim.'});print(blocked,clear,leafcount)
