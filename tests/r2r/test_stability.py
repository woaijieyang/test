"""Runtime teaching guards and read-only cross-profile CI; no model-score claims."""
from copy import deepcopy
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from host.compile import ROOT, compile_prompt
from host.run import prompt_components_metadata
from host.r2r.phase_teaching import phase_examples, _validated
from host.r2r.relations import applicability
from host.r2r.selection import _linked_index, teaching_index, select_bundle, validate_selection
from host.template_selector import library
from tools.r2r_authoring.integrate import expected


class FrozenSelectionGuards(unittest.TestCase):
    BRANCH = 'If the gate is open, walk through it. Otherwise, wait near the wall.'
    def test_explicit_generator_ids_cannot_bypass_applicability(self):
        ids = select_bundle(self.BRANCH)['generator']
        self.assertIn('R2R-GEN-036', ids)
        with self.assertRaisesRegex(ValueError, 'Inapplicable R2R specialist'):
            compile_prompt('generator', profile='r2r-en', selected_ids=ids,
                           original_instruction='Enter the room and wait.')

    def test_explicit_reviewer_ids_cannot_bypass_applicability(self):
        ids = select_bundle(self.BRANCH)['reviewer']
        self.assertIn('R2R-DIAG-30', ids)
        with self.assertRaisesRegex(ValueError, 'Inapplicable R2R specialist'):
            compile_prompt('reviewer', 'review', profile='r2r-en', selected_ids=ids,
                           original_instruction='Enter the room and wait.')

    def test_frozen_specialists_require_actual_source(self):
        ids = select_bundle(self.BRANCH)['generator']
        with self.assertRaisesRegex(ValueError, 'Inapplicable R2R specialist'):
            compile_prompt('generator', profile='r2r-en', selected_ids=ids)

    def test_valid_specialists_compile_in_all_four_phases(self):
        bundle = select_bundle(self.BRANCH)
        for role, phases in (('generator', ('initial', 'repair')),
                             ('reviewer', ('review', 'recheck'))):
            for phase in phases:
                text, _ = compile_prompt(role, phase, profile='r2r-en',
                                         selected_ids=bundle[role], original_instruction=self.BRANCH)
                self.assertIn(bundle[role][0], text)

    def test_offline_all_mode_retains_full_library(self):
        ids = [r['template_id'] for r in library('generator', 'r2r-en')]
        validate_selection('generator', ids, 'all', source_text='Proceed.')
        self.assertIn('R2R-GEN-036', ids)

    def test_general_no_match_still_uses_four_examples(self):
        bundle = select_bundle('Proceed.')
        self.assertEqual(len(bundle['generator']), 4)
        compile_prompt('generator', profile='r2r-en', selected_ids=bundle['generator'],
                       original_instruction='Proceed.')

    def test_invalid_source_type_fails(self):
        ids = select_bundle('Proceed.')['generator']
        with self.assertRaises(TypeError):
            validate_selection('generator', ids, source_text=12)

    def test_duplicate_or_nonstrings_in_gate_fail(self):
        for gate in (['required_return', 'required_return'], [['required_return']], [None]):
            with self.assertRaises(ValueError):
                applicability({'required_query_facets': gate}, {'required_return'})


class ActiveRuleLinks(unittest.TestCase):
    def inputs(self):
        return [(ROOT/'host/r2r/teaching_index.json').read_bytes(),
                (ROOT/'generator/dataset_rules/r2r_en.md').read_bytes(),
                (ROOT/'reviewer/dataset_rules/r2r_en.md').read_bytes()]

    def test_current_links_resolve(self):
        self.assertEqual(len(_linked_index(*self.inputs())), 125)

    def test_unknown_correct_prefix_is_not_accepted(self):
        blob, gen, rev = self.inputs()
        data = json.loads(blob)
        data['items'][0]['rule_ids'] = ['G-P2-Z9']
        with self.assertRaisesRegex(ValueError, 'unknown active role rule'):
            _linked_index(json.dumps(data).encode(), gen, rev)

    def test_changed_rules_invalidate_index_cache(self):
        blob, gen, rev = self.inputs()
        _linked_index(blob, gen, rev)
        changed = gen.replace(b'### G-P2-B1 ', b'### G-P2-Z9 ')
        self.assertNotEqual(changed, gen)
        with self.assertRaisesRegex(ValueError, 'unknown active role rule'):
            _linked_index(blob, changed, rev)
        self.assertEqual(len(_linked_index(blob, gen, rev)), 125)

    def test_empty_role_rules_are_not_accepted(self):
        blob, gen, rev = self.inputs()
        with self.assertRaisesRegex(ValueError, 'Missing active'):
            _linked_index(blob, b'', rev)


class PhaseContracts(unittest.TestCase):
    def data(self, role='generator'):
        phase = 'repair' if role == 'generator' else 'recheck'
        return phase, phase_examples(role, phase)

    def check_invalid(self, role, data):
        phase = 'repair' if role == 'generator' else 'recheck'
        with self.assertRaises((ValueError, KeyError, TypeError)):
            _validated(role, phase, json.dumps(data).encode(), (ROOT/role/'dataset_rules/r2r_en.md').read_bytes())

    def test_expected_contracts_validate(self):
        for role in ('generator', 'reviewer'):
            phase, data = self.data(role)
            self.assertEqual(_validated(role, phase, json.dumps(data).encode(), (ROOT/role/'dataset_rules/r2r_en.md').read_bytes()), data)

    def test_returns_defensive_copy(self):
        _, data = self.data()
        old = data[0]['id']
        data[0]['id'] = 'changed'
        self.assertEqual(self.data()[1][0]['id'], old)

    def test_duplicate_ids_rejected(self):
        _, data = self.data()
        data.append(deepcopy(data[0]))
        self.check_invalid('generator', data)

    def test_empty_list_rejected(self):
        self.check_invalid('generator', [])

    def test_wrong_phase_rejected(self):
        _, data = self.data()
        data[0]['phase'] = 'initial'
        self.check_invalid('generator', data)

    def test_fake_official_identity_rejected(self):
        _, data = self.data()
        data[0]['is_official_dataset_record'] = True
        self.check_invalid('generator', data)

    def test_incomplete_generator_candidate_rejected(self):
        _, data = self.data()
        del data[0]['expected_output']['candidate']['stage_audit']
        self.check_invalid('generator', data)

    def test_unresolved_old_finding_cannot_be_omitted_from_r1(self):
        _, data = self.data('reviewer')
        data[0]['expected_output']['prior_finding_reviews'] = []
        self.check_invalid('reviewer', data)

    def test_invalid_quote_rejected(self):
        _, data = self.data()
        data[0]['expected_output']['responses'][0]['source_quotes'] = ['invented route fact']
        self.check_invalid('generator', data)

    def test_unknown_phase_rule_is_rejected(self):
        _, data = self.data()
        data[0]['rule_ids'] = ['G-P2-Z9']
        self.check_invalid('generator', data)

    def test_cross_role_phase_rule_is_rejected(self):
        _, data = self.data()
        data[0]['rule_ids'] = ['R-P2-C1']
        self.check_invalid('generator', data)

    def test_initial_phase_not_supported(self):
        with self.assertRaises(ValueError):
            phase_examples('generator', 'initial')

    def test_disk_changes_cannot_hide_in_validation_cache(self):
        phase, data = self.data()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/'generator/dataset_rules/r2r_repair_examples.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(data))
            (path.parent/'r2r_en.md').write_bytes((ROOT/'generator/dataset_rules/r2r_en.md').read_bytes())
            with patch('host.r2r.phase_teaching.ROOT', root):
                self.assertEqual(len(phase_examples('generator', phase)), 2)
                path.write_text('[]')
                with self.assertRaises(ValueError):
                    phase_examples('generator', phase)

    def test_phase_validator_is_part_of_frozen_runtime(self):
        for role, phase in (('generator', 'repair'), ('reviewer', 'recheck')):
            paths = [r['path'] for r in prompt_components_metadata(role, phase, 'r2r-en')['files']]
            self.assertIn('host/r2r/phase_teaching.py', paths)
            paths = [r['path'] for r in prompt_components_metadata(role, phase, 'rxr-en-us')['files']]
            self.assertNotIn('host/r2r/phase_teaching.py', paths)


class WorkflowOwnership(unittest.TestCase):
    def test_workflow_matches_reviewed_authoring_source(self):
        path = '.github/workflows/rxr-development.yml'
        self.assertEqual((ROOT/path).read_text(), expected()[path])

    def test_workflow_maintenance_triggers_verification(self):
        workflow = (ROOT/'.github/workflows/rxr-development.yml').read_text()
        self.assertIn("      - '.github/workflows/rxr-development.yml'", workflow)

    def test_managed_branch_uses_prebuild_head_not_old_r2r_policy(self):
        workflow = (ROOT/'.github/workflows/rxr-development.yml').read_text()
        self.assertIn('comparison="$GITHUB_SHA"', workflow)
        self.assertIn('source_inventory.json', workflow)
        self.assertIn('R2R_BUILD_BASELINE_DIR=', workflow)
        self.assertNotIn('R2R_BASELINE_DIR=', workflow)
        self.assertEqual(workflow.count('--baseline "$R2R_BUILD_BASELINE_DIR"'), 2)
        self.assertIn('git diff --exit-code', workflow)
        self.assertIn("if: env.R2R_MANAGED == 'true'", workflow)

    def test_managed_branch_does_not_publish_or_refresh_rxr_pins(self):
        workflow = (ROOT/'.github/workflows/rxr-development.yml').read_text()
        self.assertIn("Commit the complete tested artifact set before pushing\n        if: env.R2R_MANAGED != 'true'", workflow)
        self.assertIn("Record actual validation and inherited label audit\n        if: env.R2R_MANAGED != 'true'", workflow)
        self.assertIn('if test "$R2R_MANAGED" != true; then\n            python -B tools/refresh_rxr_integrity.py', workflow)

    def test_discovery_and_missing_external_fixture_are_qualified(self):
        workflow = (ROOT/'.github/workflows/rxr-development.yml').read_text()
        self.assertIn("discover('tests', top_level_dir='.')", workflow)
        self.assertIn("test.id().endswith('.test_release_transaction')", workflow)
        self.assertIn("'FileNotFoundError' in error and 'manage_release.py' in error", workflow)
        # Execute the actual workflow discovery preamble in a clean interpreter.
        # Do not execute the suite recursively; reject all unexpected import errors.
        block = workflow.split('      - name: Run inherited and new regression tests\n', 1)[1]
        block = block.split('      - name:', 1)[0]
        code = textwrap.dedent(block.split("python -B - <<'PY'\n", 1)[1]
                               .split('          result=unittest.TextTestRunner', 1)[0])
        code += "\nerrors=[str(getattr(t,'_exception','')) for t in selected if hasattr(t,'_exception')]\n"
        code += "print(json.dumps(dict(errors=errors, count=selected.countTestCases())))\n"
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                   R2R_BUILD_BASELINE_DIR=str(ROOT))
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                                env=env, check=True, capture_output=True, text=True, timeout=30)
        report = json.loads(result.stdout)
        self.assertEqual(report['errors'], [])
        self.assertGreaterEqual(report['count'], 300)


if __name__ == '__main__':
    unittest.main()
