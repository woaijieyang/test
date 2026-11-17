from pathlib import Path
import json
import tempfile
import unittest

from oracle.research.full_report import measurements,cost_statistics,summarize,resolve_evidence,phase_cost,failure_explanation,PASS


class FullReportTests(unittest.TestCase):
    def preflight(self):
        return dict(missing_target_indices=[],geometry_catalog_present=True,points=[],links=[],endpoint_source_gate=True)

    def test_budget_failure_is_not_a_physical_unreachability_claim(self):
        result=dict(boundaries=[],positions=[[0,0,0]],search_attempts=[{'expansions':5000}],detail='max_expansions')
        r=failure_explanation({'targets':[[0,0,0],[1,0,0]]},
            dict(status='FAILURE_PRESERVED',failure='search_budget_exhausted'),self.preflight(),result)
        self.assertEqual(r['stage'],'bounded_search');self.assertFalse(r['physical_unreachability_proven'])
        self.assertEqual(r['next_required_reference_index'],1)

    def test_route_witness_does_not_hide_endpoint_contact(self):
        pre=self.preflight();pre.update(endpoint_indices=[0,1],endpoint_source_gate=False,
            points=[dict(index=1,navigable=True,source_contact={'triangle':3})])
        r=failure_explanation({'targets':[[0,0,0],[1,0,0]]},
            dict(status='ROUTE_WITNESS_ONLY_ENDPOINT_SOURCE_GATE_FAIL',failure='source_geometry_contact_at_reference_endpoint'),
            pre,audit={'full_route_accepted':True,'physical_alerts':[]})
        self.assertEqual(r['stage'],'reference_endpoint_source_gate')
        self.assertEqual(r['source_contact_endpoint_indices'],[1])
        self.assertTrue(r['full_route_accepted']);self.assertFalse(r['endpoint_source_gate'])

    def test_static_missing_points_and_edges_remain_separate_observations(self):
        pre=self.preflight();pre.update(missing_target_indices=[2],links=[dict(index=0,finite=False)])
        r=failure_explanation({'targets':[]},dict(status='STATIC_FAILURE_PRESERVED',failure='identity_or_adaptation_missing'),pre)
        self.assertEqual(r['missing_target_indices'],[2]);self.assertEqual(r['disconnected_reference_edge_indices'],[0])
        self.assertFalse(r['physical_unreachability_proven'])

    def row(self,key,status,wall,privileges=None):
        return dict(task_key=key,contract=dict(dataset='fixture',objective='ordered',privileges=privileges or []),
                    status=status,failure=None if status==PASS else 'search_budget_exhausted',
                    motion_attempted=True,teacher_cost={'total_wall_seconds':wall},replay_wall_seconds=2,
                    search_calls=1,official_primitives_consumed=0,search_failures=['search_budget_exhausted'],
                    switch_reasons=[],actions_by_origin={'local_search':3})

    def test_failures_costs_and_static_denominators_preserved(self):
        rows=[self.row('a',PASS,1),self.row('b','FAILURE_PRESERVED',9)]
        static=self.row('c','STATIC_FAILURE_PRESERVED',None);static['motion_attempted']=False
        report=summarize(rows+[static])[0]
        self.assertEqual(report['tasks'],3);self.assertEqual(report['accepted_fraction'],1/3)
        self.assertEqual(report['teacher_cost']['total_wall_seconds']['p50'],5)
        self.assertEqual(report['teacher_cost']['total_wall_seconds']['count'],2)
        self.assertEqual(report['teacher_cost']['cpu_seconds']['missing'],2)

    def test_different_information_never_pooled(self):
        rows=[self.row('a',PASS,1),self.row('b',PASS,1,['official_actions'])]
        self.assertEqual(len(summarize(rows)),2)
        with self.assertRaises(ValueError):summarize(rows+[rows[0]])

    def test_unknown_cost_not_zero_and_negative_not_accepted(self):
        self.assertIsNone(measurements([None])['sum'])
        self.assertEqual(measurements([None,2])['missing'],1)
        with self.assertRaises(ValueError):measurements([-1])
        self.assertNotIn('sum',cost_statistics('peak_rss_kib',[10,20]))

    def test_explicit_export_relocation_rejects_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(resolve_evidence('/source/run/jobs/a.json',tmp,'/source/run'),Path(tmp)/'jobs/a.json')
            with self.assertRaises(ValueError):resolve_evidence('/source/other/a.json',tmp,'/source/run')
            with self.assertRaises(ValueError):resolve_evidence('/source/run/../a.json',tmp,'/source/run')

    def test_phase_identity_and_missing_exit_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);start=dict(manifest_sha256='m',pid=12,start_ticks='50',role='audit',started_monotonic=1)
            (p/'start.json').write_text(json.dumps(start))
            self.assertIsNone(phase_cost(p,'m')['process_cpu_seconds'])
            end=dict(pid=12,start_ticks='51',ended_monotonic=3,process_cpu_seconds=1,status='COMPLETE')
            (p/'exit.json').write_text(json.dumps(end))
            with self.assertRaises(ValueError):phase_cost(p,'m')
