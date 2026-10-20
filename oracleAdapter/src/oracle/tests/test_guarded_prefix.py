import unittest
from oracle.portfolio.guarded_prefix import GuardedPrefix


class GuardedPrefixTests(unittest.TestCase):
    def test_progress_rejection_preserves_cursor_and_stops_suggestions(self):
        prefix=GuardedPrefix([1,1])
        self.assertIsNone(prefix.propose(lambda a:'legal-state',accept=lambda a,s:'reference_distance_excursion'))
        self.assertEqual(prefix.consumed,0)
        self.assertEqual(prefix.reason,'reference_distance_excursion')
        self.assertIsNone(prefix.propose(lambda a:self.fail('disabled prefix cannot resume')))

    def test_reference_prefix_registry_matches_existing_runtime_contract(self):
        from oracle.teachers.ordered import require_task_contract
        from oracle.registry import validate_contract
        task={'task_key':'rxr-fixture','purpose':'reference_execution','objective':'visit_reference_in_order',
              'privileges':['true_pose','navigation_mesh','goal','reference_path','source_geometry','official_actions']}
        contract=require_task_contract(task,{'protocol_id':'test'},{'official_policy':'guard_then_search'})
        self.assertEqual(validate_contract('guarded_official_reference_portfolio',contract).implementation,
                         'oracle.teachers.ordered:execute')
        with self.assertRaises(ValueError):validate_contract('guarded_official_prefix_portfolio',contract)
        with self.assertRaises(ValueError):validate_contract('ordered_reference_teacher',contract)

    def test_official_privilege_is_required_only_for_explicit_prefix_policy(self):
        from oracle.teachers.ordered import require_task_contract
        task={'task_key':'x','purpose':'landmark_order_execution','objective':'visit_landmark_occurrences_in_order',
              'privileges':['true_pose','navigation_mesh','goal','reference_path','source_geometry','landmark_annotations','official_actions']}
        with self.assertRaises(ValueError):require_task_contract(task,{'protocol_id':'test'})
        self.assertEqual(require_task_contract(task,{'protocol_id':'test'},{'official_policy':'guard_only'}).reset_policy,'initial_only')

    def test_replay_rejects_resumed_or_relabelled_official_prefix(self):
        from oracle.verification.route_replay import audit_prefix_origins
        task={'official_demonstration':{'actions':[2,1,0]}}
        record={'method':{'official_policy':'guard_then_search'},'actions':[2,2,3],
                'action_origins':['official_suggestion','official_suggestion','local_search'],
                'official_source_action_indices':[0,0,None], 'official_primitives_consumed':2,
                'events':[{'kind':'official_prefix_stopped','actual_action_index':2}],
                'official_policy':'guard_then_search'}
        self.assertEqual(audit_prefix_origins(task,record),[])
        record['action_origins'][-1]='official_suggestion'
        self.assertIn('official_prefix_action_provenance',audit_prefix_origins(task,record))

    def test_rejected_suggestion_is_not_consumed_or_executed(self):
        prefix = GuardedPrefix([1, 2, 1])
        calls=[]
        self.assertIsNone(prefix.propose(lambda a: calls.append(a) or None))
        self.assertEqual(calls,[1]);self.assertEqual(prefix.consumed,0)
        self.assertEqual(prefix.reason,'proposal_rejected')
        self.assertIsNone(prefix.propose(lambda a:self.fail('must stay disabled')))

    def test_sequence_cursor_survives_reference_boundaries(self):
        prefix=GuardedPrefix([2,1])
        self.assertEqual(prefix.propose(lambda a:'next'),(2,'next'))
        self.assertEqual(prefix.propose(lambda a:'next2'),(1,'next2'))
        self.assertIsNone(prefix.propose(lambda a:self.fail('exhausted')))
        self.assertEqual(prefix.reason,'source_exhausted');self.assertEqual(prefix.consumed,2)

    def test_bad_action_cannot_enter_portfolio(self):
        with self.assertRaises(ValueError):GuardedPrefix([0])
        with self.assertRaises(ValueError):GuardedPrefix([True])
