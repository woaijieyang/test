import unittest
from oracle.adapters.habitat.native import NativeState
from oracle.research.counterfactual_plan import follow_plan


class Adapter:
    def restore(self,s):self.state=s
    def snapshot(self):return self.state
    def step(self,a):
        self.state=NativeState((self.state.position[0]+.25,0,0),(0,0,0,1));return self.state
    def geodesic_distance(self,p,q):return abs(p[0]-q[0])


class CounterfactualPlanTests(unittest.TestCase):
    def test_stops_at_original_goal_region_and_keeps_occurrence_order(self):
        r=follow_plan(Adapter(),NativeState((0,0,0),(0,0,0,1)),[[0,0,0],[.5,0,0],[1,0,0]],[1]*8,.25,lambda *x:None,lambda *x:None)
        self.assertTrue(r['route_complete']);self.assertEqual(r['actions'],[1]*3)
        self.assertEqual([x['reference_index'] for x in r['boundaries']],[1,2])

    def test_physical_failure_is_retained_not_accepted(self):
        r=follow_plan(Adapter(),NativeState((0,0,0),(0,0,0,1)),[[0,0,0],[1,0,0]],[1]*8,.25,lambda *x:'fixture_violation',lambda *x:None)
        self.assertFalse(r['route_complete']);self.assertEqual(r['actions'],[1]);self.assertEqual(len(r['alerts']),1)

    def test_initial_source_contact_uses_no_actions(self):
        r=follow_plan(Adapter(),NativeState((0,0,0),(0,0,0,1)),[[0,0,0],[1,0,0]],[1],.25,lambda *x:None,lambda *x:{'fixture':'contact'})
        self.assertFalse(r['route_complete']);self.assertEqual(r['actions'],[])
