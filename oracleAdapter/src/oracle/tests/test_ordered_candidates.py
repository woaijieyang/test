import unittest
from oracle.adapters.landmark_rxr.ordered_candidates import align_candidates


def c(index,cost=0):return {'source_index':index,'cost':cost,'position':[float(index),0.,0.]}


class OrderedCandidatesTests(unittest.TestCase):
    def test_global_component_choice_does_not_pick_disconnected_local_minima(self):
        from oracle.adapters.landmark_rxr.ordered_candidates import align_connected_candidates
        a={**c(1,0),'component':0};b={**c(1,2),'component':1}
        d={**c(3,0),'component':1}
        r=align_connected_candidates([[a,b],[d]],[False])
        self.assertEqual(r['component'],1)
        self.assertEqual(r['cost'],2)

    def test_independent_closest_reverse_order_is_rejected(self):
        r=align_candidates([[c(4,0),c(1,2)],[c(2,0),c(5,4)]],[False])
        self.assertEqual([v['source_index'] for v in r['selected']],[1,2])
        self.assertEqual(r['cost'],2)

    def test_revisited_anchor_requires_later_source_occurrence(self):
        r=align_candidates([[c(0),c(4)],[c(2)],[c(0),c(4)]],[False,False])
        self.assertEqual([v['source_index'] for v in r['selected']],[0,2,4])

    def test_zero_length_segment_keeps_both_boundaries(self):
        r=align_candidates([[c(2)],[c(2)]],[True])
        self.assertEqual(len(r['selected']),2)
        self.assertIsNone(align_candidates([[c(2)],[c(2)]],[False])['selected'])

    def test_missing_or_blocked_layer_does_not_delete_occurrence(self):
        r=align_candidates([[c(1)],[],[c(3)]],[False,False])
        self.assertIsNone(r['selected']);self.assertEqual(r['failed_layer'],1)

    def test_bad_indices_cost_or_zero_length_rule_are_rejected(self):
        for bad in [c(-1),c(True),c(1,-1),c(1,float('nan'))]:
            with self.assertRaises(ValueError):align_candidates([[bad]],[])
        with self.assertRaises(ValueError):align_candidates([[c(1)],[c(2)]],[])
