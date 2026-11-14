"""Demand-driven evaluation of the pinned EvoMemNav clustering algorithm.

The source fit/select_frame/order remain unchanged. A split is calculated only
when source fit actually requests it. Pure split results are cached by exact
ordered input and source parameters; observation/view selection is never cached.
"""
from collections import OrderedDict
import copy
import hashlib
import sys
import numpy as np
from evomemnav.memory.view_clustering import SceneHierarchicalClustering


class ExactSplitCache:
    """Episode-owned, bounded and disposable pure-computation cache."""
    def __init__(self, max_bytes=2*1024*1024, max_entries=512):
        if type(max_bytes) is not int or max_bytes < 0:
            raise ValueError("Nonnegative cache byte limit required")
        if type(max_entries) is not int or max_entries < 0:
            raise ValueError("Nonnegative entry limit required")
        self.max_bytes=max_bytes; self.max_entries=max_entries
        self.bytes=0; self.entries=OrderedDict()
        self.metrics=dict(hits=0, misses=0, evictions=0, bypasses=0)

    def __deepcopy__(self, memo):
        # Forks may share only this pure cache, never mutable graph/view state.
        memo[id(self)]=self
        return self

    def get(self, key):
        if key not in self.entries:
            self.metrics["misses"]+=1
            return None
        value,size=self.entries.pop(key); self.entries[key]=(value,size)
        self.metrics["hits"]+=1
        return copy.deepcopy(value)

    def put(self, key, value):
        # Account keys, Python containers and owned numpy arrays. This is a
        # managed-content budget, not an allocator/RSS cap. Entry count also
        # bounds the OrderedDict table; evictions never touch durable graph data.
        value=copy.deepcopy(value)
        seen=set()
        def size_of(item):
            if id(item) in seen:return 0
            seen.add(id(item));size=sys.getsizeof(item)
            if isinstance(item,dict):
                size+=sum(size_of(k)+size_of(v) for k,v in item.items())
            elif isinstance(item,(tuple,list)):
                size+=sum(size_of(v) for v in item)
            return size
        size=128+size_of(key)+size_of(value)
        if not self.max_entries or size>self.max_bytes:
            self.metrics["bypasses"]+=1
            return
        if key in self.entries:self.bytes-=self.entries.pop(key)[1]
        while self.entries and (self.bytes+size>self.max_bytes or len(self.entries)>=self.max_entries):
            _,(_,n)=self.entries.popitem(last=False); self.bytes-=n
            self.metrics["evictions"]+=1
        self.entries[key]=(value,size); self.bytes+=size

    def clear(self):
        self.entries.clear(); self.bytes=0


class ReusableSceneClustering(SceneHierarchicalClustering):
    def __init__(self, *args, split_cache=None, split_coincident_by_view=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.split_coincident_by_view=split_coincident_by_view
        self.split_cache=split_cache if split_cache is not None else ExactSplitCache()
        self.reuse_metrics=dict(potential_kmeans=0, executed_kmeans=0, avoided_unused=0)

    def calculate_node_data(self, indices, key):
        if self.random_state is None or indices.shape[0]<=2:
            return super().calculate_node_data(indices,key)
        self.reuse_metrics["potential_kmeans"]+=1
        self.reuse_metrics["avoided_unused"]+=1
        # Source select_kid reads only split_criterion/split_permission; source
        # select_frame reads indices. Children/centres are needed only on split.
        return dict(indices=indices,left_indices=None,right_indices=None,
                    centers=None,split_criterion=indices.shape[0],
                    split_permission=True,color_key=key,dendrogram_check=False,
                    _split_pending=True)

    def split_function(self, tree, selected_node):
        node=tree.get_node(selected_node)
        if node.data.pop("_split_pending",False):
            indices=node.data["indices"]
            x=np.ascontiguousarray(self.X[indices,:])
            # Seed None consumes global randomness and is intentionally uncached.
            # Cache values contain tree indices, so their exact order is part of
            # the identity even when the point coordinates coincide.
            key=None if self.random_state is None else (
                "pinned_scene_node_v1", self.random_state, x.dtype.str,x.shape,
                hashlib.sha256(x.tobytes()).digest(),indices.dtype.str,indices.shape,
                hashlib.sha256(np.ascontiguousarray(indices).tobytes()).digest(),
                node.data["color_key"])
            data=self.split_cache.get(key) if key is not None else None
            if data is None:
                data=super().calculate_node_data(indices,node.data["color_key"])
                self.reuse_metrics["executed_kmeans"]+=1
                if key is not None:self.split_cache.put(key,data)
            self.reuse_metrics["avoided_unused"]-=1
            node.data.update(data)
        # A source KMeans split can put all coincident centres in one child.
        # Source fit then repeats forever. Reject without publishing fabricated
        # clustering; the owner retains CURRENT and records this failed attempt.
        data=node.data
        if (len(data["indices"])>1 and (len(data["left_indices"])==0
                or len(data["right_indices"])==0)):
            indices=data["indices"]
            if not self.split_coincident_by_view or not np.all(self.X[indices]==self.X[indices[0]]):
                raise ValueError("Clustering split made no progress; coincident object centres require review")
            # Geometry offers no ordering. Subdivide only the search for a covering view;
            # select_frame still checks actual co-visibility before assigning each anchor.
            midpoint=len(indices)//2
            data.update(left_indices=indices[:midpoint],right_indices=indices[midpoint:])
        return super().split_function(tree,selected_node)


    def fit(self, X, obj_ids, frames):
        # Source KMeans used to validate even unused splits. Preserve the
        # essential numerical contract before lazy selection can return early.
        X=np.asarray(X)
        if (X.ndim!=2 or X.shape[0]<1 or X.shape[1]<1
                or X.shape[0]!=len(obj_ids) or X.dtype.kind not in "fiu"
                or not np.isfinite(X).all()):
            raise ValueError("Finite nonempty numeric centres aligned with object IDs required")
        if self.split_coincident_by_view:
            observed=set().union(*(frame.full_obj_list.keys() for frame in frames.values()))
            if not set(obj_ids)<=observed:
                raise ValueError("Object lacks a covering observation")
        return super().fit(X,obj_ids,frames)
