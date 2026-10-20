"""Closest point on a triangle under a horizontal disk centered at the source anchor."""
import math
import numpy as np

def segment_closest(p,a,b):
 e=b-a;den=float(e@e);t=min(1,max(0,float((p-a)@e)/den)) if den else 0.;return a+t*e

def triangle_closest(p,t):
 a,b,c=t;ab=b-a;ac=c-a
 if float(np.linalg.norm(np.cross(ab,ac)))<1e-14:return min([segment_closest(p,a,b),segment_closest(p,b,c),segment_closest(p,c,a)],key=lambda q:float((q-p)@(q-p)))
 ap=p-a;d1=float(ab@ap);d2=float(ac@ap)
 if d1<=0 and d2<=0:return a.copy()
 bp=p-b;d3=float(ab@bp);d4=float(ac@bp)
 if d3>=0 and d4<=d3:return b.copy()
 vc=d1*d4-d3*d2
 if vc<=0 and d1>=0 and d3<=0:return a+(d1/(d1-d3))*ab
 cp=p-c;d5=float(ab@cp);d6=float(ac@cp)
 if d6>=0 and d5<=d6:return c.copy()
 vb=d5*d2-d1*d6
 if vb<=0 and d2>=0 and d6<=0:return a+(d2/(d2-d6))*ac
 va=d3*d6-d5*d4
 if va<=0 and d4-d3>=0 and d5-d6>=0:return b+((d4-d3)/((d4-d3)+(d5-d6)))*(c-b)
 den=1/(va+vb+vc);return a+ab*(vb*den)+ac*(vc*den)

def closest_in_horizontal_disk(triangle,anchor,radius=.35):
 t=np.asarray(triangle,dtype=float);p=np.asarray(anchor,dtype=float);r2=radius*radius;candidates=[]
 def add(q):
  if np.isfinite(q).all() and float(np.sum((q[[0,2]]-p[[0,2]])**2))<=r2+1e-12:candidates.append(q)
 add(triangle_closest(p,t))
 for a,b in zip(t,np.roll(t,-1,axis=0)):
  e=b-a;d=e[[0,2]];v=(a-p)[[0,2]];A=float(d@d);B=2*float(v@d);C=float(v@v)-r2
  if A==0:
   if C<=0:add(segment_closest(p,a,b))
   continue
  disc=B*B-4*A*C
  if disc<0:continue
  root=math.sqrt(max(0,disc));low=max(0,(-B-root)/(2*A));high=min(1,(-B+root)/(2*A))
  if low>high:continue
  den=float(e@e);q=min(high,max(low,float((p-a)@e)/den if den else low));add(a+q*e);add(a+low*e);add(a+high*e)
 normal=np.cross(t[1]-t[0],t[2]-t[0])
 if abs(normal[1])>1e-14:
  g=-normal[[0,2]]/normal[1];h=float(t[0,1]-p[1]-g@(t[0,[0,2]]-p[[0,2]]));norm=float(np.linalg.norm(g));xz=[]
  if norm>0:
   if abs(h)>=norm*radius:xz=[-math.copysign(1,h)*radius*g/norm]
   else:
    parallel=-h*g/(norm*norm);perp=np.array([-g[1],g[0]])/norm;extent=math.sqrt(max(0,r2-float(parallel@parallel)));xz=[parallel+extent*perp,parallel-extent*perp]
  for u in xz:
   q=p+np.array([u[0],h+float(g@u),u[1]]);uv,*_=np.linalg.lstsq(np.column_stack((t[1]-t[0],t[2]-t[0])),q-t[0],rcond=None);error=np.linalg.norm(t[0]+uv[0]*(t[1]-t[0])+uv[1]*(t[2]-t[0])-q)
   if error<1e-8 and min(uv)>=-1e-10 and sum(uv)<=1+1e-10:add(q)
 return min(candidates,key=lambda q:float((q-p)@(q-p))).copy() if candidates else None
