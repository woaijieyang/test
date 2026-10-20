import unittest,math
from projected_distance_reference import projected_distance as distance
class ProjectedDistanceRegression(unittest.TestCase):
 def test_vertical_face_extension_is_not_inside(self):
  poly=[[0,0,0],[.02,0,.02],[.02,1.5,.02]]
  self.assertAlmostEqual(distance(poly,[.11,0,.11]),math.hypot(.09,.09),places=12)
  self.assertGreater(distance(poly,[.11,0,.11]),.1)
 def test_triangle_interior_and_exterior(self):
  poly=[[0,0,0],[1,0,0],[0,0,1]]
  self.assertEqual(distance(poly,[.2,0,.2]),0)
  self.assertAlmostEqual(distance(poly,[.8,0,.8]),.6/math.sqrt(2),places=12)
 def test_boundary_contact(self):
  self.assertEqual(distance([[0,0,0],[1,0,0],[0,0,1]],[.5,0,.5]),0)
 def test_projected_point(self):
  self.assertAlmostEqual(distance([[0,0,0],[0,1,0],[0,2,0]],[3,0,4]),5)
 def test_near_degenerate_triangle_does_not_have_infinite_interior(self):
  poly=[[0,0,0],[1e-10,0,0],[0,0,1e-10]]
  self.assertAlmostEqual(distance(poly,[.01,0,.01]),(.02-1e-10)/math.sqrt(2),places=12)
 def test_winding_duplicates_and_translation(self):
  poly=[[0,0,0],[1,0,0],[0,0,1]];q=[.8,0,.8];expected=distance(poly,q)
  self.assertEqual(distance(list(reversed(poly))+[poly[-1]],q),expected)
  self.assertAlmostEqual(distance([[p[0]+5,p[1]-7,p[2]-9] for p in poly],[q[0]+5,q[1]-7,q[2]-9]),expected,places=12)
if __name__=='__main__':unittest.main()
