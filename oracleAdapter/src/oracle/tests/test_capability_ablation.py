import unittest
from oracle.research.capability_ablation import compare_sets


class CapabilityAblation(unittest.TestCase):
    def test_overlap_does_not_turn_hypothetical_union_into_a_result(self):
        report=compare_sets({'a'},{'b','r'},{'a','b','n'})
        self.assertEqual(report['combination_only_beyond_both_single_methods'],['n'])
        self.assertEqual(report['search_success_not_recovered_by_combination'],['r'])
        self.assertTrue(report['union_is_diagnostic_not_an_executed_method'])
        self.assertNotIn('union_success_rate',report)
