import unittest
from oracle.research.soft_priority_study import method_pair
from oracle.research.priority_study import comparable_methods


class SoftPriorityStudyTests(unittest.TestCase):
    def test_only_fixed_soft_penalty_differs(self):
        cfg={'position_cell_m':.001,'yaw_cell_degrees':.001,'maximum_priority_weight':2.}
        pair=method_pair({'state_key':'lossless_pose','search_priority_weight':1.,'max_expansions_per_search':5000},cfg)
        self.assertTrue(comparable_methods(pair,'soft_priority'))
        pair[1]['max_expansions_per_search']=5001
        self.assertFalse(comparable_methods(pair,'soft_priority'))

    def test_soft_study_cannot_hide_uniform_weight_or_key_change(self):
        a={'id':'a','state_key':'lossless_pose','search_priority_weight':1.}
        b={**a,'id':'b','search_priority_weight':2.}
        self.assertFalse(comparable_methods([a,b],'soft_priority'))
        with self.assertRaises(ValueError):comparable_methods([a,b],'unknown')
