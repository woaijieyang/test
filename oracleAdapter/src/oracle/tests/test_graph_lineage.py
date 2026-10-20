import unittest
from oracle.adapters.landmark_rxr.graph_lineage import graph_index, viewpoint_record
from oracle.adapters.landmark_rxr.graph_path_audit import classify_path, hop_path


def nodes():
    pose = [1,0,0,2,0,1,0,3,0,0,1,4,0,0,0,1]
    return [dict(image_id='a',pose=pose,included=True,unobstructed=[False,True]),
            dict(image_id='b',pose=pose,included=True,unobstructed=[True,False])]


class GraphLineageTest(unittest.TestCase):
    def test_loop_occurrences_and_absent_edge_are_distinct(self):
        pairs={('a','b'),('b','a'),('b','c'),('c','b')}
        good=classify_path(['a','a','b','a','b','c'],{'a','b','c'},pairs)
        self.assertEqual(good['status'],'GRAPH_PATH_EXISTS')
        self.assertEqual(good['repeated_consecutive_occurrences'],1)
        bad=classify_path(['a','c'],{'a','b','c'},pairs)
        self.assertEqual(bad['status'],'MISSING_ADJACENCY')
        self.assertEqual(hop_path('a','c',{'a','b','c'},pairs),['a','b','c'])
        missing=classify_path(['a','unknown','a'],{'a','b','c'},pairs)
        self.assertEqual(missing['missing_nodes'],[dict(occurrence=1,viewpoint='unknown')])

    def test_exact_id_not_nearest_coordinate(self):
        original = graph_index(nodes())
        result = viewpoint_record('s','a',original,{'different-id':[2,4,-3]})
        self.assertEqual(result['category'],'ORIGINAL_INCLUDED_ID_ABSENT_FROM_PUBLISHED_GRAPH')
        self.assertIsNone(result['replacement_identity'])
        self.assertEqual(result['original']['habitat_camera_xyz'],[2,4,-3])
        self.assertEqual(result['original']['included_neighbors'],['b'])

    def test_duplicate_and_bad_adjacency_rejected(self):
        values = nodes();values[1]['image_id']='a'
        with self.assertRaises(ValueError):graph_index(values)
        values=nodes();values[0]['unobstructed']=[True]
        with self.assertRaises(ValueError):graph_index(values)

    def test_asymmetry_and_excluded_identity_retained(self):
        values=nodes();values[1]['unobstructed'][0]=False;values[1]['included']=False
        index=graph_index(values)
        self.assertEqual(index['a']['asymmetric_neighbors'],['b'])
        self.assertEqual(index['a']['included_neighbors'],[])
        self.assertEqual(viewpoint_record('s','b',index,{})['category'],'ORIGINAL_EXCLUDED_ID')

    def test_camera_comparison_does_not_apply_height(self):
        index=graph_index(nodes())
        result=viewpoint_record('s','a',index,{'a':[2,2.5,-3]}, {'camera_position':[2,4,-3]})
        self.assertEqual(result['legacy_camera_max_axis_difference_m'],0)
        self.assertEqual(result['camera_to_published_vector_m'],[0,-1.5,0])
        self.assertEqual(result['native_reachability'],'NOT_TESTED_BY_DISCRETE_GRAPH_AUDIT')
