import unittest
from oracle.verification.contact_surface_geometry import describe_triangle


class ContactSurfaceGeometryTests(unittest.TestCase):
    def test_horizontal_face_above_center_is_not_called_legal_support(self):
        d=describe_triangle([[-1,.1,-1],[1,.1,-1],[0,.1,1]],[0,0,0])
        self.assertAlmostEqual(d['slope_degrees'],0)
        self.assertAlmostEqual(d['plane_height_at_center_minus_foot_m'],.1)
        self.assertTrue(d['center_projection_inside_triangle'])
        self.assertFalse(d['legal_support_proven'])

    def test_vertical_face_has_no_height_graph(self):
        d=describe_triangle([[0,0,0],[0,1,0],[0,0,1]],[.05,0,.1])
        self.assertAlmostEqual(d['slope_degrees'],90)
        self.assertIsNone(d['plane_height_at_center_minus_foot_m'])

    def test_sloped_plane_through_foot_is_distinct_from_height_offset(self):
        d=describe_triangle([[-1,-1,-1],[1,1,-1],[0,0,1]],[0,0,0])
        self.assertAlmostEqual(d['slope_degrees'],45)
        self.assertAlmostEqual(d['plane_height_at_center_minus_foot_m'],0)
        self.assertTrue(d['center_projection_inside_triangle'])
