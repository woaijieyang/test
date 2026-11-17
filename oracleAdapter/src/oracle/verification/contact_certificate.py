"""Exact-rational contact witnesses for the existing straight-cylinder diagnostic.

This is a certificate extractor, not a change to collision admission or motion.
The triangle minus a translation segment is a convex hull of six vertices.
Keep affine triangle weights and segment time through slab clipping/projection.
"""
import itertools
import math
from fractions import Fraction as F


def _mix(items, weights):
    return {'p': [sum(w*v['p'][k] for v,w in zip(items,weights)) for k in range(3)],
            't': sum(w*v['t'] for v,w in zip(items,weights)),
            'b': [sum(w*v['b'][k] for v,w in zip(items,weights)) for k in range(3)]}


def _cross(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _encode(q):
    return [q.numerator,q.denominator]


def linear_sweep_witness(triangle,start,end,height=1.5,foot_epsilon=1e-5):
    if height<=foot_epsilon or foot_epsilon<0:
        raise ValueError('invalid body slab')
    values=[float(x) for p in [*triangle,start,end] for x in p]
    if not all(math.isfinite(x) for x in values):
        raise ValueError('nonfinite geometry')
    tr=[[F(float(x)) for x in v] for v in triangle]
    aa=[F(float(x)) for x in start];bb=[F(float(x)) for x in end]
    low,high=F(float(foot_epsilon)),F(float(height))
    original=[]
    for time,foot in [(F(0),aa),(F(1),bb)]:
        for i,vertex in enumerate(tr):
            original.append({'p':[vertex[k]-foot[k] for k in range(3)],'t':time,'b':[F(int(i==j)) for j in range(3)]})
    clipped=[v for v in original if low<=v['p'][1]<=high]
    for a,b in itertools.combinations(original,2):
        for plane in (low,high):
            if (a['p'][1]-plane)*(b['p'][1]-plane)<0:
                weight=(plane-a['p'][1])/(b['p'][1]-a['p'][1])
                clipped.append(_mix([a,b],[1-weight,weight]))
    if not clipped:
        return None
    representatives={}
    for v in clipped:representatives.setdefault((v['p'][0],v['p'][2]),v)
    points=sorted(representatives)
    if len(points)>1:
        lower=[];upper=[]
        for p in points:
            while len(lower)>1 and _cross(lower[-2],lower[-1],p)<=0:lower.pop()
            lower.append(p)
        for p in reversed(points):
            while len(upper)>1 and _cross(upper[-2],upper[-1],p)<=0:upper.pop()
            upper.append(p)
        hull=lower[:-1]+upper[:-1]
    else:hull=points
    origin=(F(0),F(0));chosen=None
    if len(hull)>=3 and all(_cross(a,b,origin)>=0 for a,b in zip(hull,hull[1:]+hull[:1])):
        for i in range(1,len(hull)-1):
            a,b,c=hull[0],hull[i],hull[i+1];den=_cross(a,b,c)
            if not den:continue
            weights=[_cross(b,c,origin)/den,_cross(c,a,origin)/den,_cross(a,b,origin)/den]
            if min(weights)>=0:
                chosen=_mix([representatives[a],representatives[b],representatives[c]],weights);break
        assert chosen is not None
    else:
        best=None
        for a,b in zip(hull,hull[1:]+hull[:1]):
            dx,dz=b[0]-a[0],b[1]-a[1];den=dx*dx+dz*dz
            w=max(F(0),min(F(1),-(a[0]*dx+a[1]*dz)/den)) if den else F(0)
            value=_mix([representatives[a],representatives[b]],[1-w,w])
            distance2=value['p'][0]**2+value['p'][2]**2
            if best is None or distance2<best:best=distance2;chosen=value
    time=chosen['t'];weights=chosen['b']
    assert 0<=time<=1 and min(weights)>=0 and sum(weights)==1
    source=[sum(weights[i]*tr[i][k] for i in range(3)) for k in range(3)]
    foot=[(1-time)*aa[k]+time*bb[k] for k in range(3)]
    relative=[source[k]-foot[k] for k in range(3)]
    assert relative==chosen['p'] and low<=relative[1]<=high
    distance2=relative[0]**2+relative[2]**2
    return {'distance':math.sqrt(float(distance2)), 'time':float(time),
            'relative_height':float(relative[1]),'source_point':[float(x) for x in source],
            'foot':[float(x) for x in foot], 'exact_time':_encode(time),
            'exact_barycentric':[_encode(x) for x in weights],
            'exact_distance_squared':_encode(distance2),
            'exact_relative_height':_encode(relative[1])}


def verify_witness(triangle,start,end,witness,radius=.1-1e-6,height=1.5,foot_epsilon=1e-5):
    """Check certificate using original values and rational arithmetic, no hull."""
    decode=lambda x:F(int(x[0]),int(x[1]))
    time=decode(witness['exact_time']);weights=[decode(x) for x in witness['exact_barycentric']]
    assert 0<=time<=1 and len(weights)==3 and min(weights)>=0 and sum(weights)==1
    source=[sum(weights[i]*F(float(triangle[i][k])) for i in range(3)) for k in range(3)]
    foot=[(1-time)*F(float(start[k]))+time*F(float(end[k])) for k in range(3)]
    delta=[source[k]-foot[k] for k in range(3)]
    assert F(float(foot_epsilon))<=delta[1]<=F(float(height))
    distance2=delta[0]**2+delta[2]**2
    assert distance2==decode(witness['exact_distance_squared']) and delta[1]==decode(witness['exact_relative_height'])
    assert witness['time']==float(time) and witness['relative_height']==float(delta[1])
    assert witness['source_point']==[float(x) for x in source] and witness['foot']==[float(x) for x in foot]
    assert witness['distance']==math.sqrt(float(distance2))
    return distance2<F(float(radius))**2

