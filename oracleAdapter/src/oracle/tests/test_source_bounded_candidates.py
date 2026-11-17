import unittest
from oracle.adapters.landmark_rxr.source_bounded_candidates import collect_candidates,choose_common_component


class SourceBoundedCandidatesTests(unittest.TestCase):
    def test_native_float32_anchor_can_be_written_to_immutable_json(self):
        import json,numpy as np
        r=self.collect(anchor=np.array([0,0,0],dtype=np.float32))
        json.dumps(r,allow_nan=False)

    def collect(self,**kw):
        args=dict(anchor=[0.,0.,0.],anchor_kind='official_reference_node',camera=None,current=[0.,0.,0.],
            offsets=[(.1,0)],snap=lambda p:list(p),navigable=lambda p:True,contact=lambda p:None,
            component=lambda p:0,sphere_m=.5,extra_horizontal_m=.350001)
        args.update(kw);return collect_candidates(**args)

    def test_body_filter_precedes_rank_collapse_within_component(self):
        result=self.collect(contact=lambda p:{'triangle':1} if p[0]==0 else None)
        self.assertEqual(result['options'][0]['position'],[.1,0.,0.])
        self.assertEqual(result['options'][0]['rank'],3)
        self.assertGreater(result['rejections']['source_body_contact'],0)

    def test_extra_source_bound_is_kept(self):
        r=self.collect(current=None,offsets=[(.4,0)],contact=lambda p:True if p[0]==0 else None)
        self.assertFalse(r['options']);self.assertEqual(r['rejections']['source_bound'],1)

    def test_valid_current_coordinate_retained_exactly(self):
        r=self.collect(snap=lambda p:[p[0]+1e-7,p[1],p[2]])
        self.assertEqual(r['options'][0]['position'],[0.,0.,0.])
        self.assertEqual(r['options'][0]['rank'],0)

    def test_joint_component_not_independent_nearest_choices(self):
        a={'position':[0,0,0],'rank':0,'displacement':0.}
        b={'position':[.1,0,0],'rank':3,'displacement':.1}
        selected=choose_common_component([{0:a,1:b},{1:a}])
        self.assertEqual(selected['component'],1)
        self.assertEqual(len(selected['choices']),2)
        self.assertIsNone(choose_common_component([{0:a},{}]))

    def test_explicit_same_id_seed_keeps_its_height_and_original_bounds(self):
        r=self.collect(current=None,offsets=[],extra_seed_points=[[.1,.1,0]],
                       contact=lambda p:True if p[0]==0 else None)
        self.assertEqual(r['options'][0]['position'],[.1,.1,0.])
        self.assertEqual(r['options'][0]['seed_position'],[.1,.1,0.])
        rejected=self.collect(current=None,offsets=[],extra_seed_points=[[.4,0,0]],
                              contact=lambda p:True if p[0]==0 else None)
        self.assertFalse(rejected['options'])
        self.assertEqual(rejected['rejections']['source_bound'],1)

    def test_seed_does_not_invent_a_missing_source_anchor(self):
        r=self.collect(anchor=None,extra_seed_points=[[.1,0,0]])
        self.assertFalse(r['options'])

    def test_actuation_filter_precedes_component_rank_selection(self):
        r=self.collect(candidate_admission=lambda p:'unsafe_zero_filter' if p[0]==0 else None,
                       retain_seed_metadata=True)
        self.assertEqual(r['options'][0]['position'],[.1,0.,0.])
        self.assertEqual(r['options'][0]['seed_position'],[.1,0.,0.])
        self.assertEqual(r['rejections']['candidate_admission::unsafe_zero_filter'],1)
