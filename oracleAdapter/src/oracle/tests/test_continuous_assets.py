import unittest
from oracle.adapters.rxr.continuous_assets import inspect_demonstration


class ContinuousAssets(unittest.TestCase):
    def test_source_nonfinite_timestamp_is_recorded_not_navigation_pass(self):
        from oracle.adapters.rxr.continuous_assets import source_identity
        source = {"instruction": {"timed_instruction": [{"start_time": float("nan")}]}}
        result = source_identity(source)
        self.assertEqual(result["nonfinite_fields"], [{"path": ".instruction.timed_instruction[0].start_time", "value": "nan"}])
        self.assertEqual(result["sha256"], source_identity(source)["sha256"])
        self.assertNotEqual(result["sha256"], source_identity({"instruction": {"timed_instruction": [{"start_time": "NaN"}]}})["sha256"])

    def test_locations_follow_forward_occurrences_not_every_action(self):
        gt = {"actions": [2, 1, 3, 1, 0], "locations": [[0, 0, 0], [1, 0, 0], [1, 0, 1]], "forward_steps": 2}
        row = inspect_demonstration(gt, [0, 0, 0])
        self.assertEqual(row["errors"], [])
        self.assertEqual(row["location_action_indices"], [0, 2, 4])
        self.assertEqual(row["expanded_navigation_actions"], 6)
        self.assertEqual(row["position_trace_scope"], "initial_plus_forward_actions_not_full_pose_trace")

    def test_missing_stop_and_location_gap_preserved(self):
        row = inspect_demonstration({"actions": [1, 2], "locations": [[0, 0, 0]], "forward_steps": 1}, [0, 0, 0])
        self.assertIn("not_single_terminal_stop", row["errors"])
        self.assertIn("location_count_not_forward_plus_initial", row["errors"])

    def test_tilt_and_boolean_not_silently_converted(self):
        row = inspect_demonstration({"actions": [4, 1, 0], "locations": [[0, 0, 0], [1, 0, 0]], "forward_steps": 1}, [0, 0, 0])
        self.assertIn("unsupported_current_native_actions", row["errors"])
        self.assertIsNone(row["expanded_navigation_actions"])
        row = inspect_demonstration({"actions": [True, 0], "locations": [[0, 0, 0]], "forward_steps": 0}, [0, 0, 0])
        self.assertIn("non_integer_action", row["errors"])
