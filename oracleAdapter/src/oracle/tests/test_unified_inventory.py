import unittest
from oracle.adapters.unified_inventory import landmark_template,pose_relation


class UnifiedInventoryTests(unittest.TestCase):
    def fixture(self):
        raw={'split':'train','instruction_id':1,'path_id':2,'scan':'scene','language':'en-US',
             'heading':1.,'headings':[1.,2.],'path':['a','b','c','d'],
             'sub_paths':[['a','b','c'],['c','d']],'sub_instructions':['one','two']}
        legacy={'task_key':'train:1','scene':'scene','heading':1.,'original_viewpoint_path':raw['path'],
                'targets':[[0,0,0],None,[1,0,0],[2,0,0]],'static_errors':['legacy_missing'],
                'segments':[],'source_record_sha256':'legacy'}
        return raw,legacy

    def test_missing_coordinate_and_original_heading_are_retained(self):
        raw,legacy=self.fixture();task=landmark_template(raw,legacy)
        self.assertIsNone(task['targets'][1])
        self.assertEqual(task['raw_heading'],1.)
        self.assertEqual(task['target_scope'],'all_original_reference_occurrences_including_landmark_boundaries')
        self.assertEqual(task['landmark_target_indices'],[2,3])
        self.assertFalse(task['coordinates_complete'])

    def test_guide_pose_mismatch_is_not_repaired_by_overwriting_start(self):
        task={'targets':[[0,0,0],[1,0,0]],'start_rotation':[0,0,0,1]}
        source={'start_position':[0,0,0],'quaternion_xyzw':[0,1,0,0]}
        result=pose_relation(task,source,1e-5,1e-5)
        self.assertFalse(result['numeric_initial_pose_match'])
        self.assertEqual(task['start_rotation'],[0,0,0,1])
