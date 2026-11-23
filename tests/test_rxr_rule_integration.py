"""Rule-loading and selection invariants; no simulated navigation claims."""
import json
import re
import unittest
from pathlib import Path

from host.compile import compile_prompt
from host.template_selector import select_examples
from tools.check_rxr_selection_isolation import frozen_checkout, compare

ROOT = Path(__file__).resolve().parents[1]


class RuleIntegration(unittest.TestCase):
    def test_source_queries_keep_exact_frozen_selection(self):
        with frozen_checkout() as baseline:
            report = compare(baseline)
        self.assertTrue(report['source_identity_and_order_equal'])
        self.assertTrue(report['exact_selection_equal'])
        self.assertGreater(report['inputs_compared'], 40)
        print(json.dumps(report, sort_keys=True))

    def test_clarifications_are_loaded_in_both_phases_of_each_role(self):
        source = 'Walk until you reach the second doorway. Do not enter the first doorway.'
        shared = (ROOT / 'shared/dataset_rules/rxr_en_us.md').read_text()
        for role, phases in [('generator', ('initial', 'repair')), ('reviewer', ('review', 'recheck'))]:
            own = (ROOT / role / 'dataset_rules/rxr_en_us.md').read_text()
            other_role = 'reviewer' if role == 'generator' else 'generator'
            other = (ROOT / other_role / 'dataset_rules/rxr_en_us.md').read_text()
            ids = select_examples(role, 'rxr-en-us', source)
            for phase in phases:
                prompt, _ = compile_prompt(role, phase, profile='rxr-en-us', selected_ids=ids,
                                           original_instruction=source)
                self.assertEqual(prompt.count(shared), 1)
                self.assertEqual(prompt.count(own), 1)
                self.assertNotIn(other, prompt)
                self.assertIn('correct occurrence', prompt)
                self.assertIn('particular successor', prompt)
                self.assertIn('not semantic entailment', prompt)

    def test_rule_clarifications_do_not_enter_r2r(self):
        for role, phase in [('generator', 'initial'), ('generator', 'repair'),
                            ('reviewer', 'review'), ('reviewer', 'recheck')]:
            prompt, _ = compile_prompt(role, phase, profile='r2r-en', original_instruction='Walk to the door.')
            self.assertNotIn('## 2. Preserve event identity across oral repetition', prompt)
            self.assertNotIn('Completion evidence must establish the outcome needed by this particular successor.', prompt)

    def test_current_rule_files_do_not_introduce_release_labels(self):
        pattern = re.compile(r'(?i)(?<![a-z0-9])v\d+(?:[._]\d+)*(?![a-z0-9])')
        for name in ('shared/dataset_rules/rxr_en_us.md', 'generator/dataset_rules/rxr_en_us.md',
                     'reviewer/dataset_rules/rxr_en_us.md', 'docs/RXR_TEACHING_REPAIR.md'):
            self.assertIsNone(pattern.search((ROOT / name).read_text()), name)


if __name__ == '__main__':
    unittest.main()
