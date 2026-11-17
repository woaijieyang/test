import unittest
from oracle.research.full_run import budget_worker_cap,Budget


class BudgetSlotTests(unittest.TestCase):
    def test_actual905second_reservation_limits_fresh3hour_arm_to7slots(self):
        count=budget_worker_cap(10800,3605,905,0)
        self.assertEqual(count,7)
        b=Budget(10800,{'controller':3605})
        for n in range(count):b.reserve(str(n),905)
        self.assertLessEqual(b.charged(),10800)

    def test_reviewed_resume_and_live_workers_keep_their_reserved_slots(self):
        self.assertEqual(budget_worker_cap(10800,7491.94,905,0),3)
        self.assertEqual(budget_worker_cap(10800,10200,905,3),3)
        self.assertEqual(budget_worker_cap(10800,11000,905,3),3)

    def test_no_headroom_means_no_new_worker_not_a_budget_increase(self):
        self.assertEqual(budget_worker_cap(10800,10800,905,0),0)
        with self.assertRaises(ValueError):budget_worker_cap(10800,3605,0,0)
