"""TCL candidate coverage and strict split/source evidence on CPU."""
import pytest
import torch
from awarevln_memory.training.artifacts import identity
from awarevln_memory.training.cache import FeatureStore
from awarevln_memory.training.datasets import StageDataset,tcl_triplets


def observed(event_id,route,scene,dataset='r2r',partition='train',position=None):
    e=dict(event_id=event_id,route_key=route,scene=scene,dataset=dataset,
           partition=partition,source_split='train',language='en-US' if dataset=='rxr' else None,
           family=identity([scene,route]),rollout_id='r',call_id=1)
    if position is not None:e['training_position']=position
    return e


def fixture(tmp_path):
    contract={'base_identity':'base','protocol_identity':'p','source_identity':'src'}
    store=FeatureStore(tmp_path/'prompts',contract,create=True)
    a=observed('a','r2r:s1:1','s1')
    b=observed('b','r2r:s2:1','s2')
    for row in (a,b):
        meta=dict(row,augmentation_of=None)
        store.put(row['event_id'],{'prompt':torch.ones(2,8)},meta)
    meta=dict(a,augmentation_of='a')
    store.put('a::positive',{'prompt':torch.ones(2,8)},meta)
    return store,a,b


def test_cross_scene_negative_only_when_verified_train_partition(tmp_path):
    store,a,b=fixture(tmp_path)
    pairs,failures=tcl_triplets({'a':a,'b':b})
    assert not failures and len(pairs)==2
    first=next(p for p in pairs if p['anchor']=='a')
    assert first['negative_type']=='cross_scene_train_fallback'
    assert first['negative_route_key']==b['route_key']
    out=StageDataset([first],store,'tcl','train')[0]
    assert tuple(out['negative'].shape)==(2,8)


def test_no_unsafe_scene_crossing_or_val_negatives():
    a=observed('a','r2r:s1:1','s1')
    b=observed('b','r2r:s2:2','s2',partition='memory-dev')
    pairs,rejected=tcl_triplets({'a':a,'b':b})
    assert not pairs and len(rejected)==2
    b['source_split']='val_unseen'
    with pytest.raises(ValueError):tcl_triplets({'a':a,'b':b})


def test_honor_explicit_spatial_negative_and_disable_fallback():
    a=observed('a','r2r:s1:1','s1',position=[0.,0.,0.])
    b=observed('b','r2r:s1:1','s1',position=[5.,0.,0.]);b['call_id']=2
    pairs,_=tcl_triplets({'a':a,'b':b},allow_cross_scene_fallback=False)
    assert len(pairs)==2 and all(p['negative_type']=='verified_spatial_same_rollout' for p in pairs)
    missing=observed('c','r2r:s3:1','s3')
    pairs,rejected=tcl_triplets({'c':missing},allow_cross_scene_fallback=False)
    assert not pairs and rejected[0]['reason']=='NO_SPATIAL_OR_SCENE_DISJOINT_NEGATIVE'


def test_cannot_masquerade_as_same_route_negative(tmp_path):
    store,a,b=fixture(tmp_path)
    pair=next(p for p in tcl_triplets({'a':a,'b':b})[0] if p['anchor']=='a')
    wrong=dict(pair,negative_type='verified_spatial_same_rollout')
    with pytest.raises(ValueError,match='spatial negative route mismatch'):
        StageDataset([wrong],store,'tcl','train')[0]
    wrong=dict(pair,negative_scene='s1')
    with pytest.raises(ValueError,match='source mismatch'):
        StageDataset([wrong],store,'tcl','train')[0]
