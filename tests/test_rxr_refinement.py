"""Evidence, complete teaching and isolated RxR boundary regressions."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import unittest

from host import protocol, rxr_contract
from host.compile import compile_prompt, core_library, runtime_review_output, teaching_card
from host.template_selector import library, select_examples
from host.rxr_teaching import dynamic_is_detailed, validate_selection, validate_pair_bundle
from shared.identity import canonical, ContractError
from tools.check_rxr_refinement import check_protected

ROOT = Path(__file__).resolve().parents[1]


class RxRRefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = library('generator', 'rxr-en-us')
        cls.r = library('reviewer', 'rxr-en-us')
        cls.gbank = {x['template_id']: x for x in cls.g}
        cls.rbank = {x['template_id']: x for x in cls.r}

    def test_all_authored_rows_obey_protocol_and_both_projections(self):
        generators = core_library('generator', 'rxr-en-us') + self.g
        reviewers = core_library('reviewer', 'rxr-en-us') + self.r
        self.assertEqual((len(generators), len(reviewers)), (53, 90))
        for row in generators:
            with self.subTest(template=row['template_id']):
                rxr_contract.generator(row['input']['original_instruction'], row['output'])
                for detail in (True, False):
                    self.assertTrue(teaching_card(row, 'generator', detail)['applicable_lesson'])
        for row in reviewers:
            with self.subTest(template=row['template_id']):
                protocol.reviewer(row['review_input']['original_instruction'],
                                  row['review_input']['candidate'], runtime_review_output(row))
                for detail in (True, False):
                    self.assertTrue(teaching_card(row, 'reviewer', detail)['applicable_lesson'])

    def test_all_dynamic_cases_are_detailed_in_every_phase(self):
        query = self.gbank['RxR-GEN-006']['input']['original_instruction']
        selected = {role: select_examples(role, 'rxr-en-us', query, count=4)
                    for role in ('generator', 'reviewer')}
        validate_pair_bundle(selected)
        for role, phase in [('generator', 'initial'), ('generator', 'repair'),
                            ('reviewer', 'review'), ('reviewer', 'recheck')]:
            prompt, _ = compile_prompt(role, phase, profile='rxr-en-us',
                original_instruction=query, selected_ids=selected[role])
            bank = self.gbank if role == 'generator' else self.rbank
            for position, tid in enumerate(selected[role]):
                expected = teaching_card(bank[tid], role, dynamic_is_detailed(role, position))
                self.assertIn(canonical(expected), prompt)
                teaching = expected['teaching']
                self.assertEqual(('stage_evidence' in teaching if role == 'generator'
                                  else 'stage_checks' in teaching), True)
                self.assertNotIn('stage_summary', teaching)
            for row in core_library(role, 'rxr-en-us'):
                self.assertIn(canonical(teaching_card(row, role, True)), prompt)

    def test_generator_complete_cards_keep_all_five_meanings_and_exact_evidence(self):
        for row in self.g:
            summary = teaching_card(row, 'generator', False)['teaching']
            self.assertEqual(summary['source'], row['input']['original_instruction'])
            self.assertEqual(summary['stages'], row['output']['subtasks'])
            self.assertEqual(summary['handoffs'], row['output']['handoffs'])
            for old, new in zip(row['output']['stage_audit'], summary['stage_evidence']):
                for field in ('entry', 'target', 'ending', 'conditions', 'source_quotes', 'carryover'):
                    self.assertEqual(new[field], old[field])
                self.assertEqual(new['process']['candidate_quotes'], old['process']['candidate_quotes'])
                if old['process']['text'] != row['output']['subtasks'][old['subtask_index']]:
                    self.assertEqual(new['process']['text'], old['process']['text'])

    def test_reviewer_complete_cards_keep_findings_coverage_and_handoffs(self):
        for row in self.r:
            card = teaching_card(row, 'reviewer', False)['teaching']
            audit = runtime_review_output(row)
            self.assertEqual(card['review_case'], row['review_input'])
            self.assertEqual(card['findings'], audit['findings'])
            self.assertEqual(card['coverage_evidence'], audit['source_coverage'])
            self.assertEqual(card['handoffs'], audit['handoffs'])
            self.assertEqual(card['prior_finding_reviews'], audit['prior_finding_reviews'])
            self.assertEqual(len(card['stage_checks']), len(audit['stage_checks']))

    def test_projection_does_not_leak_mutable_library_objects(self):
        row = self.gbank['RxR-GEN-006']
        original = copy.deepcopy(row)
        card = teaching_card(row, 'generator', False)
        card['teaching']['stages'][0] = 'tampered'
        card['teaching']['stage_evidence'][0]['conditions']['candidate_quotes'].clear()
        self.assertEqual(row, original)

    def test_source_required_stop_can_be_restored_and_closure_is_not_pass(self):
        for number in (7, 17):
            row = self.rbank[f'RxR-DIAG-{number:02d}']
            audit = row['expected_review']
            self.assertEqual(audit['dimensions']['closure_handoff'], 'issue')
            finding = audit['findings'][0]
            self.assertEqual(finding['failed_layer'], 'L3_stage_checks')
            self.assertIn('closure_handoff', finding['related_dimensions'])
            self.assertIn('Restore that required stopping condition', finding['repair']['instruction'])
            self.assertEqual(next(x['status'] for x in audit['layer_checks']
                                  if x['layer'] == 'L4_handoffs'), 'not_applicable')
            self.assertEqual(audit['handoffs'], [])
        for number in range(1, 21):
            for finding in self.rbank[f'RxR-DIAG-{number:02d}']['expected_review']['findings']:
                self.assertNotIn('do not add STOP or a new endpoint', finding['repair']['instruction'])

    def test_local_nonterminal_defect_is_not_blanket_closure_failure(self):
        self.assertEqual(self.rbank['RxR-DIAG-02']['expected_review']['dimensions']['closure_handoff'], 'pass')

    def test_bathroom_source_evidence_and_frames_are_stage_local(self):
        audit = self.gbank['RxR-GEN-006']['output']['stage_audit']
        self.assertEqual(len(audit[0]['source_quotes']), 2)
        self.assertFalse(any('head back' in q for q in audit[0]['source_quotes']))
        self.assertTrue(any("Once you're between" in q for q in audit[1]['source_quotes']))
        self.assertNotIn('ordinal_or_count', audit[0]['conditions']['text'])
        self.assertNotIn('left', audit[0]['conditions']['candidate_quotes'])
        self.assertEqual(audit[1]['carryover'], [])

    def test_patio_entry_sustained_relation_and_terminal_reference_remain_distinct(self):
        for row, checks in [(self.gbank['RxR-GEN-023'], 'stage_audit'),
                            (self.rbank['RxR-REV-023'], 'stage_checks')]:
            audit = row['output'] if row['role'] == 'generator' else row['expected_review']
            self.assertEqual(audit[checks][1]['entry']['mode'], 'explicit_context')
            self.assertEqual(audit[checks][1]['entry']['candidate_quotes'], ['From the top of these stairs'])
            self.assertIn('Now we will go up a few stairs.', audit[checks][0]['source_quotes'])
            self.assertIn('during patio movement', row['teaching_notes']['five_element_focus'])
            self.assertEqual(audit[checks][2]['carryover'], [])

    def test_approximate_halfway_and_final_facing_have_complete_evidence(self):
        for role in ('generator', 'reviewer'):
            row = core_library(role, 'rxr-en-us')[5]
            audit = row['output']['stage_audit'] if role == 'generator' else row['expected_review']['stage_checks']
            self.assertIn('about halfway down the staircase', audit[0]['conditions']['candidate_quotes'])
        end = self.gbank['RxR-GEN-027']['output']['stage_audit'][0]['ending']
        self.assertTrue(any('facing the big window' in q for q in end['candidate_quotes']))

    def test_dynamic_lessons_are_case_specific_and_actually_projected(self):
        from tools.rxr_teaching_alignment import LESSONS
        for number, lessons in LESSONS.items():
            for role, bank, prefix, idx in [('generator', self.gbank, 'RxR-GEN-', 0),
                                            ('reviewer', self.rbank, 'RxR-REV-', 1)]:
                row = bank[prefix + f'{number:03d}']
                self.assertEqual(teaching_card(row, role, False)['applicable_lesson'], lessons[idx])

    def test_duplicate_handoff_is_rejected_on_rxr_only(self):
        row = core_library('generator', 'rxr-en-us')[3]
        candidate = copy.deepcopy(row['output'])
        candidate['handoffs'][-1] = copy.deepcopy(candidate['handoffs'][0])
        source = row['input']['original_instruction']
        protocol.generator(source, candidate)  # Shared/R2R contract remains unchanged.
        with self.assertRaises(ContractError):
            rxr_contract.generator(source, candidate)
        with self.assertRaises(ContractError):
            rxr_contract.feedback(source, {'findings': []}, {'candidate': candidate, 'responses': []})

    def test_missing_target_is_rejected_without_inventing_object_targets(self):
        row = core_library('generator', 'rxr-en-us')[2]
        candidate = copy.deepcopy(row['output'])
        candidate['stage_audit'][0]['target'] = {'text': None, 'candidate_quotes': []}
        source = row['input']['original_instruction']
        protocol.generator(source, candidate)
        with self.assertRaises(ContractError):
            rxr_contract.generator(source, candidate)
        rxr_contract.generator(source, row['output'])

    def test_explicit_production_ids_obey_counts_and_pair_order(self):
        ids = select_examples('generator', 'rxr-en-us', '')
        with self.assertRaises(ValueError):
            validate_selection('generator', ids[:1], self.g)
        reviewers = select_examples('reviewer', 'rxr-en-us', '')
        validate_pair_bundle({'generator': ids, 'reviewer': reviewers})
        with self.assertRaises(ValueError):
            validate_pair_bundle({'generator': ids, 'reviewer': list(reversed(reviewers))})
        with self.assertRaises(ValueError):
            compile_prompt('generator', 'initial', profile='rxr-en-us', selected_ids=ids[:1])
        validate_selection('generator', [row['template_id'] for row in self.g], self.g, 'all')

    def test_complete_source_and_candidate_inventory_remains_frozen(self):
        report = check_protected()
        self.assertEqual(report['rxr_templates_checked'], 143)
        self.assertEqual(report['legacy_templates_checked'], 20)
        self.assertTrue(report['rxr_sources_candidates_and_retrieval_fields_equal'])

    def test_p2_has_operational_parent_scope_and_p1_owns_layers(self):
        for role in ('generator', 'reviewer'):
            text = (ROOT / role / 'dataset_rules/rxr_en_us.md').read_text()
            local = text.split('## P2', 1)[1]
            for block in local.split('\n### ')[1:]:
                self.assertIn('Parent: P1', block)
                self.assertIn('Trigger:', block)
            self.assertNotIn('P-level fields', local)
        text = (ROOT / 'reviewer/dataset_rules/rxr_en_us.md').read_text()
        self.assertLess(text.index('### Ordered review framework: L0–L6'), text.index('## P2'))
        self.assertIn('textual change is not a prerequisite', text)
        generator = (ROOT / 'generator/dataset_rules/rxr_en_us.md').read_text()
        for marker in ('Repair entry gate:', 'Teaching delivery:'):
            self.assertLess(generator.index(marker), generator.index('## P2'))


if __name__ == '__main__':
    unittest.main()
