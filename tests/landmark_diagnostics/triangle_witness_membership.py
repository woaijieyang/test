"""Exact binary-rational dimension detection for saved geometry witnesses.
This validates witnesses only; it does not alter collision admission.
"""
import math
from fractions import Fraction as F
def witness_membership(triangle,point):
 if len(triangle)!=3 or any(len(p)!=3 for p in [*triangle,point]):raise ValueError("Expected3D triangle and point")
 if not all(math.isfinite(x) for p in [*triangle,point] for x in p):raise ValueError("Nonfinite geometry")
 a,b,c=[[F(float(x)) for x in p] for p in triangle];p=[F(float(x)) for x in point]
 def sub(a,b):return [x-y for x,y in zip(a,b)]
 def dot(a,b):return sum(x*y for x,y in zip(a,b))
 def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
 u=sub(b,a);v=sub(c,a);q=sub(p,a);n=cross(u,v);n2=dot(n,n)
 if n2:
  alpha=dot(cross(q,v),n)/n2;beta=dot(cross(u,q),n)/n2;residual=abs(float(dot(q,n)))/math.sqrt(float(n2))
  return {"kind":"triangle","minimum_barycentric":float(min(alpha,beta,1-alpha-beta)),"residual_m":residual}
 distances=[]
 for aa,bb in [(a,b),(b,c),(c,a)]:
  e=sub(bb,aa);z=sub(p,aa);ee=dot(e,e);t=max(F(0),min(F(1),dot(z,e)/ee)) if ee else F(0);delta=[z[i]-t*e[i] for i in range(3)];distances.append(dot(delta,delta))
 return {"kind":"point" if a==b==c else "segment","minimum_barycentric":None,"residual_m":math.sqrt(float(min(distances)))}
