import unittest
from oracle.verification.route_replay import audit_progress_queries


class ProgressReplayTests(unittest.TestCase):
    def record(self):
        return {'method':{'reference_progress_guard':{'max_excess_distance_m':1.,'max_nonprogress_actions':12}},
            'protocol':{'maximum_prediction_error_m':1e-5},'positions':[[0,0,0],[.25,0,0]],
            'actions':[1],'official_primitives_consumed':1,'boundaries':[],
            'reference_progress_queries':[{'reference_index':1,'action_index':0,'proposed_action':1,
                'before_distance_m':2.,'after_distance_m':1.75,'proposed_position':[.25,0,0],
                'reason':None,'monitor':{'reference_index':1,'best_distance_m':1.75,'nonprogress_actions':0}}]}

    def test_recompute_progress_from_positions_not_claimed_distance(self):
        r=self.record();task={'targets':[[0,0,0],[2,0,0]]}
        distance=lambda p,t:abs(p[0]-t[0])
        self.assertEqual(audit_progress_queries(task,r,distance),[])
        r['reference_progress_queries'][0]['after_distance_m']=.1
        self.assertIn('progress_distance_binding',audit_progress_queries(task,r,distance))

    def test_missing_monitor_queries_cannot_pass(self):
        r=self.record();r['reference_progress_queries']=[]
        self.assertIn('progress_query_coverage',audit_progress_queries({'targets':[[0,0,0],[2,0,0]]},r,lambda p,t:2))
