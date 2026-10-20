import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from motion_audit import motion_violations
class MotionBounds(unittest.TestCase):
 def test_valid_stair_forward(self):
  self.assertEqual(motion_violations([[0,0,0],[.25,.3,0]],[1]),[])
 def test_offmesh_lateral_jump_rejected(self):
  self.assertEqual(len(motion_violations([[0,0,0],[.06,0,.69]],[1])),1)
 def test_turn_cannot_translate(self):
  self.assertEqual(len(motion_violations([[0,0,0],[.1,0,0]],[2])),1)
 def test_cross_floor_jump_rejected(self):
  self.assertEqual(len(motion_violations([[0,0,0],[.1,3,0]],[1])),1)
