import unittest
from oracle.contracts import Budget,Failure
from oracle.planners.action_space import search
from oracle.planners.soft_duplicate import pose_bucket,validate_config
from oracle.adapters.habitat.native import NativeState


class SoftDuplicateTests(unittest.TestCase):
    def test_same_soft_bucket_cannot_prune_distinct_valid_successor(self):
        graph={0:{1:1,2:2},1:{},2:{1:3},3:{}}
        snapshots=[]
        r=search(0,actions=(1,2),transition=lambda s,a:graph[s].get(a),key=lambda s:s,
            reached=lambda s:s==3,heuristic=lambda s:0 if s==3 else 1,
            action_costs={1:1.,2:1.},budget=Budget(20,60,20,10),
            soft_duplicate_key=lambda s:0,soft_duplicate_weight=2.,audit_sink=snapshots.append)
        self.assertEqual(r.failure,Failure.NONE)
        self.assertEqual(r.actions,(2,1))
        self.assertEqual({n[0] for n in snapshots[0]['nodes']},{0,1,2,3})

    def test_soft_penalty_prioritizes_new_region_without_changing_real_cost(self):
        graph={0:{1:1,2:2},1:{1:4},2:{1:3},3:{},4:{}}
        r=search(0,actions=(1,2),transition=lambda s,a:graph[s].get(a),key=lambda s:s,
            reached=lambda s:s==3,heuristic=lambda s:0 if s==3 else 2,
            action_costs={1:1.,2:1.},budget=Budget(2,6,10,10),
            soft_duplicate_key=lambda s:0 if s in (0,1,4) else s,soft_duplicate_weight=2.)
        self.assertEqual(r.actions,(2,1));self.assertEqual(r.cost,2.)

    def test_config_rejects_hidden_changes_and_bucket_is_only_a_priority_hint(self):
        cfg={'position_cell_m':.001,'yaw_cell_degrees':.001,'maximum_priority_weight':2.}
        validate_config(cfg)
        a=NativeState((0,0,0),(0,0,0,1));b=NativeState((1e-7,0,0),(0,0,0,1))
        self.assertNotEqual(a,b);self.assertEqual(pose_bucket(a,cfg),pose_bucket(b,cfg))
        for bad in ({**cfg,'prune':True},{**cfg,'position_cell_m':0},{**cfg,'maximum_priority_weight':float('nan')}):
            with self.assertRaises(ValueError):validate_config(bad)
