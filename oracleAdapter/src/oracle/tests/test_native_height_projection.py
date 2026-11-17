import unittest
from oracle.verification.native_height_projection import bounded_projection,source_bound


class NativeHeightProjectionTests(unittest.TestCase):
    def test_preserved_current_point_uses_existing_rank0_bound(self):
        self.assertTrue(source_bound([.4,0,0],[.4,0,0],[0,0,0]))
        self.assertFalse(source_bound([.4,0,0],[.3,0,0],[0,0,0]))
        self.assertFalse(source_bound([.6,0,0],[.6,0,0],[0,0,0]))
    def test_fixed_point_is_checked_without_extra_queries(self):
        calls=[]
        def step(p):calls.append(p);return [p[0],1.,p[2]]
        r=bounded_projection([0.,0.,0.],step,3)
        self.assertEqual(r['position'],[0.,1.,0.]);self.assertTrue(r['fixed'])
        self.assertEqual(len(calls),2)

    def test_cycle_stops_at_declared_bound_without_claiming_fixed(self):
        r=bounded_projection([0.,0.,0.],lambda p:[p[0],1.-p[1],p[2]],3)
        self.assertFalse(r['fixed']);self.assertEqual(len(r['steps']),3)

    def test_nonfinite_result_cannot_masquerade_as_original_valid_position(self):
        r=bounded_projection([0.,0.,0.],lambda p:[float('nan'),0,0],3)
        self.assertIsNone(r['position']);self.assertFalse(r['fixed'])
        self.assertEqual(r['failure'],'nonfinite_native_query')
