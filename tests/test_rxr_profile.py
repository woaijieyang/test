import unittest
from pathlib import Path

from host.compile import ROOT, compile_prompt, core_library
from host.run import request, dataset_rules_metadata, template_bundle_metadata
from host.template_selector import library, select_examples, source, validate_dynamic_identity


class RxRProfileTests(unittest.TestCase):
    def test_dynamic_identity_gate_is_symmetric_and_fail_closed(self):
        valid_r2r = {"role": "generator", "dataset_scope": "R2R", "language": "en",
                     "template_id": "R2R-GEN-001"}
        valid_rxr = {"role": "generator", "dataset_scope": "RxR", "language": "en-US",
                     "template_id": "RxR-GEN-001"}
        validate_dynamic_identity("generator", "r2r-en", valid_r2r)
        validate_dynamic_identity("generator", "rxr-en-us", valid_rxr)
        invalid_rows = [
            ("rxr-en-us", {**valid_r2r}),
            ("r2r-en", {**valid_rxr}),
            ("rxr-en-us", {**valid_rxr, "template_id": "R2R-GEN-001"}),
            ("rxr-en-us", {**valid_rxr, "language": "en"}),
            ("rxr-en-us", {**valid_rxr, "role": "reviewer"}),
        ]
        for profile, row in invalid_rows:
            with self.subTest(profile=profile, row=row):
                with self.assertRaises(ValueError):
                    validate_dynamic_identity("generator", profile, row)

    def test_fixed_core_is_exactly_ten_and_paired(self):
        gen = core_library("generator", "rxr-en-us")
        rev = core_library("reviewer", "rxr-en-us")
        self.assertEqual(len(gen), 10)
        self.assertEqual(len(rev), 10)
        self.assertEqual([x["template_id"] for x in gen],
                         [f"RXR-CORE-G{i:02d}" for i in range(1, 11)])
        self.assertEqual([x["template_id"] for x in rev],
                         [f"RXR-CORE-R{i:02d}" for i in range(1, 11)])
        self.assertEqual([x["pair_id"] for x in rev],
                         [x["template_id"] for x in gen])
        self.assertEqual([x["template_id"] for x in gen],
                         [f"RXR-CORE-G{i:02d}" for i in range(1, 11)])
        self.assertEqual([x["pair_id"] for x in rev],
                         [x["template_id"] for x in gen])
        self.assertEqual([x["template_id"] for x in core_library("generator", "r2r-en")],
                         [f"R2R-CORE-G{i:02d}" for i in range(1, 11)])
        self.assertEqual([x["template_id"] for x in core_library("reviewer", "r2r-en")],
                         [f"R2R-CORE-R{i:02d}" for i in range(1, 11)])

    def test_legacy_sources_are_not_in_dynamic_retrieval(self):
        for role in ("generator", "reviewer"):
            ids = [x["template_id"] for x in library(role, "rxr-en-us")]
            self.assertTrue(ids)
            self.assertTrue(all("LEGACY" not in x for x in ids))
            self.assertFalse(any(x["template_id"].startswith("RxR-LEGACY")
                                 for x in library(role, "rxr-en-us")))

    def test_rxr_dynamic_selection_ranges_and_pair_alignment(self):
        for source_text in (
            "Walk to the second doorway on the left.",
            "Exit the bedroom, cross the hall, enter the kitchen, then return through the same door.",
            "After you pass the stairs, keep the wall on your right until you reach the third door, then enter the room and stop beside the desk.",
        ):
            g = select_examples("generator", "rxr-en-us", source_text)
            r = select_examples("reviewer", "rxr-en-us", source_text)
            self.assertTrue(2 <= len(g) <= 4)
            self.assertTrue(len(g) <= len(r) <= len(g) + 2)
            reviewer_by_id = {x["template_id"]: x for x in library("reviewer", "rxr-en-us")}
            self.assertEqual([reviewer_by_id[x]["pair_id"] for x in r[:len(g)]], g)
            self.assertTrue(all(reviewer_by_id[x].get("pair_id") is None
                                for x in r[len(g):]))
            self.assertNotIn(source_text, [source(x) for x in library("generator", "rxr-en-us")
                                          if x["template_id"] in g])

    def test_rxr_explicit_dynamic_count_is_bounded(self):
        with self.assertRaises(ValueError):
            select_examples("generator", "rxr-en-us", "Walk.", count=1)
        with self.assertRaises(ValueError):
            select_examples("generator", "rxr-en-us", "Walk.", count=5)
        self.assertEqual(len(select_examples("generator", "rxr-en-us", "Walk.", count=2)), 2)
        self.assertEqual(len(select_examples("generator", "rxr-en-us", "Walk.", count=4)), 4)

    def test_fixed_core_load_failure_returns_exact_source_without_model_call(self):
        from unittest.mock import patch
        from adapter.source import Source
        from host.run import run_record
        source_text = "Walk to the second doorway and stop."
        src = Source("rxr-smoke", "RxR", "en-US", source_text)
        calls = []
        def transport(req):
            calls.append(req)
            raise AssertionError("Transport must not be entered when core loading fails")
        with patch("host.run.core_library", side_effect=ValueError("synthetic core corruption")):
            result = run_record(src, transport,
                                pins={role: {"model": "fixture", "effort": "low"}
                                      for role in ("generator", "reviewer")})
        self.assertEqual(result["disposition"], "fallback_technical")
        self.assertEqual(result["instruction"], source_text)
        self.assertEqual(result["fixed_core_template_ids"]["generator"], [])
        self.assertEqual(result["fixed_core_template_ids"]["reviewer"], [])
        self.assertEqual(calls, [])

    def test_run_record_reports_all_mode_pairs_and_diagnostics(self):
        from adapter.source import Source
        from host.run import run_record
        from test_runtime_contract_v2 import SOURCE, generator_candidate, reviewer_output
        candidate = generator_candidate(True)
        review = reviewer_output(candidate, repaired=True)
        def transport(req):
            output = candidate if req["role"] == "generator" else review
            return {"output": output,
                    "receipt": {"model": req["model"], "effort": req["effort"],
                                "request_id": req["phase"] + "-fixture"}}
        result = run_record(
            Source("rxr-all-mode", "RxR", "en-US", SOURCE),
            transport,
            pins={role: {"model": "fixture", "effort": "low"}
                  for role in ("generator", "reviewer")},
            selection_mode="all",
        )
        self.assertEqual(result["disposition"], "accepted_candidate", result["error"])
        self.assertEqual(len(result["fixed_core_template_ids"]["generator"]), 10)
        self.assertEqual(len(result["fixed_core_template_ids"]["reviewer"]), 10)
        selection = result["example_selection"]
        self.assertEqual(selection["actual_generator_examples"], 35)
        self.assertEqual(selection["actual_reviewer_examples"], 64)
        self.assertEqual(selection["reviewer_pair_count"], 35)
        self.assertEqual(len(selection["reviewer_diagnostic_ids"]), 29)

    def test_r2r_dynamic_retrieval_uses_its_declared_policy(self):
        g = select_examples("generator", "r2r-en", "Walk to the door and turn left.")
        r = select_examples("reviewer", "r2r-en", "Walk to the door and turn left.")
        self.assertTrue(4 <= len(g) <= 6)
        self.assertTrue(6 <= len(r) <= 9)
        self.assertEqual(len(core_library("generator", "r2r-en")), 10)

    def test_rxr_generator_compiler_injects_core_then_dynamic(self):
        source_text = "Leave the bedroom, turn left, cross the hallway, and enter the kitchen."
        ids = select_examples("generator", "rxr-en-us", source_text)
        prompt, _ = compile_prompt("generator", "initial", profile="rxr-en-us",
                                   selected_ids=ids, original_instruction=source_text)
        self.assertIn("shared/dataset_rules/rxr_en_us.md", prompt)
        self.assertIn("generator/dataset_rules/rxr_en_us.md", prompt)
        self.assertIn("FIXED RXR GENERATOR CORE: exactly 10", prompt)
        self.assertIn("DYNAMIC RXR-EN-US GENERATOR EXAMPLES", prompt)
        self.assertLess(prompt.index("FIXED RXR GENERATOR CORE"),
                        prompt.index("DYNAMIC RXR-EN-US GENERATOR EXAMPLES"))
        for row in core_library("generator", "rxr-en-us"):
            self.assertIn(row["template_id"], prompt)
        for template_id in ids:
            self.assertIn(template_id, prompt)

    def test_rxr_reviewer_compiler_injects_independent_core_pairs_and_diagnostics(self):
        source_text = "After leaving the bedroom, turn right and enter the second door."
        ids = select_examples("generator", "rxr-en-us", source_text)
        reviewer_ids = select_examples("reviewer", "rxr-en-us", source_text)
        prompt, _ = compile_prompt("reviewer", "review", profile="rxr-en-us",
                                   selected_ids=reviewer_ids, original_instruction=source_text)
        self.assertIn("reviewer/dataset_rules/rxr_en_us.md", prompt)
        self.assertIn("FIXED RXR REVIEWER CORE: exactly 10", prompt)
        self.assertIn("DYNAMIC RXR-EN-US REVIEWER EXAMPLES", prompt)
        reviewer_by_id = {x["template_id"]: x for x in library("reviewer", "rxr-en-us")}
        self.assertEqual([reviewer_by_id[x]["pair_id"] for x in reviewer_ids[:len(ids)]], ids)
        diagnostics = reviewer_ids[len(ids):]
        self.assertLessEqual(len(diagnostics), 2)
        self.assertTrue(all(reviewer_by_id[x].get("pair_id") is None for x in diagnostics))
        for row in core_library("reviewer", "rxr-en-us"):
            self.assertIn(row["template_id"], prompt)
        for template_id in reviewer_ids:
            self.assertIn(template_id, prompt)

    def test_r2r_compilation_does_not_load_rxr_rules_or_core(self):
        source_text = "Walk through the doorway and stop beside the table."
        ids = select_examples("generator", "r2r-en", source_text)
        prompt, _ = compile_prompt("generator", "initial", profile="r2r-en",
                                   selected_ids=ids, original_instruction=source_text)
        self.assertNotIn("RXR SHARED SEMANTIC RULES", prompt)
        self.assertNotIn("FIXED RXR", prompt)
        self.assertNotIn("dataset_rules/rxr_en_us.md", prompt)

    def test_rule_and_template_hashes_are_recordable_and_profile_scoped(self):
        r2r = dataset_rules_metadata("r2r-en")
        rxr = dataset_rules_metadata("rxr-en-us")
        self.assertEqual(r2r["version"], "r2r-en-profile")
        self.assertEqual(r2r["files"], [
            "shared/semantic_contract.md",
            "shared/dataset_rules/r2r_en.md",
            "shared/dataset_rules/r2r_fragments.json",
            "generator/dataset_rules/r2r_en.md",
            "reviewer/dataset_rules/r2r_en.md",
        ])
        self.assertEqual(rxr["version"], "rxr-en-us-profile")
        self.assertEqual(len(rxr["files"]), 4)
        ids = select_examples("generator", "rxr-en-us", "Go to the kitchen.")
        bundle = template_bundle_metadata("generator", "rxr-en-us", ids)
        self.assertEqual(len(bundle["fixed_core_ids"]), 10)
        self.assertEqual(bundle["dynamic_ids"], ids)
        self.assertEqual(len(bundle["sha256"]), 64)

    def test_rule_metadata_uses_real_section_separators(self):
        metadata = dataset_rules_metadata("rxr-en-us")
        self.assertEqual(metadata["version"], "rxr-en-us-profile")
        self.assertEqual(len(metadata["files"]), 4)
        self.assertEqual(len(metadata["sha256"]), 64)
        from pathlib import Path
        root = ROOT
        expected = "\n".join(
            f"## {Path(path).as_posix()}\n{(root/path).read_text(encoding='utf-8')}"
            for path in metadata["files"]
        )
        from shared.identity import text_hash
        self.assertEqual(metadata["sha256"], text_hash(expected))
        self.assertNotIn("\\n", expected)

    def test_request_records_fixed_core_and_dynamic_bundle(self):
        source_text = "Walk into the kitchen and stop at the counter."
        ids = select_examples("generator", "rxr-en-us", source_text)
        req = request("generator", "initial", {"original_instruction": source_text},
                      {"model": "fixture", "effort": "low"}, "rxr-en-us", ids)
        self.assertEqual(len(req["fixed_core_template_ids"]), 10)
        self.assertEqual(req["selected_example_ids"], ids)
        self.assertEqual(req["template_bundle"]["dynamic_ids"], ids)
        self.assertEqual(req["dataset_rules"]["version"], "rxr-en-us-profile")


if __name__ == "__main__":
    unittest.main()
