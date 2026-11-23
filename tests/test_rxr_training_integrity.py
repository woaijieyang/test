"""Data-boundary regressions over the actual committed RxR training bundle."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from host import rxr_assets
from tools import rxr_training_io as io

ROOT = Path(__file__).resolve().parents[1]


class TrainingIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for folder in io.FOLDERS:
            shutil.copytree(ROOT / folder, self.root / folder)
        (self.root / 'provenance').mkdir()
        shutil.copyfile(ROOT / io.REGISTRY, self.root / io.REGISTRY)
        self.registry = json.loads((self.root / io.REGISTRY).read_bytes())
        self.outputs = {row['path']: (self.root / row['path']).read_bytes() for row in self.registry['templates']}

    def save_registry(self):
        (self.root / io.REGISTRY).write_bytes(io.encode(self.registry))

    def asset(self, key):
        tid = self.registry['records'][0][key]
        role = 'generator' if key == 'generator' else 'reviewer'
        path = f'{role}/templates/RxR/train/{tid}.json'
        return path, json.loads(self.outputs[path])

    def repin(self, path, row):
        data = io.encode(row)
        (self.root / path).write_bytes(data)
        next(x for x in self.registry['templates'] if x['path'] == path)['sha256'] = io.sha(data)
        self.save_registry()

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def changed_bundle(self):
        outputs = dict(self.outputs)
        registry = copy.deepcopy(self.registry)
        for path in sorted(outputs)[:2]:
            row = json.loads(outputs[path])
            row['teaching_notes']['reviewed_authoring_check'] = 'Authored change for write-failure testing only.'
            outputs[path] = io.encode(row)
            next(x for x in registry['templates'] if x['path'] == path)['sha256'] = io.sha(outputs[path])
        return outputs, registry

    def test_committed_bundle_and_libraries_validate(self):
        self.assertEqual(rxr_assets.validate_training_assets(self.root), self.registry)
        for role in ('generator', 'reviewer'):
            rows = [json.loads(data) for path, data in self.outputs.items() if path.startswith(role + '/')]
            rxr_assets.validate_training_library(role, rows, self.root)

    def test_source_identity_cannot_be_repaired_by_repinning_only(self):
        path, row = self.asset('reviewer')
        row['source']['scene_id'] = 'wrong-scene'
        self.repin(path, row)
        with self.assertRaisesRegex(ValueError, 'source identity'):
            rxr_assets.validate_training_assets(self.root)

    def test_pair_identity_is_bound_to_registry(self):
        path, row = self.asset('reviewer')
        row['pair_id'] = self.registry['records'][1]['generator']
        self.repin(path, row)
        with self.assertRaisesRegex(ValueError, 'pair identity'):
            rxr_assets.validate_training_assets(self.root)

    def test_pair_candidate_cannot_silently_change(self):
        path, row = self.asset('reviewer')
        row['review_input']['candidate']['subtasks'][0] += ' Extra command.'
        self.repin(path, row)
        with self.assertRaisesRegex(ValueError, 'actual Generator candidate'):
            rxr_assets.validate_training_assets(self.root)

    def test_duplicate_numeric_instruction_identity_rejected(self):
        self.registry['records'][1]['instruction_id'] = str(self.registry['records'][0]['instruction_id'])
        self.save_registry()
        with self.assertRaisesRegex(ValueError, 'Duplicate RxR training instruction'):
            rxr_assets.validate_training_assets(self.root)

    def test_unregistered_asset_is_not_absorbed(self):
        (self.root / io.FOLDERS[0] / 'extra.json').write_text('{}')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            rxr_assets.validate_training_assets(self.root)
        with self.assertRaisesRegex(ValueError, 'unregistered training files'):
            io.publish(self.root, self.outputs, self.registry)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_role_and_duplicate_library_rows_rejected(self):
        rows = [json.loads(data) for path, data in self.outputs.items() if path.startswith('generator/')]
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            rxr_assets.validate_training_library('other', rows, self.root)
        with self.assertRaisesRegex(ValueError, 'explicit source registry'):
            rxr_assets.validate_training_library('generator', rows + rows[:1], self.root)

    def test_stale_in_memory_teaching_is_not_accepted(self):
        rows = [json.loads(data) for path, data in self.outputs.items() if path.startswith('generator/')]
        path, row = self.asset('generator')
        row['teaching_notes']['why_this_case_matters'] += ' Updated authored explanation.'
        self.repin(path, row)
        with self.assertRaisesRegex(ValueError, 'in-memory teaching'):
            rxr_assets.validate_training_library('generator', rows, self.root)

    def test_archive_identity_is_checked_even_after_hash_repin(self):
        path, row = self.asset('generator')
        row['provenance']['archive_sha256'] = '0' * 64
        self.repin(path, row)
        with self.assertRaisesRegex(ValueError, 'source identity'):
            rxr_assets.validate_training_assets(self.root)

    def test_symbolic_link_rejected(self):
        path = next(iter(self.outputs))
        original = self.root / path
        other = self.root / 'copied-asset.json'
        other.write_bytes(original.read_bytes())
        original.unlink()
        original.symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'symbolic'):
            rxr_assets.validate_training_assets(self.root)
        with self.assertRaisesRegex(ValueError, 'symbolic'):
            io.publish(self.root, self.outputs, self.registry)

    def test_noop_and_check_do_not_change_bytes(self):
        before = self.snapshot()
        self.assertEqual(io.publish(self.root, self.outputs, self.registry, check=True), [])
        self.assertEqual(io.publish(self.root, self.outputs, self.registry), [])
        self.assertEqual(before, self.snapshot())

    def test_unreviewed_edit_is_not_overwritten(self):
        path = sorted(self.outputs)[-1]
        (self.root / path).write_bytes(b'{}\n')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'independently changed'):
            io.publish(self.root, self.outputs, self.registry)
        self.assertEqual(before, self.snapshot())

    def test_invalid_registry_digest_fails_before_any_write(self):
        outputs, registry = self.changed_bundle()
        registry['templates'][0]['sha256'] = '0' * 64
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'Registry/output bytes'):
            io.publish(self.root, outputs, registry)
        self.assertEqual(before, self.snapshot())

    def test_write_failure_rolls_back_own_changes(self):
        outputs, registry = self.changed_bundle()
        before = self.snapshot()
        replace = io._replace
        calls = []
        def fail_once(source, target):
            calls.append(str(target))
            if len(calls) == 2:
                raise OSError('simulated disk failure')
            return replace(source, target)
        with mock.patch.object(io, '_replace', side_effect=fail_once):
            with self.assertRaisesRegex(OSError, 'simulated disk failure'):
                io.publish(self.root, outputs, registry)
        self.assertEqual(before, self.snapshot())

    def test_registry_is_published_last(self):
        outputs, registry = self.changed_bundle()
        calls = []
        replace = io._replace
        def record(source, target):
            calls.append(Path(target).relative_to(self.root).as_posix())
            return replace(source, target)
        with mock.patch.object(io, '_replace', side_effect=record):
            changed = io.publish(self.root, outputs, registry)
        self.assertEqual(calls, changed)
        self.assertEqual(calls[-1], io.REGISTRY)
        self.assertEqual(io.publish(self.root, outputs, registry, check=True), [])

    def test_empty_checkout_can_materialize_known_bundle(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            io.publish(root, self.outputs, self.registry)
            rxr_assets.validate_training_assets(root)


if __name__ == '__main__':
    unittest.main()
