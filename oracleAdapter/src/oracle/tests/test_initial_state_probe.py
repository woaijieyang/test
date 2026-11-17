import unittest
from oracle.verification.initial_state_probe import classify_actions


class InitialStateProbe(unittest.TestCase):
    def rows(self,a,b):
        return [{'action':i,'direct':{'admissible':i in a},'pose_roundtrip':{'admissible':i in b}} for i in (1,2,3)]

    def test_missing_or_duplicate_primitive_cannot_prove_no_first_action(self):
        with self.assertRaises(ValueError):classify_actions(self.rows(set(),set())[:2])
        with self.assertRaises(ValueError):classify_actions([self.rows(set(),set())[0]]*3)

    def test_model_false_negative_is_not_a_data_unreachability_claim(self):
        r=classify_actions(self.rows({1},set()))
        self.assertTrue(r['admission_disagreement'])
        self.assertFalse(r['all_direct_actions_rejected'])
        self.assertFalse(r['physical_unreachability_proven'])

    def test_no_admissible_primitive_is_not_a_navigation_recovery(self):
        r=classify_actions(self.rows(set(),set()))
        self.assertTrue(r['all_direct_actions_rejected'])
        self.assertFalse(r['physical_unreachability_proven'])
        self.assertEqual(r['navigation_tasks_recovered'],0)
