"""Closed trace/atomic commit recovery using clearly synthetic CPU-only episodes."""

import json, shutil, sys, tempfile, types, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from case1_runtime.trace import TraceRecorder
from evaluate import merge, recover_closed_traces
from workspace import digest
from test_trace_persistence import TensorFixture


class Commits(unittest.TestCase):
    def setUp(self):
        (ROOT / ".cache").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".cache")
        self.run = Path(self.temp.name)
        self.env = patch.dict("os.environ", {"CASE1_RUN_ROOT": str(self.run)})
        self.env.start()
        self.worker = self.run / "shards/shard-00/attempt-01"
        self.rec = TraceRecorder(self.worker, "r2r")
        (self.worker / "effective-config.yaml").write_text(
            "synthetic CPU fixture, not a benchmark configuration\n"
        )
        ep = types.SimpleNamespace(
            scene_id="mp3d/fixture/fixture.glb",
            episode_id="fixture-1",
            instruction=types.SimpleNamespace(instruction_id=None),
        )
        before = {"position": [0, 0, 0], "elapsed_steps": 0}
        after = {"position": [0, 0, 0], "elapsed_steps": 1}
        self.rec.ensure_episode(ep, before)
        call = self.rec.begin_model_call(
            ep, 0, "synthetic fixture", [], TensorFixture(), TensorFixture(), "<end>", "<end2>"
        )
        self.rec.finish_model_call(call, TensorFixture(), "stop", "stop")
        self.rec.step(
            ep,
            0,
            before,
            after,
            True,
            {
                "success": False,
                "spl": 0.0,
                "ndtw": 0.2,
                "distance_to_goal": 4.0,
                "oracle_success": False,
            },
        )

    def tearDown(self):
        if self.rec.handle:
            self.rec.handle.close()
        self.env.stop()
        self.temp.cleanup()

    def test_atomic_commit_binds_actual_trace_and_configuration(self):
        result = json.loads((self.rec.directory / "result.json").read_text())
        self.assertEqual(result["metrics"]["sr"], 0.0)
        self.assertIs(type(result["metrics"]["sr"]), float)
        self.assertFalse((self.rec.directory / "result.json.new").exists())
        merged = merge(self.run)
        self.assertEqual(len(merged), 1)
        self.assertEqual(digest(self.run / merged[0]["trace_path"]), merged[0]["trace_sha256"])
        self.assertEqual(
            digest(self.run / merged[0]["effective_config_path"]),
            merged[0]["effective_config_sha256"],
        )

    def test_closed_failure_is_recovered_without_model_retry(self):
        (self.rec.directory / "result.json").unlink()
        self.assertEqual(merge(self.run), [])
        recover_closed_traces(self.run)
        result = merge(self.run)[0]
        self.assertTrue(result["recovered_from_closed_trace"])
        self.assertEqual(result["metrics"]["sr"], 0.0)
        self.assertEqual(result["model_calls"], 1)

    def test_duplicate_completed_attempts_are_rejected(self):
        shutil.copytree(self.worker, self.worker.parent / "attempt-02")
        with self.assertRaises(ValueError):
            merge(self.run)


if __name__ == "__main__":
    unittest.main()
