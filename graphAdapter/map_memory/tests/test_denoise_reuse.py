"""Test keep-all reuse against the original cloud algorithm, including non-eligible geometry."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/"vendor_sources/EvoMemNav"))
import copy
import numpy as np
import open3d as o3d
from graphAdapter.map_memory.perception.denoise_reuse import KeepAllClouds
from evomemnav.third_party.conceptgraph.slam.utils import denoise_objects

CFG=dict(downsample_voxel_size=.001,dbscan_remove_noise=True,dbscan_eps=.2,
         dbscan_min_points=5,spatial_sim_type='overlap')

def cloud(xyz, colors):
    p=o3d.geometry.PointCloud()
    p.points=o3d.utility.Vector3dVector(xyz)
    p.colors=o3d.utility.Vector3dVector(colors)
    return p

def check(cache,xyz,colors,cfg=CFG,limit=65536):
    actual={1:dict(pcd=cloud(xyz,colors))}
    expected=copy.deepcopy(actual)
    denoise_objects(**cfg,device='cpu',objects=expected)
    metrics=cache.apply(actual,cfg,limit)
    for field,attrs in [('pcd',['points','colors']),('bbox',['center','R','extent','color'])]:
        for attr in attrs:
            a,b=[np.asarray(getattr(row[1][field],attr)) for row in (actual,expected)]
            np.testing.assert_array_equal(a,b)
    return metrics

def test_exact_multiset_retains_current_order_and_colors_and_invalidates():
    rng=np.random.default_rng(45);xyz=rng.uniform(0,.06,(60,3));rgb=rng.random((60,3))
    cache=KeepAllClouds()
    assert check(cache,xyz,rgb)['hits']==0
    assert check(cache,xyz[::-1],1-rgb[::-1])['hits']==1
    fork=cache.fork()
    assert check(fork,xyz+.001,rgb)['hits']==0
    assert check(cache,xyz,rgb)['hits']==1
    assert check(cache,xyz,rgb,dict(CFG,dbscan_eps=.15))['hits']==0
    assert check(cache,xyz,rgb,dict(CFG,dbscan_min_points=2))['hits']==0
    assert check(cache,xyz,rgb,limit=1)['retained_bytes']==0
    assert fork.apply({},CFG,65536)['retained_bytes']==0

def test_noise_removal_is_never_replayed_as_keep_all():
    rng=np.random.default_rng(71)
    xyz=np.vstack((rng.uniform(0,.05,(55,3)),rng.uniform(2,2.05,(14,3))))
    rgb=rng.random(xyz.shape)
    cache=KeepAllClouds()
    for order in [slice(None),slice(None,None,-1)]:
        stats=check(cache,xyz[order],rgb[order])
        assert stats['hits']==0 and stats['retained_bytes']==0
