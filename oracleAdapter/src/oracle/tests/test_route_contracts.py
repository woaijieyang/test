import unittest
from oracle.adapters.habitat.native import NativeState
from oracle.teachers.ordered import require_task_contract
from oracle.verification.motion import native_violation
from oracle.verification.source_scene import SourceScene


class RouteContracts(unittest.TestCase):
    def test_contract_evidence_preserves_privileges_as_canonical_json(self):
        import json
        task = {"task_key": "x", "purpose": "reference_execution", "objective": "visit_reference_in_order",
                "privileges": ["true_pose", "navigation_mesh", "goal", "reference_path", "source_geometry"]}
        contract = require_task_contract(task, {"protocol_id": "fixture"})
        record = json.loads(json.dumps(contract.to_record(), allow_nan=False))
        self.assertEqual(record["privileges"], sorted(task["privileges"]))
        self.assertEqual(record["objective"], task["objective"])
        self.assertEqual(record["reset_policy"], "initial_only")

    def test_ordered_teacher_rejects_goal_only_contract(self):
        task = {"task_key": "x", "purpose": "goal_navigation", "objective": "reach_goal_only",
                "privileges": ["true_pose", "navigation_mesh", "goal"]}
        with self.assertRaises(ValueError):
            require_task_contract(task, {"protocol_id": "fixture"})

    def test_actual_horizontal_overstep_cannot_pass(self):
        class Navigable:
            def is_navigable(self, position):
                return True
        before = NativeState((0, 0, 0), (0, 0, 0, 1))
        after = NativeState((.261, 0, 0), (0, 0, 0, 1))
        protocol = {"forward_m": .25, "horizontal_tolerance_m": .0001,
                    "maximum_vertical_transition_m": .5, "minimum_forward_motion_m": .00001}
        self.assertEqual(native_violation(Navigable(), before, after, 1, protocol), "horizontal_limit")

    def test_rational_scene_check_is_a_distinct_implementation(self):
        import numpy as np
        scene = SourceScene.__new__(SourceScene)
        scene.np = np
        scene.triangles = np.array([[[0., .4, -.05], [0., .4, .05], [0., 1., 0.]]])
        scene.low, scene.high = scene.triangles.min(axis=1), scene.triangles.max(axis=1)
        scene.protocol = {"body_height_m": 1.5, "body_radius_m": .1,
                          "foot_epsilon_m": .00001, "radial_epsilon_m": .000001}
        scene.geometry_sha256 = "fixture"
        scene.queries = scene.triangle_checks = 0
        hit = scene.contact([-.3, 0, 0], [.3, 0, 0], arithmetic="rational_hull")
        self.assertEqual(hit["arithmetic"], "rational_hull")
        self.assertIn("exact_barycentric", hit["witness"])


if __name__ == "__main__":
    unittest.main()
