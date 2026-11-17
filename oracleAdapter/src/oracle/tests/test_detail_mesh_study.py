import unittest
from oracle.research.detail_mesh_study import check_single_factor,check_control


class DetailMeshStudyTests(unittest.TestCase):
    def test_only_detail_error_can_change(self):
        before={'agent_height':1.5,'agent_radius':.1,'cell_height':.025,'detail_sample_max_error':1.}
        check_single_factor(before,{**before,'detail_sample_max_error':.1})
        for after in ({**before,'agent_radius':.09,'detail_sample_max_error':.1},{**before,'cell_height':.01,'detail_sample_max_error':.1},before):
            with self.assertRaises(ValueError):check_single_factor(before,after)

    def test_control_needs_geometry_binding_and_mesh_byte_identity(self):
        receipt={'scene_sha256':'scene','binding_sha256':'binary','mesh_sha256':'mesh'}
        check_control(receipt,'scene','binary','mesh','mesh')
        for args in [('wrong','binary','mesh','mesh'),('scene','wrong','mesh','mesh'),('scene','binary','other','mesh')]:
            with self.assertRaises(ValueError):check_control(receipt,*args)
