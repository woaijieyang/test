import unittest
import numpy as np
from oracle.verification.source_scene import SourceScene
from oracle.planners.collision_queries import CachedSourceQueries


def fixture():
    s=SourceScene.__new__(SourceScene);s.np=np
    s.triangles=np.array([[[0.,.4,-.05],[0.,.4,.05],[0.,1.,0.]],
        [[-1.,0.,-1.],[1.,0.,-1.],[1.,0.,1.]],
        [[3.,.6,3.],[3.1,1.,3.],[3.,1.5,3.1]]])
    s.low,s.high=s.triangles.min(axis=1),s.triangles.max(axis=1)
    s.protocol={'body_height_m':1.5,'body_radius_m':.1,'foot_epsilon_m':1e-5,'radial_epsilon_m':1e-6}
    s.geometry_sha256='geometry';s.scene_sha256='scene';s.queries=s.triangle_checks=0
    return s


class CollisionQueryCacheTests(unittest.TestCase):
    def cache(self,s):
        return CachedSourceQueries(s,context_digest='frozen-task-and-protocol',cell_size_m=.5,
            max_regions=2,max_queries=3)

    def test_exact_positive_negative_queries_and_certificates_equal_uncached(self):
        s=fixture();c=self.cache(s)
        for a,b in [([-.3,0,0],[.3,0,0]),([0,0,1],[.25,0,1]),
                    ([3,.2,3],[3.25,.1,3]),([-.6,-.1,-.6],[-.4,.1,-.4])]:
            for certificate in [False,True]:
                for arithmetic in ['float_projection','rational_hull']:
                    self.assertEqual(s.contact(a,b,certificate,arithmetic),c.contact(a,b,certificate,arithmetic))
                    self.assertEqual(s.contact(a,b,certificate,arithmetic),c.contact(a,b,certificate,arithmetic))
        self.assertGreater(c.metrics['query_cache_hits'],0)
        self.assertLessEqual(len(c.query_cache),3);self.assertLessEqual(len(c.region_cache),2)

    def test_cache_hit_cannot_skip_requested_rational_certificate(self):
        s=fixture();c=self.cache(s);a,b=[-.3,0,0],[.3,0,0]
        first=c.contact(a,b);self.assertNotIn('witness',first)
        second=c.contact(a,b,certificate=True);self.assertIn('witness',second)
        second['triangle']=999
        self.assertEqual(c.contact(a,b,certificate=True)['triangle'],0)

    def test_protocol_drift_cannot_reuse_old_cache(self):
        c=self.cache(fixture());c.contact([0,0,1],[.25,0,1]);c.protocol['body_radius_m']=.2
        with self.assertRaises(ValueError):c.contact([0,0,1],[.25,0,1])

    def test_unchanged_queries_avoid_repeated_full_scene_broadphase(self):
        c=self.cache(fixture())
        for _ in range(5):self.assertIsNone(c.contact([0,0,1],[.25,0,1]))
        self.assertEqual(c.metrics['full_scene_broadphase_scans'],1)
        self.assertEqual(c.metrics['query_cache_hits'],4)
