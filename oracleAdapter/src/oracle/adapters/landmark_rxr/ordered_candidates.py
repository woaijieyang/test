"""Global monotone occurrence alignment over already identity-bound candidates.

This selects source-trace occurrences, never viewpoint identity from proximity.
All geometry/source-bound filtering must happen before this pure optimizer.
"""
import math


def align_connected_candidates(layers,allow_equal_edges):
    if not layers:raise ValueError('Nonempty route required')
    common=set(c['component'] for c in layers[0])
    for layer in layers[1:]:common.intersection_update(c['component'] for c in layer)
    trials=[]
    for component in sorted(common):
        r=align_candidates([[c for c in layer if c['component']==component] for layer in layers],allow_equal_edges)
        if r['selected'] is not None:trials.append({**r,'component':component})
    if not trials:return dict(selected=None,component=None,cost=None,common_components=sorted(common))
    return min(trials,key=lambda r:(r['cost'],r['component'],[c['source_index'] for c in r['selected']]))


def align_candidates(layers,allow_equal_edges):
    if not layers or len(allow_equal_edges)!=len(layers)-1 or any(type(x) is not bool for x in allow_equal_edges):
        raise ValueError('Explicit occurrence layers and zero-length edge rules required')
    for layer in layers:
        for c in layer:
            if (type(c['source_index']) is not int or c['source_index']<0
                    or type(c['cost']) not in (int,float) or not math.isfinite(c['cost']) or c['cost']<0
                    or len(c['position'])!=3 or not all(math.isfinite(x) for x in c['position'])):
                raise ValueError('Invalid source occurrence candidate')
    previous=[];sizes=[]
    for i,layer in enumerate(layers):
        current=[];cursor=0;best=None
        for candidate in sorted(layer,key=lambda c:(c['source_index'],c['cost'],tuple(c['position']))):
            index=candidate['source_index']
            if i==0:
                current.append((index,candidate['cost'],None,candidate));continue
            limit=index if allow_equal_edges[i-1] else index-1
            while cursor<len(previous) and previous[cursor][0]<=limit:
                item=previous[cursor]
                if best is None or (item[1],item[0])<(best[1],best[0]):best=item
                cursor+=1
            if best is not None:current.append((index,best[1]+candidate['cost'],best,candidate))
        sizes.append(len(current))
        if not current:return dict(selected=None,cost=None,failed_layer=i,reachable_candidates_per_layer=sizes)
        previous=current
    end=min(previous,key=lambda r:(r[1],r[0]));cost=end[1];chosen=[]
    while end is not None:chosen.append(end[3]);end=end[2]
    chosen.reverse()
    return dict(selected=chosen,cost=cost,failed_layer=None,reachable_candidates_per_layer=sizes)
