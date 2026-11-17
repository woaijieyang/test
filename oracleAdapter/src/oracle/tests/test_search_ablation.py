import unittest
from oracle.research.search_ablation import remove_action_information,physical_identity


class SearchAblation(unittest.TestCase):
    def test_remove_official_information_without_changing_physical_task(self):
        task={'scene':'s','targets':[[0,0,0],[1,0,0]],'start_rotation':[0,0,0,1],
              'profile_path':'p','profile_sha256':'h','geometry_catalog_sha256':'g',
              'purpose':'landmark_order_execution','objective':'visit_landmark_occurrences_in_order',
              'privileges':['true_pose','official_actions','landmark_annotations'],
              'official_demonstration':{'actions':[1,0]},'historical_replay_status':'PASS'}
        stripped=remove_action_information(task)
        self.assertNotIn('official_demonstration',stripped)
        self.assertNotIn('official_actions',stripped['privileges'])
        self.assertNotIn('historical_replay_status',stripped)
        self.assertEqual(physical_identity(task),physical_identity(stripped))
        self.assertIn('official_demonstration',task)
