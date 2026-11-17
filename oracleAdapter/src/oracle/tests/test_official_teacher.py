import unittest
from oracle.teachers.official import expand_actions, advance_boundaries


class OfficialTeacher(unittest.TestCase):
    def test_registry_exposes_live_official_teacher_with_actions_privilege(self):
        from oracle.registry import METHODS
        from oracle.contracts import Privilege
        method = METHODS['official_landmark_demonstration']
        self.assertEqual(method.implementation, 'oracle.teachers.official:execute')
        self.assertIn(Privilege.ACTIONS, method.privileges)

    def test_native_turn_translation_keeps_source_action_indices(self):
        actions, indices = expand_actions([2, 1, 3, 0])
        self.assertEqual(actions, [2, 2, 1, 3, 3])
        self.assertEqual(indices, [0, 0, 1, 2, 2])

    def test_nonterminal_stop_or_unsupported_action_rejected(self):
        for actions in ([1, 0, 1], [4, 0], [True, 0], [1]):
            with self.assertRaises(ValueError): expand_actions(actions)

    def test_reaching_later_landmark_does_not_skip_required_occurrence(self):
        distance = lambda target: {"a": 2, "b": 0}[target]
        self.assertEqual(advance_boundaries(["start", "a", "b"], 1, 7, distance, .25), [])
        self.assertEqual([b["reference_index"] for b in advance_boundaries(["start", "b", "b"], 1, 7, distance, .25)], [1, 2])
