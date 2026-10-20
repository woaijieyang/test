import unittest
import numpy as np
from bounded_triangle_projection import closest_in_horizontal_disk
class BoundedTriangleTests(unittest.TestCase):
 def test_horizontal_interior(self):
  q=closest_in_horizontal_disk([[-1,0,-1],[1,0,-1],[0,0,1]],[0,.2,0]);np.testing.assert_allclose(q,[0,0,0],atol=1e-12)
 def test_sloped_circle_boundary(self):
  # Plane y=2x+1: unconstrained nearest x=-.4 is outside radius.35.
  q=closest_in_horizontal_disk([[-1,-1,-1],[1,3,-1],[0,1,1]],[0,0,0]);np.testing.assert_allclose(q,[-.35,.3,0],atol=1e-10)
 def test_horizontal_disjoint(self):
  self.assertIsNone(closest_in_horizontal_disk([[1,0,0],[2,0,0],[1,0,1]],[0,0,0]))
 def test_vertical_clipped_edge(self):
  q=closest_in_horizontal_disk([[.2,0,0],[.6,0,0],[.6,2,0]],[0,1,0],radius=.25);np.testing.assert_allclose(q,[.25,.25,0],atol=1e-10)
 def test_degenerate_segment(self):
  q=closest_in_horizontal_disk([[-1,0,0],[0,0,0],[1,0,0]],[0,.2,0]);np.testing.assert_allclose(q,[0,0,0],atol=1e-12)
 def test_corner_constrained_by_triangle(self):
  q=closest_in_horizontal_disk([[.2,0,.1],[.6,0,.1],[.2,0,.6]],[0,1,0]);np.testing.assert_allclose(q,[.2,0,.1],atol=1e-10)
if __name__=='__main__':unittest.main()
