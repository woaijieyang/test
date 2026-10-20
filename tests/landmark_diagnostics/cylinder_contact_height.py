"""Height extrema of a triangle inside a vertical cylinder, for diagnosis only.
Collision admission stays with the existing strict projected-distance predicate.
This returns extrema on the closed radial boundary; a supremum is not new penetration tolerance.
"""
import math
import numpy as np
from projected_distance_reference import projected_distance

def clip_y(poly,bound,above):
 result=[]
 if not poly:return result
 for a,b in zip(poly,poly[1:]+poly[:1]):
  aa=a[1]>=bound if above else a[1]<=bound;bb=b[1]>=bound if above else b[1]<=bound
  if aa:result.append(a)
  if aa!=bb:result.append(a+(b-a)*((bound-a[1])/(b[1]-a[1])))
 return result

def contact_height_range(triangle,foot,radius=.1-1e-6,height=1.5,foot_epsilon=1e-5):
 tri=np.asarray(triangle,dtype=float);foot=np.asarray(foot,dtype=float);poly=clip_y(clip_y(list(tri),foot[1]+foot_epsilon,True),foot[1]+height,False)
 if len(poly)<3:return None
 candidates=[];r2=radius*radius
 def add(p):
  if np.sum((p[[0,2]]-foot[[0,2]])**2)<=r2+1e-12 and foot[1]+foot_epsilon-1e-10<=p[1]<=foot[1]+height+1e-10:candidates.append(p)
 for a,b in zip(poly,poly[1:]+poly[:1]):
  add(a);d=(b-a)[[0,2]];v=(a-foot)[[0,2]];A=float(np.dot(d,d));B=2*float(np.dot(v,d));C=float(np.dot(v,v))-r2
  if A==0:continue
  disc=B*B-4*A*C
  if disc<0:continue
  root=math.sqrt(max(0,disc))
  for t in [(-B-root)/(2*A),(-B+root)/(2*A)]:
   if -1e-12<=t<=1+1e-12:add(a+(b-a)*min(1,max(0,t)))
 normal=np.cross(tri[1]-tri[0],tri[2]-tri[0])
 if abs(normal[1])>1e-16:
  gradient=-normal[[0,2]]/normal[1];constant=float(np.dot(normal,tri[0])/normal[1]);xz_options=[foot[[0,2]]]
  length=float(np.linalg.norm(gradient))
  if length>0:xz_options.extend([foot[[0,2]]+radius*gradient/length,foot[[0,2]]-radius*gradient/length])
  for xz in xz_options:
   q=np.array([xz[0],float(np.dot(gradient,xz)+constant),xz[1]])
   if projected_distance(poly,q)==0:add(q)
 if not candidates:return None
 low=min(candidates,key=lambda p:p[1]);high=max(candidates,key=lambda p:p[1]);return {'minimum_height':float(low[1]-foot[1]),'maximum_height':float(high[1]-foot[1]),'minimum_point':low.tolist(),'maximum_point':high.tolist(),'clipped_triangle_maximum_height':float(max(p[1] for p in poly)-foot[1])}
