"""Read-only conversion, legacy-coverage and actual-prompt isolation checks.

Exact clause retention and structural checks are not semantic certification.
Do not rewrite approved expectations or call a model from these tests.
"""
import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path

from host.compile import compile_prompt
from shared.identity import canonical, text_hash

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'provenance/rxr_role_conversion.json'


def source_at(commit, path):
    return subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT)


def sentences(text):
    return re.split(r'(?<=[.!?])\s+(?=[A-Z`])', text)


def clauses(text):
    rows = {}
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith('#'):
            continue
        line = re.sub(r'^\d+\. ', '', line)
        for ordinal, clause in enumerate(sentences(line)):
            rows[(line_no, ordinal)] = clause
    return rows


def section(text, heading):
    start = text.index(heading + '\n') + len(heading) + 1
    tail = text[start:]
    boundary = re.search(r'^#{2,3} ', tail, re.M)
    return tail[:boundary.start()] if boundary else tail


class RxRRoleHierarchyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest_bytes = MANIFEST.read_bytes()
        cls.data = json.loads(cls.manifest_bytes)

    def test_every_previous_clause_has_one_traceable_destination(self):
        for role, spec in self.data['roles'].items():
            old = source_at(self.data['base_commit'], spec['path'])
            blob = hashlib.sha1(b'blob ' + str(len(old)).encode() + b'\0' + old).hexdigest()
            self.assertEqual(blob, spec['baseline_blob_sha'])
            old_clauses = clauses(old.decode('utf-8'))
            mapped = [(row[0], row[1]) for row in spec['clause_map']]
            self.assertEqual(len(mapped), len(set(mapped)))
            self.assertEqual(set(mapped), set(old_clauses))
            new = (ROOT / spec['path']).read_text(encoding='utf-8')
            for line_no, ordinal, target in spec['clause_map']:
                with self.subTest(role=role, line=line_no, clause=ordinal):
                    self.assertIn(old_clauses[(line_no, ordinal)],
                                  section(new, spec['sections'][target]))

    def test_reviewed_rule_bytes_are_pinned(self):
        for spec in self.data['roles'].values():
            content = (ROOT / spec['path']).read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), spec['new_sha256'])
            self.assertEqual(len(content), spec['new_bytes'])

    def test_layers_are_role_local_and_ordered_without_node_quotas(self):
        for role, spec in self.data['roles'].items():
            text = (ROOT / spec['path']).read_text(encoding='utf-8')
            self.assertEqual(re.findall(r'^## (P[012])\b', text, re.M), ['P0', 'P1', 'P2'])
            self.assertIn('not severity', text)
            self.assertNotIn('current_only', text)
            self.assertNotIn('current_and_history', text)
            self.assertNotRegex(text, r'(?i)(?<![a-z0-9])v\d+(?:[._]\d+)*')

    def test_review_layers_are_one_complete_p1_framework_item(self):
        text = (ROOT / self.data['roles']['reviewer']['path']).read_text(encoding='utf-8')
        start = text.index('### Ordered review framework: L0–L6')
        end = text.index('### Preconditions and adjacent-stage acceptance', start)
        self.assertLess(text.index('## P1'), start)
        self.assertLess(end, text.index('## P2'))
        self.assertEqual(re.findall(r'^L([0-6]):', text[start:end], re.M), list('0123456'))
        old = source_at(self.data['base_commit'], self.data['roles']['reviewer']['path']).decode()
        for line in old.splitlines():
            if re.match(r'^L[0-6]:', line):
                self.assertIn(line, text[start:end])

    def test_five_elements_and_handoff_remain_framework_requirements(self):
        for role, spec in self.data['roles'].items():
            text = (ROOT / spec['path']).read_text(encoding='utf-8')
            framework = text[text.index('## P1'):text.index('## P2')]
            for word in ('Entry', 'Target', 'Process', 'Ending', 'Conditions'):
                self.assertIn(word, framework)
            self.assertIn('first unperformed action', framework)
            self.assertIn('count origin', framework)
            self.assertIn('repair', framework.lower())

    def test_shared_runtime_and_all_teaching_sources_are_unchanged(self):
        # Ignore deliberately changed role files and generated build/manifest outputs.
        paths = ['shared', 'adapter', 'host', 'renderer',
                 'generator/prompt.md', 'generator/repair.md', 'generator/repair_examples.json',
                 'generator/output.schema.json', 'generator/repair.schema.json',
                 'reviewer/prompt.md', 'reviewer/checklist.md', 'reviewer/output.schema.json',
                 'generator/dataset_rules/r2r_en.md', 'reviewer/dataset_rules/r2r_en.md',
                 'generator/templates/RxR', 'reviewer/templates/RxR',
                 'generator/templates/R2R', 'reviewer/templates/R2R']
        changed = subprocess.check_output(
            ['git', 'diff', '--name-only', self.data['base_commit'], '--', *paths],
            cwd=ROOT, text=True)
        self.assertEqual(changed.strip(), '', changed)

    def test_four_stage_compilation_changes_only_approved_role_block(self):
        measurements = {}
        for role, phase in [('generator', 'initial'), ('generator', 'repair'),
                            ('reviewer', 'review'), ('reviewer', 'recheck')]:
            with self.subTest(role=role, phase=phase):
                spec = self.data['roles'][role]
                new = (ROOT / spec['path']).read_text(encoding='utf-8').strip()
                old = source_at(self.data['base_commit'], spec['path']).decode('utf-8').strip()
                prompt, schema = compile_prompt(role, phase, profile='rxr-en-us',
                    original_instruction=self.data['frozen_query'],
                    selected_ids=self.data['frozen_selected_ids'][role])
                self.assertEqual(prompt.count(new), 1)
                other = 'reviewer' if role == 'generator' else 'generator'
                other_rule = (ROOT / self.data['roles'][other]['path']).read_text(encoding='utf-8').strip()
                self.assertNotIn(other_rule, prompt)
                restored = prompt.replace(new, old, 1)
                key = role + '/' + ('review' if phase == 'recheck' else phase)
                self.assertEqual(text_hash(restored), self.data['baseline_prompts'][key])
                measurements[role + '/' + phase] = {
                    'sha256': text_hash(prompt), 'schema_sha256': text_hash(canonical(schema)),
                    'utf8_bytes': len(prompt.encode('utf-8'))}
        print('RXR_LAYER_MEASUREMENTS=' + json.dumps(measurements, sort_keys=True))

    def test_historical_reference_is_pinned_not_silently_reimported(self):
        # Blob IDs independently read from the historical commit, not guessed
        # from a title, a branch name or a different revision of the prompts.
        expected = {'generator/prompt.md': '167c2e2c8d28f5ae55d99b4417bd9be6c519e31a',
                    'reviewer/prompt.md': '1c45b61b404c50bb6d8c9e11e6186f9d7d76a66d'}
        self.assertEqual(self.data['historical_source_blobs'], expected)
        historical = {}
        for path, sha in expected.items():
            data = source_at(self.data['historical_commit'], path)
            self.assertEqual(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(), sha)
            historical[path] = data.decode('utf-8')
        self.assertIn("status='needs_review'", historical['generator/prompt.md'])
        self.assertIn('## Codex primary ownership', historical['reviewer/prompt.md'])
        self.assertIn('not another reviewer child', historical['reviewer/prompt.md'])
        decisions = self.data['historical_comparison']
        self.assertTrue(any('not restored' in row['status'] for row in decisions))
        self.assertIs(self.data['semantic_equivalence_certified'], False)
        self.assertIs(self.data['navigation_evaluated'], False)

    def test_tests_never_update_conversion_manifest(self):
        self.assertEqual(MANIFEST.read_bytes(), self.manifest_bytes)


if __name__ == '__main__':
    unittest.main()
