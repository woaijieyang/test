import unittest


class ContinuationTests(unittest.TestCase):
    def functions(self):
        try:
            from oracle.research.continuation import partition_entries,remaining_cpu_seconds
        except ImportError as exc:self.fail('Identity-bound continuation not implemented: '+str(exc))
        return partition_entries,remaining_cpu_seconds

    def test_completed_navigation_failures_are_not_reexecuted(self):
        partition,_=self.functions()
        entries=[{'record':{'task_key':k}} for k in ('passed','failed','unfinished')]
        rows=[dict(task_key='passed',status='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES'),dict(task_key='failed',status='FAILURE_PRESERVED')]
        self.assertEqual([e['record']['task_key'] for e in partition(entries,rows)],['unfinished'])
        with self.assertRaises(ValueError):partition(entries,rows+[rows[0]])
        with self.assertRaises(ValueError):partition(entries,[dict(task_key='unfinished',status='INFRASTRUCTURE_OR_INTEGRITY_STOP')])

    def test_remaining_budget_subtracts_parent_charge_without_reset(self):
        _,budget=self.functions()
        self.assertEqual(budget(720,154993.24807027262),2437006)
        with self.assertRaises(ValueError):budget(1,3600)
        with self.assertRaises(ValueError):budget(1,-1)
