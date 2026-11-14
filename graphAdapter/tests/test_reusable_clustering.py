import copy
from types import SimpleNamespace
import numpy as np
import pytest
from evomemnav.memory.view_clustering import SceneHierarchicalClustering
from graphAdapter.map_memory.perception.reusable_clustering import ExactSplitCache, ReusableSceneClustering


def frames_for(ids,groups):
    return {str(i):SimpleNamespace(full_obj_list={j:float((j%7)+1)/10 for j in group},cluster=[])
            for i,group in enumerate(groups)}


def result(model,x,ids,frames):
    found=model.fit(x,ids,copy.deepcopy(frames))
    return [(key,list(view.cluster),dict(view.full_obj_list)) for key,view in found.items()]


def test_original_oracle_many_coverage_and_order_patterns():
    rng=np.random.default_rng(339)
    cases=0
    for n in (1,2,3,6,12,21):
        for trial in range(6):
            ids=list(rng.permutation(np.arange(n)+100))
            x=rng.normal(size=(n,2))
            if trial==1:x[:]=0
            if trial==2:x[:,1]=0
            groups=[[j] for j in ids]
            if trial in (0,1,3):groups.append(ids[:])
            else:
                groups.extend([list(rng.choice(ids,size=max(1,n//2),replace=False)) for _ in range(n)])
            frames=frames_for(ids,groups)
            baseline=result(SceneHierarchicalClustering(random_state=66),x,ids,frames)
            candidate=ReusableSceneClustering(random_state=66)
            assert result(candidate,x,ids,frames)==baseline
            assert result(candidate,x,ids,frames)==baseline
            cases+=1
    assert cases==36


def test_covering_view_avoids_all_unused_kmeans(monkeypatch):
    import evomemnav.memory.view_clustering as source
    original=source.KMeans; calls=[]
    def counted(*a,**kw):calls.append(kw);return original(*a,**kw)
    monkeypatch.setattr(source,'KMeans',counted)
    x=np.random.default_rng(2).normal(size=(20,2));ids=list(range(20));frames=frames_for(ids,[ids])
    expected=result(SceneHierarchicalClustering(random_state=66),x,ids,frames)
    assert len(calls)==1
    calls.clear();model=ReusableSceneClustering(random_state=66)
    assert result(model,x,ids,frames)==expected
    assert calls==[] and model.reuse_metrics['avoided_unused']==1


def test_exact_splits_hit_but_new_view_is_reselected(monkeypatch):
    import evomemnav.memory.view_clustering as source
    original=source.KMeans;calls=[]
    def counted(*a,**kw):calls.append(kw);return original(*a,**kw)
    monkeypatch.setattr(source,'KMeans',counted)
    x=np.random.default_rng(9).normal(size=(15,2));ids=list(range(15));frames=frames_for(ids,[[j] for j in ids])
    model=ReusableSceneClustering(random_state=66)
    expected=result(model,x,ids,frames);assert calls
    calls.clear();assert result(model,x,ids,frames)==expected;assert calls==[]
    assert model.split_cache.metrics['hits']>0
    frames['fresh']=SimpleNamespace(full_obj_list={j:1. for j in ids},cluster=[])
    assert result(model,x,ids,frames)==result(SceneHierarchicalClustering(random_state=66),x,ids,frames)
    assert result(model,x,ids,frames)[0][0]=='fresh'
    old_misses=model.split_cache.metrics['misses'];x[0,0]+=1e-7
    result(model,x,ids,frames_for(ids,[[j] for j in ids]))
    assert model.split_cache.metrics['misses']>old_misses


def test_cache_bounds_defensive_copies_and_fork_sharing():
    cache=ExactSplitCache(max_bytes=2500,max_entries=1)
    value=dict(indices=np.arange(3),split_permission=True)
    cache.put('a',value);value['indices'][0]=42
    got=cache.get('a');assert got['indices'][0]==0
    got['indices'][0]=27;assert cache.get('a')['indices'][0]==0
    cache.put('b',dict(indices=np.arange(4)));assert cache.get('a') is None
    assert cache.bytes<=2500 and len(cache.entries)==1
    cache.put('large',dict(indices=np.arange(1000)));assert cache.metrics['bypasses']==1
    model=ReusableSceneClustering(random_state=66,split_cache=cache)
    fork=copy.deepcopy(model);assert fork.split_cache is cache
    assert fork.reuse_metrics is not model.reuse_metrics
    cache.clear();assert cache.bytes==0 and not cache.entries
    with pytest.raises(ValueError):ExactSplitCache(max_bytes=-1)


def test_seed_none_preserves_source_randomness_and_bypasses_cache():
    x=np.random.default_rng(4).normal(size=(9,2));ids=list(range(9));frames=frames_for(ids,[[i] for i in ids])
    original=SceneHierarchicalClustering(random_state=None);candidate=ReusableSceneClustering(random_state=None)
    np.random.seed(88);expected=result(original,x,ids,frames);state=np.random.get_state()
    np.random.seed(88);actual=result(candidate,x,ids,frames);after=np.random.get_state()
    assert actual==expected
    assert np.array_equal(state[1],after[1]) and state[2:]==after[2:]
    assert not candidate.split_cache.entries


def test_coincident_centres_without_cover_fail_instead_of_looping():
    x=np.zeros((5,2));ids=list(range(5));frames=frames_for(ids,[[i] for i in ids])
    original=SceneHierarchicalClustering(random_state=66);original.X=x
    split=original.calculate_node_data(np.arange(5),0)
    assert len(split['left_indices'])==0 or len(split['right_indices'])==0
    with pytest.raises(ValueError,match='no progress'):
        result(ReusableSceneClustering(random_state=66),x,ids,frames)


def test_cache_lifetime_has_no_global_episode_owner():
    import weakref,gc
    model=ReusableSceneClustering(random_state=66)
    ref=weakref.ref(model.split_cache)
    fork=copy.deepcopy(model)
    del model;gc.collect();assert ref() is not None
    del fork;gc.collect();assert ref() is None


@pytest.mark.parametrize('x',[np.array([[0.,0.],[np.nan,0.],[1.,1.]]),
    np.array([[0.,0.],[np.inf,0.],[1.,1.]]),np.empty((3,0)),np.zeros(3),np.zeros((2,2))])
def test_covering_view_does_not_bypass_input_validity(x):
    ids=list(range(3));frames=frames_for(ids,[ids])
    with pytest.raises(ValueError,match='Finite nonempty'):
        result(ReusableSceneClustering(random_state=66),x,ids,frames)



def test_coincident_view_fallback_only_assigns_observed_objects():
    ids=list(range(5));x=np.zeros((5,2))
    frames=frames_for(ids,[[0,1],[2],[3,4]])
    clustered=result(ReusableSceneClustering(random_state=66,split_coincident_by_view=True),x,ids,frames)
    assigned=[]
    for uid,objects,visible in clustered:
        assert set(objects)<=set(visible)
        assigned.extend(objects)
    assert sorted(assigned)==ids
    with pytest.raises(ValueError,match="covering observation"):
        result(ReusableSceneClustering(random_state=66,split_coincident_by_view=True),x,ids,frames_for(ids,[[0,1]]))
