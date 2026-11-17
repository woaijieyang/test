"""Exact-orientation reference for projected convex-polygon distance; diagnostic oracle."""
import math
from fractions import Fraction
def projected_distance(poly,point):
 pts=sorted(set((Fraction(float(v[0])),Fraction(float(v[2]))) for v in poly))
 q=(Fraction(float(point[0])),Fraction(float(point[2])))
 def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
 if len(pts)>1:
  lower=[];upper=[]
  for p in pts:
   while len(lower)>1 and cross(lower[-2],lower[-1],p)<=0:lower.pop()
   lower.append(p)
  for p in reversed(pts):
   while len(upper)>1 and cross(upper[-2],upper[-1],p)<=0:upper.pop()
   upper.append(p)
  hull=lower[:-1]+upper[:-1]
 else:hull=pts
 if len(hull)>=3 and all(cross(a,b,q)>=0 for a,b in zip(hull,hull[1:]+hull[:1])):return 0.
 qx,qz=map(float,q);best=math.inf
 for a,b in zip(hull,hull[1:]+hull[:1]):
  ax,az=map(float,a);bx,bz=map(float,b);dx,dz=bx-ax,bz-az;den=dx*dx+dz*dz
  t=max(0.,min(1.,((qx-ax)*dx+(qz-az)*dz)/den)) if den else 0.
  best=min(best,math.hypot(qx-ax-t*dx,qz-az-t*dz))
 return best
