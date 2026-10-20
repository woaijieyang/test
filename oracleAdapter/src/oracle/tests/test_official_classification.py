import unittest
from oracle.research.official_classification import classify_row


class OfficialClassification(unittest.TestCase):
    def test_old_pass_under_weaker_gate_is_not_new_algorithm_recovery(self):
        row = classify_row('x', 'MOTION_PASS_PENDING_INDEPENDENT_REPLAY',
            {'failure': 'source_geometry_contact', 'detail': 'initial_source_contact', 'actions': []},
            {'full_route_accepted': False, 'physical_alerts': [{'index': 0, 'kind': 'initial_source_contact'}]})
        self.assertEqual(row['phase'], 'initial_state')
        self.assertFalse(row['algorithm_gain_claim'])
        self.assertEqual(row['physical_unreachability'], 'NOT_PROVEN')

    def test_reproducible_trace_can_still_fail_native_gate(self):
        row = classify_row('x', 'FAIL', {'failure': 'native_action_illegal', 'detail': 'horizontal_limit', 'actions': [1]},
            {'full_route_accepted': False, 'physical_alerts': [{'index': 1, 'kind': 'horizontal_limit'}]})
        self.assertEqual(row['phase'], 'executed_transition')
        self.assertEqual(row['failure'], 'native_action_illegal')
