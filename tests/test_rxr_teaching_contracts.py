"""Regression checks for authored RxR teaching, not a semantic-score proxy."""
import copy
import json
import re
import unittest
from pathlib import Path

from host import protocol
from host.compile import core_library, runtime_review_output, teaching_card
from host.template_selector import library
from tools.build_rxr_reviewed import ROOT, expected
from tools.rxr_diagnostic_repairs import LOCAL, PARENT
from tools.rxr_positive_repairs import replace_candidate
from tools.rxr_review_contract import finalize


class ReviewedTeaching(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outputs, cls.report = expected()
        cls.rows = {}
        for role in ('generator', 'reviewer'):
            for row in core_library(role, 'rxr-en-us') + library(role, 'rxr-en-us'):
                if row['template_id'] in cls.rows:
                    raise AssertionError('Duplicate active identity')
                cls.rows[row['template_id']] = row

    def test_materialized_files_equal_authored_specification(self):
        for path, (_, desired) in self.outputs.items():
            with self.subTest(path=path):
                self.assertEqual((ROOT / path).read_bytes(), desired)
        self.assertEqual(json.loads((ROOT / 'provenance/rxr_teaching_changes.json').read_bytes()), self.report)

    def test_all_active_templates_use_the_unweakened_runtime_protocol(self):
        self.assertEqual(len(self.rows), 143)
        for tid, row in self.rows.items():
            with self.subTest(template_id=tid):
                if row['role'] == 'generator':
                    protocol.generator(row['input']['original_instruction'], row['output'])
                else:
                    review = runtime_review_output(row)
                    protocol.reviewer(row['review_input']['original_instruction'], row['review_input']['candidate'], review)
                    protocol.validate('reviewer/output.schema.json', review)
                teaching_card(row, row['role'], True)
                teaching_card(row, row['role'], False)

    def test_core_completion_is_not_a_prohibition_or_door_attribute(self):
        for role, prefix in [('generator', 'G'), ('reviewer', 'R')]:
            for number, required in [(2, 'until you reach the second doorway on your right'),
                                     (5, 'enter the bathroom through the first door on your right'),
                                     (7, 'until you are next to it')]:
                row = self.rows[f'RXR-CORE-{prefix}{number:02d}']
                audit = row['output'] if role == 'generator' else row['expected_review']
                checks = audit['stage_audit'] if role == 'generator' else audit['stage_checks']
                self.assertIn(required, ' '.join(checks[0]['ending']['candidate_quotes']))
                self.assertIn(required, audit['handoffs'][0]['preceding_exit']['candidate_quote'])
            row = self.rows[f'RXR-CORE-{prefix}03']
            audit = row['output'] if role == 'generator' else row['expected_review']
            check = (audit['stage_audit'] if role == 'generator' else audit['stage_checks'])[0]
            self.assertEqual(check['ending']['kind'], 'explicit_event')
            self.assertEqual(check['ending']['stop_scope'], 'none')

    def test_repeated_turns_align_with_distinct_actual_events(self):
        coverage = {c['requirement_id']: c for c in self.rows['RxR-REV-009']['expected_review']['source_coverage']}
        self.assertEqual({e['subtask_index'] for e in coverage['SRC-01']['candidate_evidence']}, {0})
        self.assertEqual({e['subtask_index'] for e in coverage['SRC-05']['candidate_evidence']}, {1})
        self.assertFalse(any('Now turn around' in e['quote'] for key in ('SRC-01', 'SRC-05') for e in coverage[key]['candidate_evidence']))

    def test_coverage_proves_movement_not_only_visible_furniture(self):
        row = self.rows['RxR-REV-019']
        coverage = {c['requirement_id']: c for c in row['expected_review']['source_coverage']}
        q8 = ' '.join(e['quote'] for e in coverage['SRC-08']['candidate_evidence'])
        q9 = ' '.join(e['quote'] for e in coverage['SRC-09']['candidate_evidence'])
        self.assertIn('Look towards the left.', q8)
        self.assertIn('walk towards this bench', q8)
        self.assertIn('walk towards this door', q9)
        self.assertNotIn('white table', q9)
        self.assertNotIn('At the table', ' '.join(row['review_input']['candidate']['subtasks']))

    def test_semantic_stop_scope_does_not_follow_the_word_stand(self):
        self.assertEqual(self.rows['RxR-GEN-009']['output']['stage_audit'][0]['ending']['stop_scope'], 'none')
        self.assertEqual(self.rows['RxR-GEN-032']['output']['stage_audit'][-1]['ending']['stop_scope'], 'terminal')

    def test_source_range_and_door_state_survive_local_route_repairs(self):
        self.assertIn('mostly to the end', ' '.join(self.rows['RxR-GEN-023']['output']['subtasks']))
        self.assertIn('now it will open for you', ' '.join(self.rows['RxR-GEN-035']['output']['subtasks']))

    def test_single_span_negatives_really_change_the_declared_event(self):
        for n, spec in LOCAL.items():
            row = self.rows[f'RxR-DIAG-{n:02d}']
            source = row['review_input']['original_instruction']
            candidate = row['review_input']['candidate']['subtasks'][0]
            old, new = spec[:2]
            with self.subTest(template_id=row['template_id']):
                self.assertEqual(source.count(old), 1)
                self.assertEqual(candidate, source.replace(old, new, 1))
                self.assertNotEqual(candidate, source)
                self.assertEqual(row['expected_review']['findings'][0]['source_quote'], old)
                self.assertTrue(all(re.fullmatch(r'SRC-[0-9]{2,}', c['requirement_id']) for c in row['expected_review']['source_coverage']))

    def test_parent_negatives_preserve_all_unaffected_route_text(self):
        for n, spec in PARENT.items():
            parent_n, index, old, new = spec[:4]
            expected_stages = copy.deepcopy(self.rows[f'RxR-REV-{parent_n:03d}']['review_input']['candidate']['subtasks'])
            self.assertEqual(expected_stages[index].count(old), 1)
            expected_stages[index] = expected_stages[index].replace(old, new, 1)
            self.assertEqual(self.rows[f'RxR-DIAG-{n:02d}']['review_input']['candidate']['subtasks'], expected_stages)

    def test_negative_change_and_locality_are_visible_in_compact_cards(self):
        for tid in ('RxR-DIAG-12', 'RxR-DIAG-18', 'RxR-DIAG-20', 'RxR-DIAG-28'):
            row = self.rows[tid]
            card = teaching_card(row, 'reviewer', False)
            self.assertEqual(card['verdict'], 'revise')
            self.assertEqual(card['findings'], runtime_review_output(row)['findings'])
            self.assertTrue(card['findings'][0]['problem'])
            self.assertTrue(card['findings'][0]['source_quote'])

    def test_review_contract_repair_is_idempotent_and_preserves_candidate(self):
        rows = {tid: copy.deepcopy(row) for tid, row in self.rows.items() if row['role'] == 'reviewer'}
        before = copy.deepcopy(rows)
        finalize(rows)
        self.assertEqual(before, rows)

    def test_author_replacement_rejects_missing_or_repeated_span(self):
        row = copy.deepcopy(self.rows['RxR-GEN-019'])
        with self.assertRaises(ValueError):
            replace_candidate(row, 0, 'NOT A SOURCE-SPAN', 'replacement')
        self.assertEqual(row, self.rows['RxR-GEN-019'])


if __name__ == '__main__':
    unittest.main()
