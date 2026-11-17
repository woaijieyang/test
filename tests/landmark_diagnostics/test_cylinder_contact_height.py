import unittest
import numpy as np
from cylinder_contact_height import contact_height_range
class ContactHeightTests(unittest.TestCase):
 def check_witnesses(self,tri,result,radius=.1):
  tri=np.array(tri,float)
  for key in ['minimum_point','maximum_point']:
   p=np.array(result[key]);uv,*_=np.linalg.lstsq(np.column_stack((tri[1]-tri[0],tri[2]-tri[0])),p-tri[0],rcond=None);self.assertLess(np.linalg.norm(tri[0]+uv[0]*(tri[1]-tri[0])+uv[1]*(tri[2]-tri[0])-p),1e-8);self.assertGreaterEqual(min(uv),-1e-8);self.assertLessEqual(sum(uv),1+1e-8);self.assertLessEqual(np.linalg.norm(p[[0,2]]),radius+1e-8)
 def test_horizontal_disk_inside_triangle(self):
  tri=[[-1,.005,-1],[1,.005,-1],[0,.005,1]];r=contact_height_range(tri,[0,0,0],radius=.1);self.assertAlmostEqual(r['minimum_height'],.005);self.assertAlmostEqual(r['maximum_height'],.005);self.check_witnesses(tri,r)
 def test_sloping_plane_circle_extrema(self):
  tri=[[-1,-.8,-1],[1,1.2,-1],[0,.2,1]];r=contact_height_range(tri,[0,0,0],radius=.1);self.assertAlmostEqual(r['minimum_height'],.1);self.assertAlmostEqual(r['maximum_height'],.3);self.check_witnesses(tri,r)
 def test_outside_high_vertex_is_not_contact_height(self):
  tri=[[-1,0,-1],[1,1,-1],[0,.5,1]];r=contact_height_range(tri,[0,0,0],radius=.1);self.assertAlmostEqual(r['maximum_height'],.55);self.assertAlmostEqual(r['clipped_triangle_maximum_height'],1.0);self.check_witnesses(tri,r)
 def test_vertical_plane_body_height_clip(self):
  tri=[[.05,-1,-2],[.05,-1,2],[.05,3,0]];r=contact_height_range(tri,[0,0,0],radius=.1);self.assertAlmostEqual(r['minimum_height'],1e-5);self.assertAlmostEqual(r['maximum_height'],1.5);self.check_witnesses(tri,r)
 def test_disjoint_triangle(self):
  self.assertIsNone(contact_height_range([[.2,0,-1],[.2,2,-1],[.2,0,1]],[0,0,0],radius=.1))
 def test_vertical_projection_degenerate(self):
  tri=[[-1,0,.05],[1,0,.05],[0,1,.05]];r=contact_height_range(tri,[0,0,0],radius=.1);self.assertAlmostEqual(r['maximum_height'],1);self.check_witnesses(tri,r)
if __name__=='__main__':unittest.main()
