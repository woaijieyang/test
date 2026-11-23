"""Check deliberately reviewed RxR prompt pins, never self-update expectations.

The fixture pins actual bytes and schema, not estimated tokens or navigation SR.
R2R isolation is independently checked against the immutable source checkout.
"""
import json
import subprocess
import unittest
from pathlib import Path

from host.compile import compile_prompt, core_library
from host.template_selector import select_examples
from shared.identity import canonical, text_hash

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/rxr_prompt_pins.json'


class RxRPromptSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins = json.loads(FIXTURE.read_text(encoding='utf-8'))

    def compile(self, role, phase):
        return compile_prompt(
            role, phase, profile=self.pins['profile'],
            original_instruction=self.pins['query'],
            selected_ids=self.pins['selected_ids'][role],
        )

    def test_measured_query_selection_is_not_replaced_by_current_defaults(self):
        for role in ('generator', 'reviewer'):
            actual = select_examples(role, self.pins['profile'], self.pins['query'])
            self.assertEqual(actual, self.pins['selected_ids'][role])

    def test_all_measured_prompt_and_schema_hashes_match_without_normalization(self):
        before = FIXTURE.read_bytes()
        for key, expected in self.pins['prompts'].items():
            role, phase = key.split('/')
            with self.subTest(phase=key):
                prompt, schema = self.compile(role, phase)
                self.assertEqual(text_hash(prompt), expected)
                self.assertEqual(text_hash(canonical(schema)), self.pins['schema_sha256'][key])
                self.assertEqual(len(prompt.encode('utf-8')), self.pins['utf8_bytes'][key])
        self.assertEqual(FIXTURE.read_bytes(), before)

    def test_recheck_keeps_the_frozen_review_system_contract(self):
        review_prompt, review_schema = self.compile('reviewer', 'review')
        recheck_prompt, recheck_schema = self.compile('reviewer', 'recheck')
        self.assertEqual(recheck_prompt, review_prompt)
        self.assertEqual(recheck_schema, review_schema)
        self.assertEqual(text_hash(recheck_prompt), self.pins['prompts']['reviewer/review'])
        self.assertEqual(text_hash(canonical(recheck_schema)), self.pins['schema_sha256']['reviewer/review'])

    def test_fixed_core_order_is_present_in_each_phase(self):
        for role, phase in (
            ('generator', 'initial'), ('generator', 'repair'),
            ('reviewer', 'review'), ('reviewer', 'recheck'),
        ):
            with self.subTest(role=role, phase=phase):
                rows = core_library(role, self.pins['profile'])
                self.assertEqual(len(rows), 10)
                ids = [row['template_id'] for row in rows]
                prompt, _ = self.compile(role, phase)
                self.assertIn(', '.join(ids), prompt)
                positions = [prompt.index('"template_id":' + canonical(tid))
                             for tid in ids]
                self.assertEqual(positions, sorted(positions))

    def test_common_contract_and_compiler_match_the_reviewed_measurement(self):
        # Changes here require an explicit reviewed rebaseline, not CI rewriting
        # the expected prompt hash after observing whatever the code produced.
        protected = (
            'shared/semantic_contract.md', 'generator/prompt.md',
            'reviewer/prompt.md', 'generator/repair.md',
            'generator/output.schema.json', 'generator/repair.schema.json',
            'reviewer/output.schema.json', 'host/compile.py',
            'host/template_selector.py', 'host/rxr_retrieval.py',
        )
        commit = self.pins['measured_source_commit']
        for path in protected:
            with self.subTest(path=path):
                expected = subprocess.check_output(
                    ['git', 'show', commit + ':' + path], cwd=ROOT)
                self.assertEqual((ROOT / path).read_bytes(), expected)

    def test_bytes_are_not_reported_as_verified_model_tokens(self):
        self.assertIs(self.pins['token_budget_verified'], False)
        self.assertIs(self.pins['navigation_evaluated'], False)
        self.assertEqual(set(self.pins['prompts']), set(self.pins['schema_sha256']))
        self.assertEqual(set(self.pins['prompts']), set(self.pins['utf8_bytes']))
        for value in self.pins['utf8_bytes'].values():
            self.assertIs(type(value), int)
            self.assertGreater(value, 0)


if __name__ == '__main__':
    unittest.main()
