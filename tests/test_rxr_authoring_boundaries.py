"""Mechanical authoring checks do not turn substring matches into semantics."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import build_rxr_teaching as builder
from tools.rxr_evidence_alignment import mapped_quote


class EvidenceAlignmentTests(unittest.TestCase):
    def test_repeated_quote_cannot_pick_the_wrong_event(self):
        source = 'Turn left. Pass the table. Turn left.'
        start = source.rindex('Turn left.')
        candidate = source[:start] + 'Turn right.'
        with self.assertRaisesRegex(ValueError, 'Ambiguous repeated evidence'):
            mapped_quote(source, candidate, 'Turn left.', start, 'Turn left.', 'Turn right.')
        self.assertEqual(mapped_quote(source, candidate, 'Turn left.', start, 'Turn left.', 'Turn right.', occurrence=0),
                         ('Turn left.', False, 0))
        self.assertEqual(mapped_quote(source, candidate, 'Turn left.', start, 'Turn left.', 'Turn right.', occurrence=start),
                         ('Turn right.', True, start))

    def test_contextual_quote_selects_actual_occurrence(self):
        source = 'Turn left. Pass the table. Turn left.'
        start = source.rindex('Turn left.')
        candidate = source[:start] + 'Turn right.'
        self.assertEqual(mapped_quote(source, candidate, 'Pass the table. Turn left.', start, 'Turn left.', 'Turn right.'),
                         ('Pass the table. Turn right.', True, 11))

    def test_unaffected_repeated_words_remain_exact(self):
        source = 'door door. Walk left.'
        start = source.index('left')
        candidate = source.replace('left', 'right')
        self.assertEqual(mapped_quote(source, candidate, 'door', start, 'left', 'right'), ('door', False, 0))

    def test_undeclared_second_edit_is_rejected(self):
        source = 'Turn left. Stop.'
        with self.assertRaisesRegex(ValueError, 'single declared edit'):
            mapped_quote(source, 'Turn right. Go.', 'Turn left.', 5, 'left', 'right')

    def test_deleted_and_partial_spans_are_explicit(self):
        self.assertEqual(mapped_quote('A Turn left. B', 'A B', 'Turn left. ', 2, 'Turn left. ', ''), ('', True, 2))
        with self.assertRaises(ValueError):
            mapped_quote('left', 'right', '', 0, 'left', 'right')
        with self.assertRaises(ValueError):
            mapped_quote('left', 'right', 'left', 0, 'left', 'right', occurrence=1)


class TrainingBuilderBoundaryTests(unittest.TestCase):
    def test_duplicate_specs_are_rejected(self):
        lessons = copy.deepcopy(builder.LESSONS)
        lessons[1] = copy.deepcopy(lessons[0])
        with self.assertRaisesRegex(ValueError, 'Duplicate authored'):
            builder.validate_lesson_inventory(lessons)

    def test_full_expected_bundle_reproduces_committed_bytes(self):
        outputs, registry = builder.expected_bundle()
        for name, expected in outputs.items():
            self.assertEqual((builder.ROOT / name).read_bytes(), expected, name)
        self.assertEqual(json.loads((builder.ROOT / 'provenance/rxr_training_sources.json').read_bytes()), registry)

    def test_late_invalid_case_does_not_write_partial_bundle(self):
        lessons = copy.deepcopy(builder.LESSONS)
        # Keep every source identity intact but break the last lesson's exact quote.
        value = list(lessons[-1]['coverage'][0])
        value[2] = 'This quote does not exist in the candidate.'
        lessons[-1]['coverage'][0] = tuple(value)
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            with mock.patch.object(builder, 'ROOT', root), mock.patch.object(builder, 'LESSONS', lessons):
                with self.assertRaises(ValueError):
                    builder.build()
            self.assertEqual(list(root.rglob('*')), [])


if __name__ == '__main__':
    unittest.main()
