import unittest
from oracle.verification.linear_sweep import triangle_linear_sweep_distance
from oracle.verification.contact_certificate import linear_sweep_witness, verify_witness


class GeometryCertificates(unittest.TestCase):
    def test_middle_of_step_contact_has_checkable_certificate(self):
        triangle = [[0., .4, -.05], [0., .4, .05], [0., 1., 0.]]
        start, end = [-.3, 0., 0.], [.3, 0., 0.]
        self.assertGreater(triangle_linear_sweep_distance(triangle, start, start), .1)
        self.assertGreater(triangle_linear_sweep_distance(triangle, end, end), .1)
        self.assertLess(triangle_linear_sweep_distance(triangle, start, end), .1)
        witness = linear_sweep_witness(triangle, start, end)
        self.assertTrue(verify_witness(triangle, start, end, witness))
        witness["exact_time"] = [2, 1]
        with self.assertRaises(AssertionError):
            verify_witness(triangle, start, end, witness)

    def test_ground_support_is_not_body_penetration_in_fixed_slab(self):
        triangle = [[-1., 0., -1.], [1., 0., -1.], [0., 0., 1.]]
        self.assertEqual(triangle_linear_sweep_distance(triangle, [0., 0., 0.], [.25, 0., 0.]), float("inf"))

    def test_nonfinite_geometry_is_not_accepted(self):
        with self.assertRaises(ValueError):
            triangle_linear_sweep_distance([[float("nan"), 1., 0.]] * 3, [0.] * 3, [0.] * 3)


if __name__ == "__main__":
    unittest.main()
