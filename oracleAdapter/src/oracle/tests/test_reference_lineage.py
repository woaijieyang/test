import unittest
from oracle.adapters.landmark_rxr.reference_lineage import correspond


class ReferenceLineageTests(unittest.TestCase):
    def fixture(self):
        raw=dict(split='train',instruction_id=12,path_id=3,scan='s',language='en-US',
                 path=['a','b','a'],sub_paths=[['a','b'],['b','a']])
        ce=dict(split='train',instruction_id='12',path_id='3',scene='s',language='en-US',episode_id=9,
                reference_path=[[0,0,0],[1,0,0],[0,0,0]])
        return raw,ce

    def test_distinct_occurrences_survive_same_id_and_position(self):
        raw,ce=self.fixture();r=correspond(raw,ce)
        self.assertEqual([o['index'] for o in r['occurrences']],[0,1,2])
        self.assertEqual(r['subpath_intervals'],[[0,1],[1,2]])
        self.assertEqual(r['repeated_ids'],1)

    def test_wrong_scene_and_length_do_not_gain_ordinal_mapping(self):
        raw,ce=self.fixture();ce['scene']='other'
        self.assertEqual(correspond(raw,ce)['status'],'IDENTITY_MISMATCH')
        raw,ce=self.fixture();ce['reference_path'].pop()
        self.assertEqual(correspond(raw,ce)['status'],'REFERENCE_LENGTH_MISMATCH')

    def test_zero_length_keeps_both_source_occurrences(self):
        raw,ce=self.fixture();ce['reference_path'][1]=[0,0,0]
        r=correspond(raw,ce)
        self.assertEqual(r['consecutive_zero_length'],2)
        self.assertEqual(len(r['occurrences']),3)
