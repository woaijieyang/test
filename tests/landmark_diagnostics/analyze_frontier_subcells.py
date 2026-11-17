"""Bounded adaptive geometry queries inside blocked frontier cells; no mesh or gate changes."""
import os,sys,json,math,struct,heapq,itertools,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
sys.path[:0]=[str(Path.cwd()/'scripts'),str(Path.cwd()/'tests/landmark_diagnostics')]
from workspace import ROOT,atomic_json,digest
from projected_distance_reference import projected_distance
import numpy as np,psutil
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])])
O=ROOT/'outputs/landmark-connectivity/native-stage-trace-xc-v3';out=O/'frontier-subcell-analysis.json';assert not out.exists();atomic_json(O/'frontier-subcell-process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
front=json.loads((O/'frontier-source-geometry.json').read_text());v=json.loads((O/'validation.json').read_text());cs,ch,*_=v['native_build_config'];raw=(O/'native-1.bin').read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);verts=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);idx=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=verts[idx].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);length=np.linalg.norm(normal,axis=1);ny=np.divide(abs(normal[:,1]),length,out=np.zeros(len(tri)),where=length>1e-12)
helper=ROOT/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';s=helper.read_text();exec(s[s.index('def clip('):s.index('records=[]')]);reports=[]
for item in front['samples']:
 center=np.array(item['position']);half=cs/2;ids=np.flatnonzero((lo[:,0]<center[0]+half+.1)&(hi[:,0]>center[0]-half-.1)&(lo[:,2]<center[2]+half+.1)&(hi[:,2]>center[2]-half-.1)&(lo[:,1]<center[1]+1.5)&(hi[:,1]>center[1]+1e-5));polys=[]
 for j in ids:
  poly=clip(list(tri[j]),center[1]+1e-5,True)
  if len(poly)<3:continue
  poly=clip(poly,center[1]+1.5,False)
  if len(poly)>=3:
   arr=np.array(poly);polys.append((int(j),poly,arr[:,[0,2]].min(axis=0),arr[:,[0,2]].max(axis=0)))
 floors=np.flatnonzero((lo[:,0]<=center[0]+half)&(hi[:,0]>=center[0]-half)&(lo[:,2]<=center[2]+half)&(hi[:,2]>=center[2]-half)&(lo[:,1]<=center[1]+1e-5)&(hi[:,1]>=center[1]-ch-1e-5)&(ny>=math.cos(math.pi/4)-1e-9))
 def clearance(q):
  best=.1+math.sqrt(2)*cs;witness=None
  for j,poly,a,b in polys:
   bound=math.hypot(max(a[0]-q[0],0,q[0]-b[0]),max(a[1]-q[2],0,q[2]-b[1]))
   if bound>=best:continue
   d=projected_distance(poly,q)
   if d<best:best=d;witness=j
  return best,witness
 def support(q):
  hits=[]
  for j in floors:
   a,b,c=tri[j];u=b[[0,2]]-a[[0,2]];w=c[[0,2]]-a[[0,2]];delta=q[[0,2]]-a[[0,2]];den=u[0]*w[1]-u[1]*w[0]
   if abs(den)<1e-12:continue
   t=(delta[0]*w[1]-delta[1]*w[0])/den;s=(u[0]*delta[1]-u[1]*delta[0])/den
   if t>=-1e-8 and s>=-1e-8 and t+s<=1+1e-8:
    y=float(a[1]+t*(b[1]-a[1])+s*(c[1]-a[1]))
    if q[1]-ch-1e-5<=y<=q[1]+1e-5:hits.append((y,int(j)))
  return max(hits) if hits else None
 counter=itertools.count();queue=[(0,next(counter),center,half,0)];tested=0;blocked=0;uncertain=0;found=None;certificates=[]
 while queue and tested<2000:
  _,_,q,h,depth=heapq.heappop(queue);d,witness=clearance(q);tested+=1;reach=math.sqrt(2)*h
  if d+reach<.1-1e-6-1e-12:
   blocked+=1;certificates.append({'center':q.tolist(),'half_width':h,'triangle':witness,'distance':d,'maximum_xy_offset':reach});continue
  if d>=.1-1e-6:
   sup=support(q)
   if sup:found={'position':q.tolist(),'minimum_projected_distance':d,'support_y':sup[0],'support_triangle':sup[1],'height_above_support':q[1]-sup[0]};break
  if depth>=6:uncertain+=1;continue
  nh=h/2
  for dx in [-nh,nh]:
   for dz in [-nh,nh]:
    child=q+np.array([dx,0,dz]);cd,_=clearance(child);heapq.heappush(queue,(-(cd+math.sqrt(2)*nh),next(counter),child,nh,depth+1))
 status='SOURCE_CLEAR_SUPPORTED_POINT_FOUND' if found else 'FIXED_HEIGHT_CELL_CERTIFIED_BLOCKED' if not queue and not uncertain else 'INCONCLUSIVE_AT_FIXED_SEARCH_LIMIT'
 reports.append({'span_id':item['path_index'],'span_key':item['span_key'],'center':center.tolist(),'status':status,'tested_subcells':tested,'blocked_subcells':blocked,'uncertain_leaves':uncertain,'pending_subcells':len(queue),'candidate':found,'blocked_certificates':certificates});print(item['path_index'],status,tested,flush=True)
atomic_json(out,{'status':'SUBCELL_DIAGNOSIS_NOT_ROUTE_ACCEPTANCE','time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'cell_size':cs,'fixed_y':'Original pre-erosion compact span height','body':{'height':1.5,'radius':.1},'max_depth':6,'max_tested_subcells_per_cell':2000,'source_geometry_sha256':digest(O/'native-1.bin'),'frontier_receipt_sha256':digest(O/'frontier-source-geometry.json'),'reference_distance_sha256':digest(ROOT/'tests/landmark_diagnostics/projected_distance_reference.py'),'script_sha256':digest(__file__),'records':reports,'limits':'Blocked certificates apply only to the stated fixed-height cell boxes. A supported body-clear point alone does not prove a connecting path or real primitive-action execution. No data, mesh, body or threshold changed.'})
