import unittest
from oracle.contracts import Budget, Failure, Objective, Purpose, Privilege, TaskContract
from oracle.common.identity import Context, exact_state_key
from oracle.planners.action_space import search
from oracle.adapters.landmark_rxr.occurrences import align_subpaths
from oracle.adapters.landmark_rxr.occurrences import align_with_source_connectors
from oracle.adapters.landmark_rxr.ledger import canonical_id
from oracle.verification.binding import bind, bind_callable
from oracle.registry import validate_contract
from oracle.adapters.habitat.native import NativeState
from pathlib import Path


class ContractsAndSearch(unittest.TestCase):
    def setUp(self):
        self.context = Context(*(["a" * 64] * 7), "native-state-v1")

    def test_rounding_alias_loses_reachable_successor(self):
        # Two distinct same-centimeter states have different futures. This is
        # a small counterexample, not a simulated Habitat navigation score.
        a, b = 0.001, 0.004
        edges = {(0., 1): a, (0., 2): b, (b, 1): 1.0}
        kwargs = dict(actions=(1, 2), transition=lambda s, a: edges.get((s, a)),
                      reached=lambda s: s == 1., heuristic=lambda s: 0.,
                      action_costs={1: 1., 2: 1.}, budget=Budget(10, 20, 5, 2.))
        bad = search(0., key=lambda s: round(s, 2), **kwargs)
        good = search(0., key=lambda s: exact_state_key((s,), 0, self.context), **kwargs)
        self.assertEqual(bad.failure, Failure.FRONTIER)
        self.assertEqual(good.failure, Failure.NONE)
        self.assertEqual(good.actions, (2, 1))

    def test_reference_progress_and_context_cannot_alias(self):
        self.assertNotEqual(exact_state_key((1.,), 0, self.context),
                            exact_state_key((1.,), 1, self.context))
        changed = Context(*(["b" * 64] * 7), "native-state-v1")
        self.assertNotEqual(exact_state_key((1.,), 0, self.context),
                            exact_state_key((1.,), 0, changed))

    def test_budget_failure_is_not_unreachability(self):
        result = search(0, actions=(1,), transition=lambda s, a: s + 1,
                        key=lambda s: s, reached=lambda s: s == 10,
                        heuristic=lambda s: 0., action_costs={1: 1.},
                        budget=Budget(2, 10, 20, 1.))
        self.assertEqual(result.failure, Failure.SEARCH_BUDGET)
        self.assertEqual(result.expansions, 2)

    def test_cheaper_longer_label_cannot_prune_shorter_budget_feasible_label(self):
        edges = {(0, 1): 1, (1, 1): 2, (0, 2): 2, (2, 1): 3}
        result = search(0, actions=(1, 2), transition=lambda s, a: edges.get((s, a)),
                        key=lambda s: s, reached=lambda s: s == 3,
                        heuristic=lambda s: 0., action_costs={1: .1, 2: 1.},
                        budget=Budget(20, 40, 2, 2.))
        self.assertEqual(result.failure, Failure.NONE)
        self.assertEqual(result.actions, (2, 1))

    def test_forward_bit_does_not_make_rounded_state_sufficient(self):
        edges = {(0., 1): 1.001, (0., 2): 1.004,
                 (1.001, 1): 2.001, (1.004, 1): 2.004, (2.004, 1): 3.}
        args = dict(actions=(1, 2), transition=lambda s, a: edges.get((s, a)),
                    reached=lambda s: s == 3., heuristic=lambda s: 0.,
                    action_costs={1: 1., 2: 1.}, budget=Budget(20, 40, 6, 2.))
        limited_key = lambda s: (round(s, 2), (s, 1) in edges)
        self.assertEqual(limited_key(1.001), limited_key(1.004))
        self.assertEqual(search(0., key=limited_key, **args).failure, Failure.FRONTIER)
        actual = search(0., key=lambda s: exact_state_key((s,), 0, self.context), **args)
        self.assertEqual(actual.actions, (2, 1, 1))
        self.assertEqual(actual.failure, Failure.NONE)

    def test_loop_occurrences_and_zero_length_segment_survive(self):
        result = align_subpaths(["a", "b", "a", "c"],
                                [["a", "b"], ["b", "a"], ["a"], ["a", "c"]])
        self.assertEqual(result.intervals, ((0, 1), (1, 2), (2, 2), (2, 3)))

    def test_no_shortcut_or_missing_instruction_boundary(self):
        self.assertEqual(align_subpaths(["a", "b", "c"], [["a", "c"]]).status,
                         "UNRESOLVED")

    def test_privilege_objective_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            TaskContract("x", Purpose.GOAL, Objective.LANDMARK_ORDER,
                         frozenset({Privilege.GOAL}), "p", "a" * 64, "initial_only")

    def test_registry_rejects_silent_additional_privileged_information(self):
        privileges = frozenset({Privilege.POSE, Privilege.NAVMESH, Privilege.GOAL})
        task = TaskContract("x", Purpose.GOAL, Objective.GOAL_ONLY, privileges, "p", "a" * 64, "initial_only")
        self.assertEqual(validate_contract("bounded_native_action_search", task).name, "bounded_native_action_search")
        enriched = TaskContract("x", Purpose.GOAL, Objective.GOAL_ONLY,
                                privileges | {Privilege.REFERENCE}, "p", "a" * 64, "initial_only")
        with self.assertRaises(ValueError):
            validate_contract("bounded_native_action_search", enriched)

    def test_native_state_owns_immutable_input_values(self):
        position, rotation = [0., 0., 0.], [0., 0., 0., 1.]
        state = NativeState(position, rotation)
        position[0] = 99.
        rotation[3] = 0.
        self.assertEqual(state.position, (0., 0., 0.))
        self.assertEqual(state.quaternion_xyzw, (0., 0., 0., 1.))

    def test_typed_ids_and_rejected_lossy_conversion(self):
        self.assertEqual(canonical_id(" 00042 "), canonical_id(42))
        self.assertEqual(canonical_id(42.0), "42")
        for invalid in [True, 42.1, float("nan"), "42.1", "unresolved"]:
            with self.assertRaises(ValueError):
                canonical_id(invalid)

    def test_wrong_actual_module_or_hash_rejected(self):
        root = Path(__file__).resolve().parents[1]
        with self.assertRaises(RuntimeError):
            bind("json", root)
        with self.assertRaises(RuntimeError):
            bind("oracle.contracts", root, "0" * 64)

    def test_actual_handler_must_match_config_not_directory_label(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(bind_callable(align_subpaths, "oracle.adapters.landmark_rxr.occurrences:align_subpaths", root)["actual"],
                         "oracle.adapters.landmark_rxr.occurrences:align_subpaths")
        with self.assertRaises(RuntimeError):
            bind_callable(align_subpaths, "oracle.verification.alias_probe:run", root)

    def test_boundary_gap_is_preserved_as_explicit_source_edge(self):
        result = align_with_source_connectors(["a", "b", "c", "d"], [["a", "b"], ["c", "d"]])
        self.assertEqual(result.status, "ORDERED_WITH_EXPLICIT_SOURCE_CONNECTORS")
        self.assertEqual(result.connectors, ((1, 2),))
        self.assertEqual(result.intervals, ((0, 1), (2, 3)))

    def test_ambiguous_loop_occurrence_is_not_resolved_by_nearest(self):
        result = align_with_source_connectors(["a", "b", "a", "b", "c"], [["a"], ["a", "b"], ["c"]])
        self.assertEqual(result.status, "AMBIGUOUS")


if __name__ == "__main__":
    unittest.main()
