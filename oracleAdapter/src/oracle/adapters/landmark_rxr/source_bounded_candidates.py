"""Body-aware use of an existing bounded proposal family, without new identity matching.

Callbacks supply actual native queries and the frozen source predicate. This
module neither rebuilds a navmesh nor declares movement/semantic acceptance.
"""
from collections import Counter
import math


def collect_candidates(*,anchor,anchor_kind,camera,current,offsets,snap,navigable,contact,component,
                       sphere_m,extra_horizontal_m,extra_seed_points=(),candidate_admission=None,retain_seed_metadata=False):
    if anchor is None:return {'options':{},'rejections':{'unresolved_anchor':1}}
    if (len(anchor)!=3 or not all(math.isfinite(v) for v in anchor)
            or not all(math.isfinite(v) and v>0 for v in (sphere_m,extra_horizontal_m))):
        raise ValueError('Finite source anchor and explicit positive bounds required')
    if anchor_kind=='bounded_camera_projection' and camera is None:raise ValueError('Camera-derived anchor needs original camera identity')
    seeds=([(0,current)] if current is not None else [])+[(2,anchor)]
    seeds += [(3,[anchor[0]+dx,anchor[1],anchor[2]+dz]) for dx,dz in offsets]
    extra_seed_points=tuple(extra_seed_points)
    for point in extra_seed_points:
        if len(point)!=3 or not all(math.isfinite(float(v)) for v in point):
            raise ValueError('Explicit finite source-coordinate seeds required')
        seeds.append((3,[float(v) for v in point]))
    found={};seen=set();rejected=Counter()
    for rank,seed in seeds:
        q=[float(v) for v in snap(seed)]
        if rank==0 and navigable(current) and math.dist(current,q)<=1e-5:
            q=list(current)  # Preserve already-valid original bytes/numbers.
        key=tuple(q)
        if key in seen:continue
        seen.add(key)
        if (len(q)!=3 or not all(math.isfinite(v) for v in q) or not navigable(q)
                or math.dist(q,list(snap(q)))>1e-5):
            rejected['not_actual_native_point']+=1;continue
        delta=math.dist(q,anchor)
        if delta>sphere_m or (rank>=3 and math.hypot(q[0]-anchor[0],q[2]-anchor[2])>extra_horizontal_m):
            rejected['source_bound']+=1;continue
        if anchor_kind=='bounded_camera_projection':
            if math.hypot(q[0]-camera[0],q[2]-camera[2])>=.5 or not 0<=camera[1]-q[1]<=2:
                rejected['camera_bound']+=1;continue
        if contact(q):
            rejected['source_body_contact']+=1;continue
        if candidate_admission is not None:
            reason=candidate_admission(q)
            if reason:
                rejected['candidate_admission::'+str(reason)]+=1;continue
        label=component(q)
        item={'position':q,'rank':rank,'anchor':[float(v) for v in anchor],'anchor_kind':anchor_kind,'displacement':delta}
        if extra_seed_points or retain_seed_metadata:item['seed_position']=[float(v) for v in seed]
        if label not in found or (rank,delta,tuple(q))<(found[label]['rank'],found[label]['displacement'],tuple(found[label]['position'])):
            found[label]=item
    return {'options':found,'rejections':dict(rejected)}


def choose_common_component(options):
    if not options:return None
    common=set(options[0])
    for candidate in options[1:]:common.intersection_update(candidate)
    if not common:return None
    chosen=min(common,key=lambda c:(sum(r[c]['rank']*1000+r[c]['displacement'] for r in options),repr(c)))
    return {'component':chosen,'choices':[r[chosen] for r in options]}
