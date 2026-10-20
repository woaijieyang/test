from pathlib import Path
import json
import tempfile
import unittest
from oracle.research.full_run import live,has_execution_result
from oracle.research.full_worker import compare_preflight


class FullLifecycle(unittest.TestCase):
    def test_pid_reuse_and_zombie_do_not_count_as_live_owned_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'42').mkdir();p=root/'42/stat'
            def state(status,ticks):p.write_text('42 (python) '+status+' 0'*18+' '+str(ticks))
            state('S',100)
            self.assertTrue(live({'pid':42,'start_ticks':'100'},root))
            self.assertFalse(live({'pid':42,'start_ticks':'99'},root))
            state('Z',100)
            self.assertFalse(live({'pid':42,'start_ticks':'100'},root))

    def test_budget_charge_includes_possible_post_receipt_cleanup(self):
        from oracle.research.full_run import phase_charge
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'exit.json').write_text(json.dumps({'process_cpu_seconds':2.,'ended_monotonic':10.}))
            self.assertEqual(phase_charge(root,905,observed=13.),5.)
            self.assertEqual(phase_charge(root,905,observed=10000.),905)

    def test_settled_cost_does_not_grow_while_run_is_suspended(self):
        from oracle.research.full_run import phase_charge
        from oracle.common.artifacts import digest
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'exit.json').write_text(json.dumps({'process_cpu_seconds':2.,'ended_monotonic':10.}))
            (root/'settled-cost.json').write_text(json.dumps({'charged_cpu_upper_bound_seconds':3.,'exit_sha256':digest(root/'exit.json')}))
            self.assertEqual(phase_charge(root,905,observed=10000.),3.)

    def test_completed_failure_is_a_result_not_a_rerun_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'motion').mkdir()
            (root/'preflight.json').write_text(json.dumps({'native_ready':True}))
            (root/'motion/result.json').write_text(json.dumps({'status':'FAILURE_PRESERVED'}))
            self.assertTrue(has_execution_result(root))

    def test_static_failure_is_retained_without_a_motion_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'preflight.json').write_text(json.dumps({'native_ready':False}))
            self.assertTrue(has_execution_result(root))

    def test_independent_static_endpoint_disagreement_is_fatal(self):
        a={'native_ready':True,'failure':None,'missing_target_indices':[],
           'geometry_catalog_present':True,'endpoint_source_gate':True,'points':[],'links':[]}
        b={**a,'endpoint_source_gate':False}
        with self.assertRaises(ValueError):compare_preflight(a,b)
