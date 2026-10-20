import os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from workspace import owned
from setup_data_links import ensure_link


class Boundaries(unittest.TestCase):
    def setUp(self):
        (ROOT / ".cache").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".cache")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_escape_and_archive_rejected(self):
        for p in ("../outside", "backup/history.txt", "upstream/file", "models/weight"):
            with self.assertRaises(ValueError):
                owned(p, self.root)
        target = self.root / "allowed"
        self.assertEqual(owned(target, self.root), target)

    @unittest.skipIf(os.name == "nt", "Server Linux symlink contract")
    def test_link_idempotence_and_collision(self):
        source = self.root / "source"
        source.mkdir()
        link = self.root / "link"
        ensure_link(link, str(source))
        ensure_link(link, str(source))
        with self.assertRaises(ValueError):
            ensure_link(link, str(self.root / "different"))
        entity = self.root / "entity"
        entity.write_text("preserve")
        with self.assertRaises(ValueError):
            ensure_link(entity, str(source))
        self.assertEqual(entity.read_text(), "preserve")
        with self.assertRaises(ValueError):
            owned(link / "output.txt", self.root)
        escaped = self.root / "parent-link"
        escaped.symlink_to(source, target_is_directory=True)
        with self.assertRaises(ValueError):
            ensure_link(escaped / "new-link", str(source))
        self.assertFalse((source / "new-link").exists())

    @unittest.skipIf(os.name == "nt", "Linux kernel protection")
    def test_kernel_write_denial_and_child_inheritance(self):
        allowed = self.root / "allowed"
        allowed.mkdir()
        blocked = self.root / "blocked"
        blocked.mkdir()
        (allowed / "escape").symlink_to(blocked, target_is_directory=True)
        program = """import sys,os,subprocess
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from landlock import restrict
allowed=Path(sys.argv[2]);blocked=Path(sys.argv[3]);abi=restrict([allowed])
(allowed/'ok').write_text('ok')
for p in (blocked/'deny',allowed/'escape'/'deny'):
 try:p.write_text('bad')
 except PermissionError:pass
 else:raise AssertionError('Unprotected write')
child=subprocess.run([sys.executable,'-c','from pathlib import Path;import sys;Path(sys.argv[1]).write_text("bad")',str(blocked/'child')],capture_output=True)
assert child.returncode!=0
print(abi)
"""
        r = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                program,
                str(ROOT / "scripts"),
                str(allowed),
                str(blocked),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((allowed / "ok").read_text(), "ok")
        self.assertEqual(list(blocked.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
