import copy,unittest
from oracle.research.global_validation import select_task


class GlobalValidationSelectionTests(unittest.TestCase):
    def fixture(self):
        t={'task_key':'train:x','dataset':'landmark_rxr','targets':[[0,0,0],[1,0,0]],'raw_heading':.2,
           'start_rotation':[0,0,0,1],'legacy_source_record_sha256':'legacy','source_record_sha256':'canonical',
           'privileges':['true_pose','official_actions'],'official_demonstration':{'actions':[1,0]},
           'method_selection':{'official_policy':'guard_then_search'},'cohort':'old'}
        body={'task_key':'train:x','status':'PASS_GLOBAL_PROPOSAL_RATIONAL_STATIC_NOT_MOTION','old_targets':t['targets'],
              'proposed_targets':[[.2,0,0],[1,0,0]],'original_heading':.2,'legacy_source_record_sha256':'legacy'}
        dense={'task_key':'train:x','old_targets':t['targets'],'proposed_targets':[[.1,0,0],[1,0,0]],
               'original_heading':.2,'source_record_sha256':'canonical'}
        return t,body,dense

    def test_source_priority_does_not_select_by_navigation_outcome(self):
        t,b,d=self.fixture();b['navigation_status']='PASS';d['navigation_status']='FAIL'
        original=copy.deepcopy(t);n=select_task(t,b,d,False,'new-source')
        self.assertEqual(n['targets'],d['proposed_targets'])
        self.assertEqual(n['global_mapping_selection']['family'],'official_dense_trace')
        self.assertNotIn('official_demonstration',n)
        self.assertEqual(t,original);self.assertEqual(n['start_rotation'],t['start_rotation'])

    def test_unchanged_tasks_keep_original_information_policy(self):
        t,b,d=self.fixture();b={'status':'UNCHANGED_BASELINE_NO_MAPPING_FAULT'}
        n=select_task(t,b,None,False,'s')
        self.assertEqual(n['targets'],t['targets']);self.assertIn('official_demonstration',n)
        self.assertEqual(n['method_selection'],t['method_selection'])

    def test_held_record_cannot_be_replaced(self):
        t,b,d=self.fixture()
        with self.assertRaises(ValueError):select_task(t,b,d,True,'s')

    def test_sealed_dataset_cannot_enter(self):
        t,b,d=self.fixture();t['dataset']='rxr'
        with self.assertRaises(ValueError):select_task(t,b,d,False,'s')
