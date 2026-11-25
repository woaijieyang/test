"""Source-only eligibility, phase contracts and preference/rejection boundaries."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from host.compile import ROOT, compile_prompt, teaching_card, core_library
from host.run import prompt_components_metadata
from host.template_selector import library
from host.r2r.selection import select_bundle, teaching_index, _index_blob
from host.r2r.relations import facet_signals, applicability
from tools.r2r_authoring.phase_lessons import lessons, SPECS
from tools.r2r_authoring.build import materialize
from tests.r2r.test_quality import run

SPECIAL={'R2R-GEN-036','R2R-REV-036','R2R-DIAG-30','R2R-GEN-037','R2R-REV-037','R2R-DIAG-31'}

class Eligibility(unittest.TestCase):
    def test_general_wait_does_not_admit_specialist(self):
        for text in ('Enter the room and wait by the bed.','Walk through the hallway on the right, then stop.','Continue until you see the cabinet.'):
            b=select_bundle(text)
            self.assertFalse(SPECIAL & set(b['generator']+b['reviewer']))
            self.assertTrue(any(x['reason']=='inapplicable_specialist' for x in b['evidence']['generator']['excluded']))
    def test_branch_case_has_positive_and_negative_teaching(self):
        b=select_bundle('If the gate is open, go through it. Otherwise, wait beside the wall.')
        self.assertIn('R2R-GEN-036',b['generator']);self.assertIn('R2R-DIAG-30',b['reviewer'])
    def test_explicit_return_retains_positive_and_negative(self):
        b=select_bundle('Leave the doorway, walk around the desk and return to the doorway.')
        self.assertIn('R2R-GEN-037',b['generator']);self.assertIn('R2R-DIAG-31',b['reviewer'])
    def test_weak_back_to_is_not_return_admission(self):
        b=select_bundle('Walk back to the hallway and wait.')
        self.assertNotIn('required_return',facet_signals('Walk back to the hallway and wait.'))
        self.assertNotIn('R2R-GEN-037',b['generator']);self.assertNotIn('R2R-DIAG-31',b['reviewer'])
    def test_original_door_reference_is_strong(self):
        self.assertIn('required_return',facet_signals('Walk back to the original doorway.'))
    def test_either_side_and_prohibition_are_not_unknown_names(self):
        from host.r2r.selection import signals
        for text in ('Keep the chairs on either side.','Do not enter either room.'):
            self.assertNotIn('uncertain_name',facet_signals(text));self.assertNotIn('uncertainty',signals(text))
    def test_prohibited_return_does_not_admit_return_process(self):
        for text in ("Do not return to the door.", "Never go back to the original door."):
            self.assertNotIn('required_return', facet_signals(text))
            self.assertNotIn('R2R-GEN-037', select_bundle(text)['generator'])
    def test_explicit_uncertainty_remains_detectable(self):
        self.assertIn('uncertain_name',facet_signals('The name is unknown.'))
    def test_surface_motion_is_not_a_start(self):
        self.assertIn('surface_motion',facet_signals('Walk a few steps on the red carpet towards the table.'))
        self.assertNotIn('surface_motion',facet_signals('From the red carpet, walk towards the table.'))
    def test_missing_specialist_metadata_rejected(self):
        p=ROOT/'host/r2r/teaching_index.json';data=json.loads(p.read_bytes());data['items'][0].pop('required_query_facets')
        with self.assertRaisesRegex(ValueError,'Missing specialist'):_index_blob(json.dumps(data).encode())
    def test_invalid_gate_rejected(self):
        for value in ('required_return',['invented_facet']):
            with self.assertRaises(ValueError):applicability({'required_query_facets':value},set())
    def test_no_match_uses_general_calibration_not_source_fallback(self):
        b=select_bundle('Proceed.');self.assertEqual(len(b['generator']),4)
        self.assertFalse(SPECIAL & set(b['generator']+b['reviewer']))
    def test_all_selected_specialists_have_real_source_relation(self):
        idx,_=teaching_index()
        for text in ('Enter the hall and stop.','If the doorway is open, enter it. Otherwise, wait.','Return to the original door.'):
            b=select_bundle(text);facets=facet_signals(text)
            for tid in b['generator']+b['reviewer']:self.assertTrue(applicability(idx[tid],facets))

class TeachingBoundaries(unittest.TestCase):
    def bank(self):return {r['template_id']:r for role in ('generator','reviewer') for r in core_library(role,'r2r-en')+library(role,'r2r-en')}
    def test_existing_approved_candidates_unchanged(self):
        import subprocess
        for p in (ROOT/'generator/templates/R2R').rglob('*.json'):
            rel=p.relative_to(ROOT).as_posix();old=json.loads(subprocess.check_output(['git','show','d4cce47841c817083217a7fffa3a1e6235316491:'+rel],cwd=ROOT));new=json.loads(p.read_bytes())
            self.assertEqual(old['input'],new['input']);self.assertEqual(old['output']['subtasks'],new['output']['subtasks'])
    def test_optional_anchor_is_not_relabelled_wrong(self):
        row=self.bank()['R2R-GEN-034'];b=teaching_card(row,'generator',True)['decision_boundary']
        self.assertIn('acceptable',b['counter_boundary']);self.assertIn('Omitting',b['operation'])
        self.assertEqual(self.bank()['R2R-REV-034']['expected_review']['verdict'],'pass')
    def test_boundaries_survive_compact_and_full_projection(self):
        for tid in ('R2R-GEN-015','R2R-GEN-034','R2R-GEN-035','R2R-REV-034'):
            row=self.bank()[tid]
            for detail in (False,True):self.assertEqual(teaching_card(row,row['role'],detail)['decision_boundary'],row['teaching_notes']['decision_boundary'])
    def test_rule_evidence_matches_quotes(self):
        for row in self.bank().values():
            b=row['teaching_notes'].get('decision_boundary')
            if not b:continue
            src=(row.get('input') or row['review_input'])['original_instruction'];parts=(row['output'] if row['role']=='generator' else row['review_input']['candidate'])['subtasks']
            for q in b['source_quotes']:self.assertIn(q,src)
            for e in b['candidate_evidence']:self.assertIn(e['quote'],parts[e['subtask_index']])
    def test_operation_coverage_is_more_than_id_tags(self):
        c=json.loads((ROOT/'provenance/r2r_operation_coverage.json').read_bytes());self.assertFalse(c['priority_rule_gaps'])
        for rule in ('G-P2-B4','G-P2-C1','R-P2-C2','R-P2-C3'):
            self.assertTrue(any(rule in r['rule_ids'] and r.get('evidence_pointer') and r['phases'] for r in c['records']))

class PhaseTeaching(unittest.TestCase):
    def test_real_phase_schemas_and_four_call_rejection(self):
        d=lessons()
        for g,r in zip(d['generator'],d['reviewer']):
            source=g['input']['original_instruction'];candidate=g['expected_output']['candidate']
            result,requests,pending=run(source,[candidate,g['input']['review'],g['expected_output'],r['expected_output']])
            self.assertFalse(pending);self.assertIsNone(result['error'],result['error']);self.assertEqual(result['instruction'],source)
            self.assertEqual([q['phase'] for q in requests],['initial','review','repair','recheck'])
    def test_phase_specific_injection_and_rxr_exclusion(self):
        for role,phase in (('generator','initial'),('generator','repair'),('reviewer','review'),('reviewer','recheck')):
            p,_=compile_prompt(role,phase,profile='r2r-en',original_instruction='Walk into the hall.')
            for spec in SPECS:self.assertEqual(spec['id'] in p,phase in ('repair','recheck'))
            p,_=compile_prompt(role,phase,profile='rxr-en-us',original_instruction='Walk into the hall.')
            for spec in SPECS:self.assertNotIn(spec['id'],p)
    def test_phase_assets_are_frozen_before_calls(self):
        for role,phase,name in (('generator','repair','r2r_repair_examples.json'),('reviewer','recheck','r2r_recheck_examples.json')):
            self.assertIn(f'{role}/dataset_rules/{name}',[x['path'] for x in prompt_components_metadata(role,phase,'r2r-en')['files']])
            self.assertNotIn(f'{role}/dataset_rules/{name}',[x['path'] for x in prompt_components_metadata(role,phase,'rxr-en-us')['files']])
    def test_wrong_advice_is_explicitly_not_gold(self):
        for role,items in lessons().items():
            for e in items:self.assertIn('intentionally wrong',e['note']);self.assertFalse(e['is_official_dataset_record'])
    def test_phase_source_registry_rejects_drift(self):
        changed=copy.deepcopy(SPECS);changed[0]['source']+=' '
        with patch('tools.r2r_authoring.phase_lessons.SPECS',changed):
            with self.assertRaisesRegex(ValueError,'Unregistered phase teaching source'):materialize()
    def test_global_roles_and_schemas_remain_frozen(self):
        import subprocess
        for name in ('shared/semantic_contract.md','generator/repair_examples.json','host/protocol.py','generator/output.schema.json','generator/repair.schema.json','reviewer/output.schema.json'):
            self.assertEqual((ROOT/name).read_bytes(),subprocess.check_output(['git','show','d4cce47841c817083217a7fffa3a1e6235316491:'+name],cwd=ROOT))

if __name__=='__main__':unittest.main()
