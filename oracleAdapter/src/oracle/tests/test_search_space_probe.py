import unittest
from oracle.research.search_space_probe import summarize
from oracle.adapters.habitat.native import NativeState


class SearchSpaceProbeTests(unittest.TestCase):
    def test_nearby_labels_are_only_reported_not_identified(self):
        a=NativeState((0,0,0),(0,0,0,1))
        b=NativeState((1e-7,0,0),(0,0,0,1))
        d=summarize({'nodes':((a,None,None,0),(b,0,1,1)),
            'heuristics':(4.,3.),'expanded_indices':(0,1),'frontier':(), 'active_indices':(0,1)},.25)
        self.assertEqual(d['expanded_exact_poses'],2)
        self.assertEqual(d['expanded_report_only_mm_yaw001_buckets'],1)
        self.assertFalse(d['approximate_equivalence_proven'])
        self.assertEqual(d['generated_inside_original_goal_region'],0)
