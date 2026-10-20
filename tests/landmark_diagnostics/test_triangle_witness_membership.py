import unittest,math
from triangle_witness_membership import witness_membership as check
class MembershipTests(unittest.TestCase):
 def test_triangle_interior_and_edge(self):
  for p in [[.2,.3,0.],[.5,.5,0.]]:
   r=check([[0,0,0],[1,0,0],[0,1,0]],p);self.assertEqual(r["kind"],"triangle");self.assertGreaterEqual(r["minimum_barycentric"],0);self.assertEqual(r["residual_m"],0)
 def test_outside_triangle_is_not_interior(self):
  r=check([[0,0,0],[1,0,0],[0,1,0]],[1,1,0]);self.assertLess(r["minimum_barycentric"],0)
 def test_off_plane_distance(self):
  r=check([[0,0,0],[1,0,0],[0,1,0]],[.2,.2,.0001]);self.assertAlmostEqual(r["residual_m"],.0001)
 def test_duplicate_vertices_segment_and_outside(self):
  tri=[[0,0,0],[1,2,3],[1,2,3]];r=check(tri,[.25,.5,.75]);self.assertEqual(r["kind"],"segment");self.assertEqual(r["residual_m"],0);self.assertGreater(check(tri,[2,4,6])["residual_m"],1)
 def test_distinct_collinear_vertices(self):
  r=check([[0,0,0],[1,0,0],[2,0,0]],[1.5,.01,0]);self.assertEqual(r["kind"],"segment");self.assertAlmostEqual(r["residual_m"],.01)
 def test_point_degeneracy(self):
  r=check([[1,2,3]]*3,[2,3,4]);self.assertEqual(r["kind"],"point");self.assertAlmostEqual(r["residual_m"],math.sqrt(3))
 def test_float_gram_cancellation_not_degeneracy(self):
  tri=[[0,0,0],[1,0,1],[1,1e-10,1]];r=check(tri,[.75,2.5e-11,.75]);self.assertEqual(r["kind"],"triangle");self.assertGreaterEqual(r["minimum_barycentric"],0);self.assertLess(r["residual_m"],1e-20)
 def test_nonfinite_rejected(self):
  with self.assertRaises(ValueError):check([[0,0,0]]*3,[math.nan,0,0])
if __name__=="__main__":unittest.main()
