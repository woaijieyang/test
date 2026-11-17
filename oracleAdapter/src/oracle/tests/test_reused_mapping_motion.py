import unittest
from oracle.research.reused_mapping_motion import bind_reused_task


class ReusedMappingMotionTests(unittest.TestCase):
    def fixture(self):
        t={'task_key':'train:x','dataset':'landmark_rxr','targets':[[0,0,0],[1,0,0]],'raw_heading':.2,
           'legacy_source_record_sha256':'legacy','source_record_sha256':'canonical','privileges':['true_pose','official_actions'],
           'official_demonstration':{'actions':[1,0]}}
        r={'task_key':'train:x','status':'PASS_REUSED_PROPOSAL_RATIONAL_STATIC_NOT_MOTION',
           'potential_strict_endpoint_repair':True,'old_targets':t['targets'],'proposed_targets':[[.1,0,0],[1,0,0]],
           'original_heading':.2,'raw_source_record_sha256':'legacy'}
        return t,r

    def test_distinguishes_historical_hash_encoding_and_preserves_identity(self):
        t,r=self.fixture();n=bind_reused_task(t,r,'sources')
        self.assertEqual(n['source_record_sha256'],'canonical')
        self.assertEqual(n['legacy_source_record_sha256'],'legacy')
        self.assertEqual(n['targets'],r['proposed_targets'])
        self.assertNotIn('official_demonstration',n)
        self.assertEqual(t['targets'][0],[0,0,0])

    def test_unverified_or_mismatched_historical_record_is_rejected(self):
        t,r=self.fixture();r['original_heading']=0
        with self.assertRaises(ValueError):bind_reused_task(t,r,'sources')
        t,r=self.fixture();r['potential_strict_endpoint_repair']=False
        with self.assertRaises(ValueError):bind_reused_task(t,r,'sources')
