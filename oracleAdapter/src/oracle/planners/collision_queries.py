"""Per-task planning-query acceleration; execution/replay stay uncached.

Only candidate selection is coarsened. Exact slab/sweep checks and triangle
order remain unchanged. Query keys preserve all endpoint bits and proof mode.
"""
from collections import OrderedDict
from copy import deepcopy
import math

from oracle.verification.source_scene import SourceScene


class CachedSourceQueries(SourceScene):
    def __init__(self, source, *, context_digest, cell_size_m, max_regions, max_queries):
        if (not context_digest or not math.isfinite(cell_size_m) or cell_size_m <= 0
                or any(type(n) is not int or n < 1 for n in (max_regions,max_queries))):
            raise ValueError('Explicit cache identity and positive bounds required')
        # Shared frozen geometry, separate counters and configuration. No simulator.
        for name in ('np','triangles','low','high','geometry_sha256','scene_sha256'):
            setattr(self,name,getattr(source,name))
        self.protocol = dict(source.protocol)
        self._bound_protocol = dict(source.protocol)
        self._context = (context_digest,source.geometry_sha256,source.scene_sha256)
        self.cell_size_m = cell_size_m
        self.max_regions,self.max_queries = max_regions,max_queries
        self.region_cache,self.query_cache = OrderedDict(),OrderedDict()
        self.queries = self.triangle_checks = 0
        self.metrics = dict(query_cache_hits=0,region_cache_hits=0,full_scene_broadphase_scans=0,
                            query_evictions=0,region_evictions=0)

    def _broadphase_indices(self, low, high, radius, height, foot):
        np = self.np
        c0=tuple(np.floor(low/self.cell_size_m).astype(int))
        c1=tuple(np.floor(high/self.cell_size_m).astype(int))
        key=(c0,c1)
        if key in self.region_cache:
            self.metrics['region_cache_hits']+=1
            candidates=self.region_cache.pop(key)
        else:
            self.metrics['full_scene_broadphase_scans']+=1
            lower=np.asarray(c0)*self.cell_size_m
            upper=(np.asarray(c1)+1)*self.cell_size_m
            candidates=super()._broadphase_indices(lower,upper,radius,height,foot)
        self.region_cache[key]=candidates
        if len(self.region_cache)>self.max_regions:
            self.region_cache.popitem(last=False);self.metrics['region_evictions']+=1
        lo,hi=self.low[candidates],self.high[candidates]
        mask=((lo[:,0]<high[0]+radius)&(hi[:,0]>low[0]-radius)
              &(lo[:,2]<high[2]+radius)&(hi[:,2]>low[2]-radius)
              &(lo[:,1]<high[1]+height)&(hi[:,1]>low[1]+foot))
        return candidates[mask]

    def contact(self,start,end,certificate=False,arithmetic='float_projection'):
        if self.protocol!=self._bound_protocol:
            raise ValueError('Source query protocol changed after binding')
        a,b=tuple(float(x) for x in start),tuple(float(x) for x in end)
        if len(a)!=3 or len(b)!=3 or not all(math.isfinite(v) for v in a+b):
            raise ValueError('Finite xyz query endpoints required')
        key=(self._context,tuple(v.hex() for v in a+b),bool(certificate),arithmetic)
        if key in self.query_cache:
            self.queries+=1;self.metrics['query_cache_hits']+=1
            value=self.query_cache.pop(key);self.query_cache[key]=value
            return deepcopy(value)
        value=super().contact(a,b,certificate,arithmetic)
        self.query_cache[key]=deepcopy(value)
        if len(self.query_cache)>self.max_queries:
            self.query_cache.popitem(last=False);self.metrics['query_evictions']+=1
        return value
