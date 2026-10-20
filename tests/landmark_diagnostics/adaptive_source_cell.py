"""Bounded in-cell source queries; same physical predicate and finite resolution as prior audit."""
import math,heapq,itertools
import numpy as np
from projected_distance_reference import projected_distance

def solve_cell(center,cs,ch,tri,lo,hi,ny,clip,excluded=()):
 center=np.array(center);half=cs/2;ids=np.flatnonzero((lo[:,0]<center[0]+half+.1)&(hi[:,0]>center[0]-half-.1)&(lo[:,2]<center[2]+half+.1)&(hi[:,2]>center[2]-half-.1)&(lo[:,1]<center[1]+1.5)&(hi[:,1]>center[1]+1e-5));polys=[]
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
   if sup and all(math.dist(q,p)>1e-6 for p in excluded):found={'position':q.tolist(),'minimum_projected_distance':d,'support_y':sup[0],'support_triangle':sup[1],'height_above_support':q[1]-sup[0]};break
  if depth>=6:uncertain+=1;continue
  nh=h/2
  for dx in [-nh,nh]:
   for dz in [-nh,nh]:
    child=q+np.array([dx,0,dz]);cd,_=clearance(child);heapq.heappush(queue,(-(cd+math.sqrt(2)*nh),next(counter),child,nh,depth+1))
 status='SOURCE_CLEAR_SUPPORTED_POINT_FOUND' if found else 'FIXED_HEIGHT_CELL_CERTIFIED_BLOCKED' if not queue and not uncertain else 'INCONCLUSIVE_AT_FIXED_SEARCH_LIMIT'

 return {'status':status,'tested_subcells':tested,'blocked_subcells':blocked,'uncertain_leaves':uncertain,'pending_subcells':len(queue),'candidate':found,'blocked_certificates':certificates,'distance_note':'Distance score is capped and evaluated against all potential colliders of the cell; it is not a global clearance measurement.'}
