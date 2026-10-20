import unittest


class ProgressComparisonLimits(unittest.TestCase):
    def test_three_arm_progress_study_is_not_described_as_state_key_only(self):
        from oracle.research.report import comparison_limits
        m={'config':{'teacher':'oracle.teachers.ordered:execute'},'methods':[
            {'id':'unchanged_control'}, {'id':'cache_only','planning_query_cache':{}},
            {'id':'cache_plus_reference_progress','reference_progress_guard':{}}]}
        lines=comparison_limits(m)
        self.assertTrue(any('cache' in s.lower() and 'progress' in s.lower() for s in lines))
        self.assertFalse(any('Only state key differs' in s for s in lines))
from oracle.research.report import summarize_rows


class StudyReport(unittest.TestCase):
    def test_multi_method_source_denominator_is_not_summed_across_algorithms(self):
        from oracle.research.report import source_scope_summary
        rows=[{'task_key':'a','method':'control','status':'PASS_ORDERED_NATIVE_AND_RATIONAL_REPLAY'},
              {'task_key':'a','method':'candidate','status':'PASS_ORDERED_NATIVE_AND_RATIONAL_REPLAY'}]
        scope=source_scope_summary({'a':{}},[{'task_key':'b'}],rows,2)
        self.assertEqual(scope['pass_count_by_method_with_full_source_denominator'],{'control':1,'candidate':1})
        self.assertEqual(scope['denominator'],2)
        self.assertNotIn('pass_count_with_full_source_denominator',scope)

    def test_portfolio_report_names_real_factor_and_compute_difference(self):
        from oracle.research.report import comparison_limits
        text=' '.join(comparison_limits({'config':{'teacher':'oracle.teachers.ordered:execute','comparison_factor':'guarded_prefix_fallback'}}))
        self.assertNotIn('Only state key differs',text)
        self.assertIn('realized computation',text)

    def test_official_replay_report_does_not_claim_state_key_comparison(self):
        from oracle.research.report import comparison_limits
        text = ' '.join(comparison_limits({'config': {'teacher': 'oracle.teachers.official:execute'}}))
        self.assertNotIn('Only state key differs', text)
        self.assertIn('not algorithm improvement', text)

    def row(self, key, method, passed, wall):
        return {"task_key": key, "cohort": "fixture", "method": method,
                "status": "PASS_ORDERED_NATIVE_AND_RATIONAL_REPLAY" if passed else "FAILURE_PRESERVED",
                "failure": "none" if passed else "search_budget_exhausted",
                "detail": None, "cost": {"total_wall_seconds": wall, "cpu_seconds": wall,
                "actual_native_calls": 5, "native_preview_calls": 10, "source_queries": 15,
                "triangle_checks": 20, "search_expansions": 30, "peak_rss_kib": 100}, "audit_wall_seconds": 1}

    def test_failed_tasks_remain_in_cost_and_denominator(self):
        rows = [self.row("a", "control", True, 1), self.row("b", "control", False, 9),
                self.row("a", "candidate", False, 3), self.row("b", "candidate", True, 5)]
        report = summarize_rows(rows, ["control", "candidate"])
        c = report["cohorts"]["fixture"]
        self.assertEqual(c["methods"]["control"]["tasks"], 2)
        self.assertEqual(c["methods"]["control"]["cost"]["total_wall_seconds"]["p50"], 5)
        self.assertEqual(c["paired"]["candidate"]["recovered"], ["b"])
        self.assertEqual(c["paired"]["candidate"]["regressed"], ["a"])

    def test_missing_pair_and_duplicate_are_rejected(self):
        row = self.row("a", "control", True, 1)
        with self.assertRaises(ValueError): summarize_rows([row], ["control", "candidate"])
        with self.assertRaises(ValueError): summarize_rows([row, row], ["control"])

    def test_different_task_cohorts_are_not_pooled(self):
        a = self.row("a", "control", True, 1)
        b = self.row("b", "control", False, 2); b["cohort"] = "landmark"
        report = summarize_rows([a, b], ["control"])
        self.assertEqual(set(report["cohorts"]), {"fixture", "landmark"})
        self.assertNotIn("overall_success_rate", report)
