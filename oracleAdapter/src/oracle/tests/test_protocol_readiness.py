import unittest
from oracle.adapters.landmark_rxr.protocol_readiness import inspect


class ProtocolReadinessTests(unittest.TestCase):
    def test_long_source_path_not_turned_into_failure(self):
        config=dict(maximum_subtrajectory_steps=10,reported_complete_tasks={'train':1},reported_subinstructions={'train':1})
        raw=dict(split='train',instruction_id=4,sub_paths=[list(range(13))],heading=0,headings=[0])
        counts,long=inspect([raw],config)
        self.assertEqual(counts['train']['subpaths_longer_than_paper_action_budget'],1)
        self.assertEqual(long[0]['result'],'NOT_A_FAILURE_VERDICT')
        self.assertNotIn('failed',counts['train'])

    def test_duplicate_source_or_missing_heading_rejected(self):
        config=dict(maximum_subtrajectory_steps=10,reported_complete_tasks={'train':1},reported_subinstructions={'train':1})
        raw=dict(split='train',instruction_id=4,sub_paths=[['a','b']],heading=0,headings=[0])
        with self.assertRaises(ValueError):inspect([raw,raw],config)
        raw['headings']=[]
        with self.assertRaises(ValueError):inspect([raw],config)
