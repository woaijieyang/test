"""Inspect the native source geometry along the minimum-erased-cell graph bridge."""
import os,sys,json,math,struct,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
sys.path[:0]=[str(Path.cwd()/'scripts'),str(Path.cwd()/'tests/landmark_diagnostics')]
from workspace import ROOT,atomic_json,digest
from projected_distance_reference import projected_distance
import numpy as np,psutil
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])])
O=ROOT/'outputs/landmark-connectivity/native-stage-trace-xc-v3';g=json.loads((O/'ledge-bridges-v2/validation.json').read_text());path=g['removed_bridge_spans'];raw=(O/'native-1.bin').read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);v=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);indices=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=v[indices].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);norm=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);length=np.linalg.norm(norm,axis=1);ny=np.divide(abs(norm[:,1]),length,out=np.zeros(len(tri)),where=length>1e-12)
helper=ROOT/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';s=helper.read_text();exec(s[s.index('def clip('):s.index('records=[]')])
samples=[{'position':r['world_center'],'raw_index':r['raw_index'],'ledge_reason':r['reason'],'cell_center':True} for r in path]
reports=[]
for sample in samples:
 p=np.array(sample['position']);ids=np.flatnonzero((lo[:,0]<p[0]+.1)&(hi[:,0]>p[0]-.1)&(lo[:,2]<p[2]+.1)&(hi[:,2]>p[2]-.1)&(lo[:,1]<p[1]+1.5)&(hi[:,1]>p[1]+1e-5));contacts=[];false=[]
 for j in ids:
  poly=clip(list(tri[j]),p[1]+1e-5,True)
  if len(poly)<3:continue
  poly=clip(poly,p[1]+1.5,False)
  if len(poly)<3:continue
  old=distance(poly,p);exact=projected_distance(poly,p)
  row={'triangle':int(j),'vertices':tri[j].tolist(),'exact_distance':exact,'prior_distance':old,'min_height':float(min(x[1] for x in poly)-p[1]),'max_height':float(max(x[1] for x in poly)-p[1]),'normal_abs_y':float(ny[j])}
  if exact<.1-1e-6:contacts.append(row)
  elif old<.1-1e-6:false.append(row)
 support=[];near=np.flatnonzero((lo[:,0]<=p[0]+.10001)&(hi[:,0]>=p[0]-.10001)&(lo[:,2]<=p[2]+.10001)&(hi[:,2]>=p[2]-.10001)&(lo[:,1]<=p[1]+1e-5)&(hi[:,1]>=p[1]-.5)&(ny>=math.cos(math.pi/4)-1e-9))
 for r,ang in [(0,0)]+[(.1,j*2*math.pi/24) for j in range(24)]:
  x=p[0]+r*math.cos(ang);z=p[2]+r*math.sin(ang);hits=[]
  for j in near:
   a,b,c=tri[j];u=b[[0,2]]-a[[0,2]];w=c[[0,2]]-a[[0,2]];delta=np.array([x,z])-a[[0,2]];den=u[0]*w[1]-u[1]*w[0]
   if abs(den)<1e-12:continue
   t=(delta[0]*w[1]-delta[1]*w[0])/den;s=(u[0]*delta[1]-u[1]*delta[0])/den
   if t>=-1e-8 and s>=-1e-8 and t+s<=1+1e-8:
    y=float(a[1]+t*(b[1]-a[1])+s*(c[1]-a[1]))
    if p[1]-.5<=y<=p[1]+1e-5:hits.append(y)
  support.append({'radius':r,'angle':ang,'highest_support_y':max(hits) if hits else None,'drop':float(p[1]-max(hits)) if hits else None})
 reports.append({**sample,'contacts':contacts,'false_prior_contacts':false,'support':support})
atomic_json(O/'ledge-bridges-v2/removed-span-source-geometry.json',{'status':'SOURCE_GEOMETRY_BRIDGE_DIAGNOSIS_NOT_ROUTE_ACCEPTANCE','time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'graph_receipt_sha256':digest(O/'ledge-bridges-v2/validation.json'),'native_geometry_sha256':digest(O/'native-1.bin'),'script_sha256':digest(__file__),'reference_distance_sha256':digest(ROOT/'tests/landmark_diagnostics/projected_distance_reference.py'),'samples':reports,'limits':'Graph-center path is diagnostic, not native executable action sequence. Circle rays measure potential support within0.5m below feet, not an added acceptance rule. Both triangle orientations considered for support; body/clearance remain1.5m/0.1m.'});print('samples',len(reports),'body_contacts',sum(bool(x['contacts']) for x in reports),'prior_false_contacts',sum(len(x['false_prior_contacts']) for x in reports),'missing_rim_support',sum(any(s['highest_support_y'] is None for s in x['support']) for x in reports))
