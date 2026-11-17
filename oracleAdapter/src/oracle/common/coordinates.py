"""Explicit axis/heading conventions, with no camera-to-foot height correction.

RxR README: zero heading faces source+y with z up; clockwise positive radians.
Habitat: right-handed y-up, local forward-z, quaternion coefficients xyzw.
This rotation alone does not identify a camera pose with an agent floor point.
"""
import math


def finite_vector(values, length):
    values=tuple(float(x) for x in values)
    if len(values)!=length or not all(math.isfinite(x) for x in values):
        raise ValueError('Finite vector with declared dimension required')
    return values


def matterport_to_habitat(point):
    x,y,z=finite_vector(point,3)
    return x,z,-y


def habitat_to_matterport(point):
    x,y,z=finite_vector(point,3)
    return x,-z,y


def heading_quaternion_xyzw(heading):
    if not math.isfinite(heading):raise ValueError('Finite heading in radians required')
    return 0.,-math.sin(heading/2),0.,math.cos(heading/2)


def quaternion_forward(quaternion):
    q=finite_vector(quaternion,4);norm=math.sqrt(sum(x*x for x in q))
    if abs(norm-1.)>1e-4:raise ValueError('Unit xyzw quaternion required')
    x,y,z,w=(v/norm for v in q)
    return -2*(x*z+w*y),-2*(y*z-w*x),-(1-2*(x*x+y*y))


def direction_error(a,b):
    a,b=finite_vector(a,3),finite_vector(b,3)
    na,nb=math.sqrt(sum(x*x for x in a)),math.sqrt(sum(x*x for x in b))
    if min(na,nb)==0:raise ValueError('Nonzero directions required')
    return math.acos(max(-1.,min(1.,sum(x*y for x,y in zip(a,b))/(na*nb))))
