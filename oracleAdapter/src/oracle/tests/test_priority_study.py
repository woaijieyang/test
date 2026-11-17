import copy
import json
from pathlib import Path
import tempfile
import unittest

from oracle.research.priority_study import make_task, method_pair, compare_outcomes,combined_controller_charge
from oracle.research.full_worker import validate_launchers
from oracle.common.artifacts import digest


class PriorityStudy(unittest.TestCase):
    def test_controller_reservation_deduplicated_only_for_same_process_lifetime(self):
        identity={'pid':1,'start_ticks':'99'}
        self.assertEqual(combined_controller_charge([3705,3805],[identity,identity],identity),3905)
        with self.assertRaises(ValueError):
            combined_controller_charge([3705,3805],[identity,{'pid':1,'start_ticks':'100'}],identity)

    def test_real_worker_launcher_gate_rejects_omission_empty_and_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();files=[root/'oracleAdapter/run.py',root/'scripts/with_runtime.sh']
            for p in files:p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
            with self.assertRaises(ValueError):validate_launchers(root,{})
            with self.assertRaises(ValueError):validate_launchers(root,{'launchers':{}})
            manifest={'launchers':{str(p):digest(p) for p in files}}
            validate_launchers(root,manifest)
            files[0].write_text('changed')
            with self.assertRaises(ValueError):validate_launchers(root,manifest)

    def test_task_conversion_changes_only_execution_source_and_cohort(self):
        original=dict(dataset='landmark_rxr',split='train',task_key='train:1',targets=[[0,0,0],[1,0,0]],
                      start_rotation=[0,0,0,1],privileges=['true_pose'],
                      method_selection={'official_policy':'none'},module_source_sha256='old',cohort='old')
        saved=copy.deepcopy(original);result=make_task(original,'new')
        self.assertEqual(original,saved)
        for k in original:
            if k not in {'module_source_sha256','cohort'}:self.assertEqual(result[k],original[k])

    def test_sealed_and_nontrain_tasks_cannot_enter(self):
        for dataset,split in [('r2r','train'),('rxr','train'),('landmark_rxr','val_unseen')]:
            with self.assertRaises(ValueError):make_task(dict(dataset=dataset,split=split),'new')

    def test_methods_only_change_id_and_priority(self):
        base={'max_expansions_per_search':5000,'action_costs':{'1':1.,'2':.15},'id':'old'}
        methods=method_pair(base)
        self.assertEqual([m['search_priority_weight'] for m in methods],[1.,2.])
        self.assertEqual({k:v for k,v in methods[0].items() if k not in {'id','search_priority_weight'}},
                         {k:v for k,v in methods[1].items() if k not in {'id','search_priority_weight'}})

    def test_missing_pairs_are_rejected(self):
        with self.assertRaises(ValueError):compare_outcomes({'a':True},{},set())

    def test_historical_success_control_failure_cannot_hide_in_both_failed(self):
        r=compare_outcomes({'a':False,'b':False},{'a':False,'b':True},{'a'})
        self.assertFalse(r['development_promotion_gate'])
        self.assertEqual(r['success_control_failures'],['a'])

    def test_recovery_with_no_regression_is_only_development_gate(self):
        r=compare_outcomes({'a':True,'b':False},{'a':True,'b':True},{'a'})
        self.assertTrue(r['development_promotion_gate'])
        self.assertFalse(r['global_acceptance'])
