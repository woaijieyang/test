import copy,unittest
from oracle.research.detail_scene_validation import candidate_task,may_repair_targets


class DetailSceneTests(unittest.TestCase):
    def test_official_action_tasks_are_preserved_before_proposal_generation(self):
        self.assertTrue(may_repair_targets({'method_selection':{'official_policy':'none'}},False))
        self.assertFalse(may_repair_targets({'method_selection':{'official_policy':'guard_then_search'}},False))
        self.assertFalse(may_repair_targets({'method_selection':{'official_policy':'none'}},True))
    def test_source_identity_order_heading_and_missing_points_preserved(self):
        old={'dataset':'landmark_rxr','scene':'pRbA3pwrgk9','task_key':'train:1','targets':[[0,0,0],None],
             'start_rotation':[0,0,0,1],'original_viewpoint_path':['a','b'],'method_selection':{'official_policy':'none'},
             'global_mapping_selection':{'family':'unchanged'},'profile_path':'old','profile_sha256':'old','module_source_sha256':'old','cohort':'old'}
        saved=copy.deepcopy(old);new=candidate_task(old,[[0,.01,0],None],'new','profile','source')
        self.assertEqual(old,saved);self.assertEqual(new['original_viewpoint_path'],['a','b']);self.assertEqual(new['start_rotation'],old['start_rotation']);self.assertIsNone(new['targets'][1])
        self.assertEqual(new['global_mapping_selection']['parent_selection'],old['global_mapping_selection'])

    def test_cannot_drop_occurrence_or_silently_change_official_action_information(self):
        old={'dataset':'landmark_rxr','scene':'pRbA3pwrgk9','task_key':'train:1','targets':[[0,0,0]],'method_selection':{'official_policy':'guard_then_search'},'global_mapping_selection':{}}
        with self.assertRaises(ValueError):candidate_task(old,[],'new','p','s')
        with self.assertRaises(ValueError):candidate_task(old,[[0,.1,0]],'new','p','s')
