"""CPU regression for the native D smoke fixture's source and approval fences."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'verify_d_episode.py'
spec = importlib.util.spec_from_file_location('verify_d_episode', SCRIPT)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)

class PrimaryGate(unittest.TestCase):
    def test_mismatched_candidate_cannot_create_navigation(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            key = "r2r|test"
            language = run / "language" / smoke.sha(key.encode())
            language.mkdir(parents=True)
            smoke.save(language/"await_primary.json", dict(record_id=key, attempt=0,
                reviewer_verdict="pass", hashes={"generator":"candidate-A"}))
            smoke.save(run/"primary.json", dict(record_id=key, attempt=0, owner="primary",
                verdict="pass", hashes={"generator":"candidate-B"}))
            from unittest.mock import patch
            with patch.object(smoke,"original",return_value={"task_key":key}), self.assertRaises(AssertionError):
                smoke.prepare(run)
            self.assertFalse((run/"navigation").exists())

if __name__ == "__main__":
    unittest.main()
