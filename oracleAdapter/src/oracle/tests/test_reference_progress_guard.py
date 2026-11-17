import unittest
from oracle.portfolio.reference_progress import ReferenceProgressGuard


class ReferenceProgressTests(unittest.TestCase):
    def guard(self):
        return ReferenceProgressGuard(max_excess_distance_m=1., max_nonprogress_actions=12)

    def test_close_miss_cannot_consume_the_rest_of_the_route(self):
        g=self.guard()
        self.assertIsNone(g.check(1,2.168394935,.288110307))
        self.assertIsNone(g.check(1,.288110307,.538110307))
        self.assertIsNone(g.check(1,.538110307,1.038110307))
        self.assertEqual(g.check(1,1.038110307,1.538110307),'reference_distance_excursion')
        self.assertAlmostEqual(g.best_distance,.288110307)

    def test_bounded_detour_and_turns_are_not_forbidden_monotonically(self):
        g=self.guard()
        for a,b in [(3.,3.),(3.,3.),(3.,3.4),(3.4,3.7),(3.7,2.9)]:
            self.assertIsNone(g.check(1,a,b))
        self.assertEqual(g.nonprogress_actions,0)

    def test_stagnation_switches_before_unbounded_prefix_execution(self):
        g=self.guard()
        for _ in range(11):self.assertIsNone(g.check(1,2.,2.))
        self.assertEqual(g.check(1,2.,2.),'reference_progress_stalled')

    def test_reference_occurrence_resets_monitor_not_agent(self):
        g=self.guard();g.check(1,3.,.3)
        self.assertIsNone(g.check(2,8.,7.8))
        self.assertEqual(g.reference_index,2)
        self.assertEqual(g.best_distance,7.8)
        with self.assertRaises(ValueError):g.check(1,7.,6.)

    def test_nonfinite_distance_and_invalid_configuration_fail_closed(self):
        for v in [0,-1,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):ReferenceProgressGuard(max_excess_distance_m=v,max_nonprogress_actions=12)
        with self.assertRaises(ValueError):self.guard().check(1,2,float('inf'))
