import unittest
from oracle.verification.dense_mapping import verify_selection


class DenseMappingAuditTests(unittest.TestCase):
    def fixture(self):
        occ=[{'index':i,'viewpoint_id':str(i),'position':[float(i),0,0]} for i in range(2)]
        gt=[[0.,0,0],[1.,0,0]]
        selected=[dict(reference_index=i,source_viewpoint_id=str(i),anchor=gt[i],source_position=gt[i],position=gt[i],source_index=i,source_forward_action_index=i-1,cost=0.) for i in range(2)]
        return occ,selected,gt,[-1,0],{'source_sphere_m':.5,'extra_horizontal_m':.350001}

    def test_valid_binding_then_wrong_id_rejected(self):
        a=self.fixture();self.assertEqual(verify_selection(*a),[])
        a[1][1]['source_viewpoint_id']='nearest-other-node'
        self.assertIn('source_occurrence_binding',verify_selection(*a))

    def test_reversed_dense_occurrences_rejected(self):
        a=self.fixture();a[1][1]['source_index']=0
        self.assertIn('dense_occurrence_order',verify_selection(*a))

    def test_horizontal_proposal_bound_is_not_only_spherical(self):
        a=self.fixture();a[1][0]['position']=[.4,0,0]
        self.assertIn('source_displacement_bound',verify_selection(*a))

    def test_cannot_drop_missing_reference(self):
        a=self.fixture();a[1].pop()
        self.assertEqual(verify_selection(*a),['occurrence_count'])
