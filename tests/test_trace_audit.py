import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_model_trace import parse, inspect


def call(text, index=1):
    return {
        "kind": "model_call",
        "call_id": index,
        "raw_decoded_output": text,
        "normalized_output": text,
        "stop_str": "<|eot_id|>",
        "sep2": "<|end_of_text|>",
        "generation": {"do_sample": False, "temperature": 0.0, "max_new_tokens": 256},
    }


def step(action, index=1, call_id=1):
    return {"kind": "primitive_action", "step": index, "action": action, "last_call_id": call_id}


class TraceAudit(unittest.TestCase):
    def test_native_chunk_and_rounding(self):
        self.assertEqual(parse("<BEGIN_OF_ACTION> move forward 75 cm")[0], [1, 1, 1])
        self.assertEqual(parse("turn left 31 degree")[0], [2, 2])
        self.assertEqual(parse("unknown output"), ([1], False, True))

    def test_mismatched_real_action_rejected(self):
        events = [
            {"kind": "reset"},
            call("turn left 15 degree"),
            step(1),
            {"kind": "terminal", "steps": 1, "model_calls": 1},
        ]
        self.assertTrue(inspect(events)[0])

    def test_pending_queue_blocks_new_call(self):
        events = [
            {"kind": "reset"},
            call("move forward 75 cm"),
            step(1),
            call("stop", 2),
            step(0, 2, 2),
            {"kind": "terminal", "steps": 2, "model_calls": 2},
        ]
        self.assertIn("model called with pending primitive queue", inspect(events)[0])

    def test_reason_stuck_native_stop(self):
        events = (
            [{"kind": "reset"}]
            + [call("<BEGIN_OF_REASONING> think", i) for i in range(1, 5)]
            + [step(0, 1, 4), {"kind": "terminal", "steps": 1, "model_calls": 4}]
        )
        self.assertEqual(inspect(events), ([], 0))

    def test_empty_fake_episode_not_accepted(self):
        self.assertTrue(
            inspect([{"kind": "reset"}, {"kind": "terminal", "steps": 0, "model_calls": 0}])[0]
        )


if __name__ == "__main__":
    unittest.main()
