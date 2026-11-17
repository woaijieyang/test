import unittest

from adapter.source import from_record
from host.compile import compile_prompt, core_library
from host.run import request, run_record
from host.template_selector import select_examples, library
from test_runtime_contract_v2 import SOURCE, generator_candidate, reviewer_output


class HostDispatchProfileTests(unittest.TestCase):
    def setUp(self):
        self.pins = {
            role: {"model": "fixture", "effort": "low"}
            for role in ("generator", "reviewer")
        }

    def test_adapter_profile_controls_request_and_prompt_isolation(self):
        r2r = from_record({
            "dataset": "R2R", "split": "val_seen", "episode_id": "r2r-1",
            "instruction_text": "Walk through the doorway and stop."
        })
        rxr = from_record({
            "dataset": "RxR", "language": "en-US", "split": "val_seen",
            "instruction_id": "rxr-1", "instruction": SOURCE
        })

        for src, expected_profile in ((r2r, "r2r-en"), (rxr, "rxr-en-us")):
            ids = select_examples("generator", src.profile, src.raw)
            req = request("generator", "initial",
                          {"original_instruction": src.raw}, self.pins["generator"],
                          src.profile, ids)
            self.assertEqual(req["profile"], expected_profile)
            self.assertEqual(req["selected_example_ids"], ids)

        r2r_req = request("generator", "initial",
                          {"original_instruction": r2r.raw}, self.pins["generator"],
                          r2r.profile, select_examples("generator", r2r.profile, r2r.raw))
        r2r_system = r2r_req["messages"][0]["content"]
        self.assertNotIn("RXR SHARED SEMANTIC RULES", r2r_system)
        self.assertNotIn("RXR ROLE GUIDANCE", r2r_system)
        self.assertNotIn("FIXED RXR", r2r_system)
        self.assertEqual(r2r_req["fixed_core_template_ids"], [])

        rxr_ids = select_examples("generator", rxr.profile, rxr.raw)
        rxr_req = request("generator", "initial",
                          {"original_instruction": rxr.raw}, self.pins["generator"],
                          rxr.profile, rxr_ids)
        self.assertEqual(len(rxr_req["fixed_core_template_ids"]), 10)
        self.assertTrue(2 <= len(rxr_req["selected_example_ids"]) <= 4)
        self.assertIn("RXR SHARED SEMANTIC RULES", rxr_req["messages"][0]["content"])
        self.assertIn("FIXED RXR GENERATOR CORE", rxr_req["messages"][0]["content"])

    def test_host_dispatches_adapter_profile_to_both_roles(self):
        src = from_record({
            "dataset": "RxR", "language": "en-US", "split": "val_seen",
            "instruction_id": "dispatch-1", "instruction": SOURCE
        })
        candidate = generator_candidate(repaired=True)
        review = reviewer_output(candidate, repaired=True)
        requests = []

        def transport(req):
            requests.append(req)
            output = candidate if req["role"] == "generator" else review
            return {
                "output": output,
                "receipt": {
                    "model": req["model"], "effort": req["effort"],
                    "request_id": req["phase"] + "-dispatch-fixture"
                }
            }

        result = run_record(src, transport, pins=self.pins)
        self.assertEqual(result["disposition"], "accepted_candidate", result["error"])
        self.assertEqual([(r["role"], r["phase"]) for r in requests],
                         [("generator", "initial"), ("reviewer", "review")])
        self.assertTrue(all(r["profile"] == "rxr-en-us" for r in requests))
        for role in ("generator", "reviewer"):
            role_requests = [r for r in requests if r["role"] == role]
            self.assertEqual(len(role_requests), 1)
            self.assertEqual(len(role_requests[0]["fixed_core_template_ids"]), 10)
            self.assertTrue(2 <= len(role_requests[0]["selected_example_ids"]) <=
                            (4 if role == "generator" else 6))
            self.assertEqual(role_requests[0]["prompt_components"],
                             result["prompt_components"][role][
                                 "initial" if role == "generator" else "review"])
            self.assertEqual(role_requests[0]["template_bundle"]["sha256"],
                             result["template_bundles"][role]["sha256"])

    def test_rxr_g0_r0_g1_r1_reuses_frozen_profile_rules_and_templates(self):
        from test_runtime_contract_v2 import reviewer_output
        src = from_record({
            "dataset": "RxR", "language": "en-US", "split": "val_seen",
            "instruction_id": "dispatch-four-phase", "instruction": SOURCE
        })
        old = generator_candidate(repaired=False)
        new = generator_candidate(repaired=True)
        r0 = reviewer_output(old, repaired=False)
        r1 = reviewer_output(new, repaired=True, r1=True)
        repair = {
            "candidate": new,
            "responses": [{
                "finding_index": 0,
                "decision": "accept",
                "source_quotes": ["go down the hall"],
                "reason": "The source explicitly requires the omitted hallway traversal."
            }]
        }
        replies = [old, r0, repair, r1]
        requests = []

        def transport(req):
            requests.append(req)
            return {
                "output": replies.pop(0),
                "receipt": {
                    "model": req["model"], "effort": req["effort"],
                    "request_id": f"rxr-four-phase-{len(requests)}"
                }
            }

        result = run_record(src, transport, pins=self.pins)
        self.assertEqual(result["disposition"], "accepted_candidate", result["error"])
        self.assertEqual([(x["role"], x["phase"]) for x in requests], [
            ("generator", "initial"), ("reviewer", "review"),
            ("generator", "repair"), ("reviewer", "recheck")
        ])
        for req in requests:
            self.assertEqual(req["profile"], "rxr-en-us")
            self.assertEqual(len(req["fixed_core_template_ids"]), 10)
        for role, phase in (("generator", "initial"), ("reviewer", "review"),
                            ("generator", "repair"), ("reviewer", "recheck")):
            req = next(x for x in requests if x["role"] == role and x["phase"] == phase)
            self.assertEqual(req["prompt_components"],
                             result["prompt_components"][role][phase])
            self.assertEqual(req["template_bundle"]["sha256"],
                             result["template_bundles"][role]["sha256"])
        self.assertEqual(requests[0]["selected_example_ids"], requests[2]["selected_example_ids"])
        self.assertEqual(requests[1]["selected_example_ids"], requests[3]["selected_example_ids"])
        self.assertEqual(requests[0]["fixed_core_template_ids"],
                         requests[2]["fixed_core_template_ids"])
        self.assertEqual(requests[1]["fixed_core_template_ids"],
                         requests[3]["fixed_core_template_ids"])

    def test_r2r_v5_compatibility_assets_are_byte_identical(self):
        import hashlib
        import json
        from pathlib import Path
        from host.compile import ROOT

        manifest = json.loads(
            (ROOT / "provenance/r2r_v5_compatibility.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["baseline_commit"],
                         "c2243fdd3f8c3ae08f1ad6837e14b17a17e228f3")
        self.assertEqual(manifest["file_count"], len(manifest["files"]))
        for entry in manifest["files"]:
            path = ROOT / entry["path"]
            data = path.read_bytes()
            blob = hashlib.sha1(
                b"blob " + str(len(data)).encode("ascii") + b"\\0" + data
            ).hexdigest()
            with self.subTest(path=entry["path"]):
                self.assertEqual(blob, entry["git_blob_sha1"])

    def test_r2r_prompt_restores_v5_build_and_curated_header(self):
        source_text = "Walk through the doorway and stop beside the table."
        ids = select_examples("generator", "r2r-en", source_text)
        prompt, _ = compile_prompt(
            "generator", "initial", profile="r2r-en",
            selected_ids=ids, original_instruction=source_text
        )
        self.assertTrue(prompt.startswith(
            "BUILD: v1.5.2 / runtime-contract-v2. Selected few-shot examples are "
            "source-feature-matched and frozen per record; the source instruction "
            "remains the only route authority.\\n\\n"
        ))
        self.assertIn("CURATED R2R-EN GENERATOR EXAMPLES:", prompt)
        self.assertNotIn("FIXED RXR", prompt)
        self.assertNotIn("RXR SHARED SEMANTIC RULES", prompt)
        self.assertNotIn("RXR ROLE GUIDANCE", prompt)

    def test_r2r_never_receives_rxr_core_or_rules(self):
        src = from_record({
            "dataset": "R2R", "split": "val_seen", "episode_id": "dispatch-r2r",
            "instruction_text": SOURCE
        })
        candidate = generator_candidate(repaired=True)
        review = reviewer_output(candidate, repaired=True)
        requests = []

        def transport(req):
            requests.append(req)
            output = candidate if req["role"] == "generator" else review
            return {"output": output, "receipt": {
                "model": req["model"], "effort": req["effort"],
                "request_id": req["phase"] + "-r2r-fixture"
            }}

        result = run_record(src, transport, pins=self.pins)
        self.assertEqual(result["disposition"], "accepted_candidate", result["error"])
        self.assertEqual(len(requests), 2)
        for req in requests:
            self.assertEqual(req["profile"], "r2r-en")
            self.assertEqual(req["fixed_core_template_ids"], [])
            self.assertEqual(req["dataset_rules"]["version"], "v5-common")
            system = req["messages"][0]["content"]
            self.assertNotIn("RXR SHARED SEMANTIC RULES", system)
            self.assertNotIn("RXR ROLE GUIDANCE", system)
            self.assertNotIn("FIXED RXR", system)
            self.assertNotIn("rxr_en_us", system)


if __name__ == "__main__":
    unittest.main()
