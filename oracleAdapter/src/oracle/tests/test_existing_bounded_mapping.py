import copy,unittest
from oracle.verification.existing_bounded_mapping import check_record_invariants,check_choice_bounds


class ExistingBoundedMappingTests(unittest.TestCase):
    def source(self):return {'method':'same_id','position':[0.,0.,0.],'camera_position':[0.,1.5,0.]}

    def test_original_heading_instruction_and_failed_records_cannot_change(self):
        old={'task_key':'train:1','targets':[[0,0,0]],'heading':1.2,'source_record_sha256':'raw','mapping_methods':['old']}
        new=copy.deepcopy(old);new['targets']=[[.1,0,0]];new['mapping_methods']=['proposal']
        self.assertEqual(check_record_invariants(old,new),[])
        new['heading']=0
        self.assertIn('non_mapping_field_changed',check_record_invariants(old,new))

    def test_extra_seed_bound_is_not_relaxed_to_source_sphere(self):
        q={'position':[.4,0,0],'anchor':[0.,0.,0.],'anchor_kind':'official_reference_node','rank':3,'displacement':.4}
        self.assertIn('extra_horizontal_bound',check_choice_bounds(self.source(),[0.,0.,0.],[0.,0.,0.],q))

    def test_native_source_identity_overrides_published_guess(self):
        s=self.source();s['position']=[1.,0.,0.]
        q={'position':[1.,0,0],'anchor':[1.,0,0],'anchor_kind':'same_id','rank':2,'displacement':0.}
        self.assertIn('source_anchor_identity',check_choice_bounds(s,[0.,0.,0.],[0.,0.,0.],q))

    def test_bounded_camera_gate_and_missing_anchor_fail_closed(self):
        s={'method':'UNRESOLVED_no_direct_identity','camera_position':[0.,1.5,0.]}
        q={'position':[.49,0,0],'anchor':[.49,0,0],'anchor_kind':'bounded_camera_projection','rank':0,'displacement':0.}
        self.assertEqual(check_choice_bounds(s,None,[.49,0,0],q),[])
        self.assertIn('unresolved_source_anchor',check_choice_bounds(s,None,None,q))
