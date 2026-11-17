import unittest,math
from swept_cylinder_reference import triangle_linear_sweep_distance as distance
class SweptCylinderReferenceTests(unittest.TestCase):
 def test_stationary_wall_distance(self):
  self.assertAlmostEqual(distance([[.2,.1,-.5],[.2,1.4,.5],[.2,.1,.5]],[0,0,0],[0,0,0]),.2)
 def test_wall_hit_between_clear_endpoints(self):
  tri=[[0,.1,-.5],[0,1.4,.5],[0,.1,.5]]
  self.assertGreater(distance(tri,[-.2,0,0],[-.2,0,0]),.1)
  self.assertGreater(distance(tri,[.2,0,0],[.2,0,0]),.1)
  self.assertEqual(distance(tri,[-.2,0,0],[.2,0,0]),0)
 def test_triangle_above_body(self):
  self.assertTrue(math.isinf(distance([[-1,2,-1],[1,2,0],[-1,2,1]],[0,0,0],[.25,0,0])))
 def test_vertical_sweep_hits_ceiling(self):
  self.assertEqual(distance([[-1,1.6,-1],[1,1.6,0],[-1,1.6,1]],[0,0,0],[0,.2,0]),0)
 def test_alternative_step_curve_is_different_not_a_gate_change(self):
  tri=[[-1,.2,-1],[0,.2,1],[0,.2,-1]];a=[-.1,.2,0];b=[.15,0,0];corner=[.15,.2,0]
  self.assertLess(distance(tri,a,b),.1)
  self.assertGreaterEqual(distance(tri,a,corner),.1)
  self.assertGreaterEqual(distance(tri,corner,b),.1)
 def test_reverse_sweep_same_volume(self):
  tri=[[0,.1,-.5],[0,1.4,.5],[0,.1,.5]];a=[-.2,.05,.1];b=[.2,.15,-.1]
  self.assertAlmostEqual(distance(tri,a,b),distance(tri,b,a))
if __name__=='__main__':unittest.main()
