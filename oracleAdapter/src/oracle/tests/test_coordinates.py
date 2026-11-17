import math
import unittest
from oracle.common.coordinates import matterport_to_habitat, habitat_to_matterport, heading_quaternion_xyzw, quaternion_forward, direction_error


class Coordinates(unittest.TestCase):
    def test_axis_basis_and_round_trip_without_height_shift(self):
        self.assertEqual(matterport_to_habitat((1,0,0)),(1.,0.,0.))
        self.assertEqual(matterport_to_habitat((0,1,0)),(0.,0.,-1.))
        self.assertEqual(matterport_to_habitat((0,0,1)),(0.,1.,0.))
        point=(1.234,5.678,-9.01)
        self.assertEqual(habitat_to_matterport(matterport_to_habitat(point)),point)

    def test_clockwise_source_heading_and_quaternion_sign_equivalence(self):
        for heading in (0, math.pi/2, math.pi, 3*math.pi/2, .371):
            expected=(math.sin(heading),0.,-math.cos(heading))
            q=heading_quaternion_xyzw(heading)
            self.assertLess(direction_error(expected,quaternion_forward(q)),1e-7)
            self.assertLess(direction_error(expected,quaternion_forward(tuple(-x for x in q))),1e-7)

    def test_wrong_quaternion_order_is_detectable(self):
        q=heading_quaternion_xyzw(.371)
        self.assertGreater(direction_error(quaternion_forward(q),quaternion_forward((q[3],q[0],q[1],q[2]))),.1)

    def test_nonfinite_heading_or_invalid_rotation_rejected(self):
        with self.assertRaises(ValueError):heading_quaternion_xyzw(float('nan'))
        with self.assertRaises(ValueError):quaternion_forward((0,0,0,0))
