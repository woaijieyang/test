"""Offline dispatch tests; provider responses are fixtures, not navigation results."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dispatch as app
from transport import ResponsesBackend

class DispatcherTests(unittest.TestCase):
    def test_isolation_repair_limit_and_resume(self):
        records = {"one": "Walk ahead.", "two": "Turn left."}
        calls = []
        def respond(req):
            prefix, payload = req["input"].rsplit("\nACTUAL INPUT (process only this record)\n", 1)
            data = json.loads(payload)
            self.assertNotIn("previous_response_id", req)
            self.assertFalse(req["store"])
            source = data["original_instruction"]
            self.assertNotIn(next(s for s in records.values() if s != source), payload)
            role = "generator" if prefix.startswith("Independent generator") else "reviewer"
            if role == "generator":
                if "review" in data:
                    self.assertEqual(data["review"]["findings"][0]["source_quote"], source)
                value = dict(status="ok", subtasks=[source], issues=[])
            else:
                passed = source == "Turn left."
                finding = dict(code="OTHER", source_quote=source, problem="Fixture finding", subtask_indices=[0])
                checks = [dict(subtask_index=0, entry_context="Start", required_history=[],
                               completion_condition=source, carryover_requirements=[], source_quotes=[source])]
                value = dict(verdict="pass" if passed else "revise", findings=[] if passed else [finding], stage_checks=checks)
            calls.append((source, role))
            return dict(status="completed", id="test-id", model="test-model",
                        output=[dict(type="message",content=[dict(type="output_text",text=json.dumps(value))])])
        config = app.load(app.PACKAGE / "config/workflow.json")
        self.assertEqual([config[k] for k in ("generator_workers","reviewer_workers","max_review_rounds")],[4,4,3])
        for name in ("codex_cli", "responses"):
            self.assertEqual((config[name]["model"], config[name]["effort"]), ("gpt-6.1-sol","high"))
        provider = ResponsesBackend(endpoint="https://example.invalid/v1/responses", api_key_env="VLN_FAKE_TEST",
                                    model="test-model", effort="medium", send=respond)
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {"VLN_FAKE_TEST":"fake-for-test"}):
            root = Path(folder)
            for _ in range(2):
                self.assertFalse(app.dispatch(records,root,config,"responses",provider))
                self.assertEqual(len(calls),8)
            first = app.load(root/app.sha("one")/"await_primary.json")
            self.assertFalse(first["primary_accepted"])
            self.assertEqual(first["attempt"],2)
            self.assertEqual(first["proposed_units"],[records["one"]])
            self.assertEqual(app.load(root/app.sha("two")/"await_primary.json")["attempt"],0)
if __name__ == "__main__":
    unittest.main()

