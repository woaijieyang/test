"""Trace transactions with synthetic tensors; not an image/model integration test."""

import json, sys, tempfile, types, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from case1_runtime.trace import TraceRecorder


class TensorFixture:
    shape = (1, 3, 1, 1)

    def detach(self):
        return self

    def cpu(self):
        return self

    def contiguous(self):
        return self

    def numpy(self):
        return self

    def tobytes(self):
        return b"\x00" * 6

    def tolist(self):
        return [[1, 2]]


class TracePersistence(unittest.TestCase):
    def setUp(self):
        (ROOT / ".cache").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".cache")
        self.rec = TraceRecorder(self.temp.name, "r2r")
        self.ep = types.SimpleNamespace(
            scene_id="mp3d/fixture/fixture.glb",
            episode_id="1",
            instruction=types.SimpleNamespace(instruction_id=None),
        )
        self.state = {"position": [0, 0, 0], "elapsed_steps": 0}
        self.rec.ensure_episode(self.ep, self.state)

    def tearDown(self):
        if self.rec.handle:
            self.rec.handle.close()
        self.temp.cleanup()

    def start(self):
        return self.rec.begin_model_call(
            self.ep, 0, "synthetic prompt", [], TensorFixture(), TensorFixture(), "<end>", "<end2>"
        )

    def events(self):
        return [
            json.loads(x) for x in (self.rec.directory / "trace.jsonl").read_text().splitlines()
        ]

    def test_input_survives_generation_failure(self):
        self.start()
        events = self.events()
        self.assertEqual([e["kind"] for e in events], ["reset", "model_input"])
        self.assertFalse((Path(self.temp.name) / "results.jsonl").exists())
        with self.assertRaises(RuntimeError):
            self.rec.close()

    def test_result_must_match_input_transaction(self):
        call = self.start()
        with self.assertRaises(RuntimeError):
            self.rec.finish_model_call(call + 1, TensorFixture(), "stop", "stop")
        self.rec.finish_model_call(call, TensorFixture(), "stop", "stop")
        events = self.events()
        self.assertEqual(events[-1]["kind"], "model_call")
        self.assertEqual(events[-1]["processed_image_sha256"], events[-2]["processed_image_sha256"])


if __name__ == "__main__":
    unittest.main()
