import unittest
from oracle.contracts import Budget
from oracle.planners.action_space import search


class SearchSnapshotTests(unittest.TestCase):
    def test_observer_does_not_change_success_or_failure_search(self):
        for cap in (1, 8):
            with self.subTest(cap=cap):
                seen=[]
                def run(sink=None):
                    return search(0, actions=(1,2), transition=lambda s,a:s+a,
                        key=lambda s:s, reached=lambda s:s==4, heuristic=lambda s:abs(4-s),
                        action_costs={1:1.,2:1.}, budget=Budget(cap,30,10,10), audit_sink=sink)
                plain=run(); observed=run(seen.append)
                for field in ('actions','states','failure','expansions','transition_calls','cost','diagnostics'):
                    self.assertEqual(getattr(plain,field),getattr(observed,field))
                self.assertEqual(len(seen),1)
                snapshot=seen[0]
                self.assertEqual(len(snapshot['expanded_indices']),observed.expansions)
                self.assertEqual(len(snapshot['nodes']),observed.diagnostics['generated_labels'])
                self.assertEqual(len(snapshot['heuristics']),len(snapshot['nodes']))
                for state,parent,action,depth in snapshot['nodes'][1:]:
                    self.assertEqual(state,snapshot['nodes'][parent][0]+action)
                    self.assertEqual(depth,snapshot['nodes'][parent][3]+1)

    def test_snapshot_exposes_distinct_states_without_merging(self):
        snapshots=[]
        result=search(0.,actions=(1,2),transition=lambda s,a:s+a*1e-8,
            key=float.hex,reached=lambda s:False,heuristic=lambda s:0.,
            action_costs={1:1.,2:1.},budget=Budget(3,9,10,10),audit_sink=snapshots.append)
        self.assertGreater(len({n[0] for n in snapshots[0]['nodes']}),1)
        self.assertEqual(result.expansions,3)
