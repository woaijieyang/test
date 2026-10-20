import unittest,math
from bounded_camera_seed import select_camera_seed
class PF:
 def __init__(self,q,nav=True):self.q=q;self.nav=nav
 def snap_point(self,p):return self.q
 def is_navigable(self,p):return self.nav
class Tests(unittest.TestCase):
 def test_valid_same_bounds(self):self.assertEqual(select_camera_seed(PF([0,0,0]),[0,1.5,0]),[0,0,0])
 def test_invalid_not_silently_projected(self):
  for q in [[.5,0,0],[0,-.501,0],[0,1.6,0],[math.nan,0,0]]:
   with self.subTest(q=q):self.assertIsNone(select_camera_seed(PF(q),[0,1.5,0]))
  self.assertIsNone(select_camera_seed(PF([0,0,0],False),[0,1.5,0]))
 def test_unstable_snap_rejected(self):
  class Moving:
   def snap_point(self,p):return [p[0]+.001,0,p[2]]
   def is_navigable(self,p):return True
  self.assertIsNone(select_camera_seed(Moving(),[0,1.5,0]))
if __name__=='__main__':unittest.main()
