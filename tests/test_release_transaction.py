"""Exercise installation and rollback ONLY in disposable case-local fixture trees."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from host.compile import ROOT

SCRIPT=ROOT.parents[2]/'docs/stages/v5-entry-diagnostics-20261114-r0/manage_release.py'
spec=importlib.util.spec_from_file_location('offline_release_fixture',SCRIPT)
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)


class ReleaseTransaction(unittest.TestCase):
    def fixture(self,root):
        doc=root/release.DOC;doc.mkdir(parents=True)
        old=root/'src/subtaskAdapter'/release.NAME;old.mkdir(parents=True)
        new=old.with_name(release.NAME+'-entry-diagnostics-candidate');new.mkdir()
        (old/'core.py').write_text('original\n',encoding='utf-8')
        (new/'core.py').write_text('candidate\n',encoding='utf-8')
        archive=doc/'original-v5-before.tar.gz';archive.write_bytes(b'offline archive checksum fixture')
        def entries(p):return [{'path':k,'sha256':v} for k,v in release.files(p).items()]
        baseline={'files':entries(old),'archive':archive.name,'archive_sha256':release.digest(archive),
                  'process_before':[],'protected_runtime_files':[]}
        (doc/'BASELINE_MANIFEST.json').write_text(json.dumps(baseline))
        (doc/'CANDIDATE_MANIFEST.json').write_text(json.dumps({'files':entries(new)}))
        (doc/'SERVER_CURRENT_CONTRACT.json').write_text(json.dumps({'tests':1,'failures':[],'errors':[]}))
        return doc,old,new

    def test_promote_and_exact_rollback(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parents[2],prefix='.v5-release-test-') as t:
            root=Path(t);doc,old,new=self.fixture(root);before=release.files(old)
            check=release.promote(root,check_only=True)
            self.assertEqual(check['status'],'CHECK_ONLY');self.assertEqual(release.files(old),before)
            self.assertEqual(release.promote(root)['status'],'PROMOTED')
            self.assertEqual(release.files(old),release.files(new))
            self.assertEqual(release.rollback(root,check_only=True)['status'],'ROLLBACK_CHECK_PASS')
            self.assertEqual(release.rollback(root)['status'],'ROLLED_BACK')
            self.assertEqual(release.files(old),before)
            self.assertTrue((doc/'rolled-back-candidate-directory').is_dir())

    def test_candidate_drift_refuses_without_replacing(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parents[2],prefix='.v5-release-test-') as t:
            root=Path(t);_,old,new=self.fixture(root);before=release.files(old)
            (new/'core.py').write_text('unapproved edit\n')
            with self.assertRaisesRegex(RuntimeError,'Candidate drifted'):release.promote(root)
            self.assertEqual(release.files(old),before)

    def test_rollback_does_not_discard_later_edits(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parents[2],prefix='.v5-release-test-') as t:
            root=Path(t);_,old,new=self.fixture(root);release.promote(root)
            (old/'core.py').write_text('later user edit\n')
            with self.assertRaisesRegex(RuntimeError,'later edits'):release.rollback(root)
            self.assertEqual((old/'core.py').read_text(),'later user edit\n')

    def test_backup_checksum_is_required(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parents[2],prefix='.v5-release-test-') as t:
            root=Path(t);doc,old,_=self.fixture(root);before=release.files(old)
            (doc/'original-v5-before.tar.gz').write_bytes(b'corrupt')
            with self.assertRaisesRegex(RuntimeError,'Backup archive'):release.promote(root)
            self.assertEqual(release.files(old),before)
