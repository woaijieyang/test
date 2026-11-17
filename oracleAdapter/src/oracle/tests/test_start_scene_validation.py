import copy
import unittest
from oracle.research.start_scene_validation import repaired_task


class StartSceneValidation(unittest.TestCase):
    def data(self):
        task=dict(dataset='landmark_rxr',scene='oLBMNvg9in8',task_key='val_unseen:1',targets=[[0,0,0],[1,0,0]],
                  raw_heading=.3,start_rotation=[0,0,0,1],method_selection={'official_policy':'none'},
                  module_source_sha256='old',cohort='old',original_viewpoint_path=['a','b'])
        proposal=dict(old_targets=copy.deepcopy(task['targets']),proposed_targets=[[.1,0,0],[1,0,0]],
                      original_heading=.3,start_rotation=[0,0,0,1],original_anchor=[0,0,0])
        return task,proposal

    def test_only_initial_target_and_execution_provenance_change(self):
        task,p=self.data();saved=copy.deepcopy(task);new=repaired_task(task,p,'new')
        self.assertEqual(task,saved);self.assertEqual(new['targets'][1:],task['targets'][1:])
        self.assertEqual(new['start_rotation'],task['start_rotation'])
        self.assertEqual(new['original_viewpoint_path'],task['original_viewpoint_path'])

    def test_noninitial_change_or_silent_official_prior_is_rejected(self):
        task,p=self.data();p['proposed_targets'][1]=[2,0,0]
        with self.assertRaises(ValueError):repaired_task(task,p,'new')
        task,p=self.data();task['official_demonstration']={'actions':[1]}
        with self.assertRaises(ValueError):repaired_task(task,p,'new')
