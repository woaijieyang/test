import copy
import unittest
from oracle.research.same_id_static import validate_seed_source


class SameIdStatic(unittest.TestCase):
    def data(self):
        target=dict(task_key='train:t',scene='s',profile_sha256='p',geometry_catalog_sha256='g',
                    original_viewpoint_path=['v'],targets=[[0,0,0]])
        source={**copy.deepcopy(target),'task_key':'train:s'}
        seed=dict(origin='strict_success_same_id_prior',source_task_key='train:s',source_reference_index=0,
                  source_receipt_sha256='r',position=[0,0,0])
        outcome=dict(status='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES',receipt_sha256='r')
        return target,source,seed,outcome

    def test_verified_same_id_seed_is_accepted_as_input_not_as_route_pass(self):
        t,s,p,r=self.data();self.assertIsNone(validate_seed_source(t,0,p,s,r))

    def test_same_coordinate_cannot_replace_a_different_node_identity(self):
        t,s,p,r=self.data();s['original_viewpoint_path']=['other']
        with self.assertRaises(ValueError):validate_seed_source(t,0,p,s,r)

    def test_coordinate_edit_or_failed_donor_is_rejected(self):
        t,s,p,r=self.data();p['position']=[.01,0,0]
        with self.assertRaises(ValueError):validate_seed_source(t,0,p,s,r)
        t,s,p,r=self.data();r['status']='FAILURE_PRESERVED'
        with self.assertRaises(ValueError):validate_seed_source(t,0,p,s,r)

    def test_preserved_current_coordinate_does_not_claim_successful_donor(self):
        t,s,p,r=self.data();p.update(origin='preserved_current_target_NOT_success_prior',source_task_key=t['task_key'])
        r['status']='STATIC_FAILURE_PRESERVED'
        validate_seed_source(t,0,p,t,r)
        p['source_reference_index']=1
        with self.assertRaises(ValueError):validate_seed_source(t,0,p,t,r)
