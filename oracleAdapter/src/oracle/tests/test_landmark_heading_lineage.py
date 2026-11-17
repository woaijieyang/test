import unittest
from oracle.adapters.landmark_rxr.heading_lineage import heading_facts


class LandmarkHeadingLineage(unittest.TestCase):
    def test_numeric_wrap_difference_is_not_orientation_difference(self):
        import math
        row=heading_facts({'heading':0.,'headings':[2*math.pi],'sub_paths':[['a','b']],'sub_instructions':['x']},0.)
        self.assertFalse(row['header_exactly_equal_to_first_subheading'])
        self.assertLess(row['header_first_subheading_difference_if_radians'],1e-10)

    def test_landmark_heading_not_replaced_by_guide(self):
        raw={'heading':1.,'headings':[1.,2.],'sub_paths':[['a','b'],['b','c']],'sub_instructions':['x','y']}
        result=heading_facts(raw,3.)
        self.assertEqual(result['landmark_heading'],1.)
        self.assertFalse(result['header_exactly_equal_to_guide'])
        self.assertTrue(result['header_exactly_equal_to_first_subheading'])
        self.assertTrue(result['one_heading_per_subpath'])
        self.assertFalse(result['automatic_heading_replacement'])

    def test_missing_subheading_is_reported_not_filled(self):
        result=heading_facts({'heading':1.,'headings':[],'sub_paths':[['a','b']],'sub_instructions':['x']},1.)
        self.assertFalse(result['one_heading_per_subpath'])
        self.assertIsNone(result['header_exactly_equal_to_first_subheading'])
