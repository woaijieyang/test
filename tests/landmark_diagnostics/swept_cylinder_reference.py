"""Analytical linear sweep of a vertical cylinder against one triangle.
The triangle minus the translation segment is the convex hull of six vertices.
Clipping that hull to the body-height slab and projecting to x/z gives the
radial distance. All pairwise edge/slab intersections include every hull edge;
extra intersections are interior points and do not enlarge the convex hull.
This module does not define or authorize any alternative agent trajectory.
"""
import math,itertools
from projected_distance_reference import projected_distance
def triangle_linear_sweep_distance(triangle,start,end,height=1.5,foot_epsilon=1e-5):
 if height<=foot_epsilon or foot_epsilon<0:raise ValueError('invalid body slab')
 points=[[float(v[k])-float(p[k]) for k in range(3)] for p in (start,end) for v in triangle]
 if not all(math.isfinite(x) for p in points for x in p):raise ValueError('nonfinite geometry')
 clipped=[p for p in points if foot_epsilon<=p[1]<=height]
 for a,b in itertools.combinations(points,2):
  for plane in (foot_epsilon,height):
   if (a[1]-plane)*(b[1]-plane)<0:
    t=(plane-a[1])/(b[1]-a[1]);clipped.append([a[k]+t*(b[k]-a[k]) for k in range(3)])
 return projected_distance(clipped,[0.,0.,0.]) if clipped else math.inf
