import hashlib
import json
import unittest
from pathlib import Path

from adapter.source import Source
from host.compile import ROOT, compile_prompt, core_library, runtime_review_output
from host.run import request, dataset_rules_metadata, template_bundle_metadata
from host.template_selector import library, select_examples
from host import protocol


class R2RV62CoreTests(unittest.TestCase):
    def test_fixed_core_identity_order_and_note_contract(self):
        gen = core_library("generator", "r2r-en")
        rev = core_library("reviewer", "r2r-en")
        self.assertEqual([x["template_id"] for x in gen],
                         [f"R2R-CORE-G{i:02d}" for i in range(1, 11)])
        self.assertEqual([x["template_id"] for x in rev],
                         [f"R2R-CORE-R{i:02d}" for i in range(1, 11)])
        self.assertEqual(len(gen), 10)
        self.assertEqual(len(rev), 10)
        self.assertEqual(len({x["template_id"] for x in gen}), 10)
        self.assertEqual(len({x["template_id"] for x in rev}), 10)
        for row in [*gen, *rev]:
            self.assertEqual(row["dataset_scope"], "R2R")
            self.assertEqual(row["language"], "en")
            self.assertEqual(row["role"], "generator" if row in gen else "reviewer")
            for field in ("semantic_pattern", "decision_reason", "transfer_rule", "anti_pattern"):
                self.assertTrue(row["teaching_notes"].get(field), (row["template_id"], field))

    def test_reviewer_core_pair_ids_are_provenance_not_order_dependency(self):
        gen_ids = {x["template_id"] for x in core_library("generator", "r2r-en")}
        rev = core_library("reviewer", "r2r-en")
        pairs = [x["pair_id"] for x in rev]
        self.assertEqual(len(set(pairs)), 10)
        self.assertEqual(set(pairs), gen_ids)
        self.assertNotEqual(pairs, [x["template_id"] for x in core_library("generator", "r2r-en")])

    def test_core_is_excluded_from_dynamic_libraries_and_selection(self):
        for role, expected in (("generator", 35), ("reviewer", 61)):
            rows = library(role, "r2r-en")
            self.assertEqual(len(rows), expected)
            self.assertFalse(any(x["template_id"].startswith("R2R-CORE-") for x in rows))
            ids = select_examples(role, "r2r-en", "Walk through the doorway and stop beside the table.")
            self.assertFalse(any(x.startswith("R2R-CORE-") for x in ids))
            self.assertTrue(all(x in {r["template_id"] for r in rows} for x in ids))
        self.assertTrue(6 <= len(select_examples("generator", "r2r-en", "Walk through the doorway.")) <= 8)
        self.assertTrue(8 <= len(select_examples("reviewer", "r2r-en", "Walk through the doorway.")) <= 12)

    def test_generator_core_passes_existing_runtime_contract(self):
        for row in core_library("generator", "r2r-en"):
            with self.subTest(template=row["template_id"]):
                protocol.generator(row["input"]["original_instruction"], row["output"])
                self.assertEqual(len(row["output"]["stage_audit"]), len(row["output"]["subtasks"]))
                self.assertEqual(len(row["output"]["handoffs"]), max(0, len(row["output"]["subtasks"]) - 1))

    def test_reviewer_core_passes_existing_runtime_contract_and_verdict_balance(self):
        verdicts = []
        for row in core_library("reviewer", "r2r-en"):
            audit = runtime_review_output(row)
            candidate = row["review_input"]["candidate"]
            with self.subTest(template=row["template_id"]):
                protocol.reviewer(row["review_input"]["original_instruction"], candidate, audit)
                self.assertEqual(len(audit["layer_checks"]), 7)
                self.assertEqual([x["layer"] for x in audit["layer_checks"]], list(protocol.LAYERS))
                self.assertEqual(len(audit["stage_checks"]), len(candidate["subtasks"]))
                self.assertEqual(len(audit["handoffs"]), max(0, len(candidate["subtasks"]) - 1))
            verdicts.append(audit["verdict"])
        self.assertEqual(verdicts.count("pass"), 4)
        self.assertEqual(verdicts.count("revise"), 5)
        self.assertEqual(verdicts.count("unresolved"), 1)

    def test_all_core_templates_pass_authored_template_schema(self):
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        schemas = {p.name: json.loads(p.read_bytes())
                   for p in (ROOT / "shared/template_schemas_v1_5_2").glob("*.json")}
        registry = Registry().with_resources(
            (name, Resource.from_contents(data)) for name, data in schemas.items()
        )
        for role in ("generator", "reviewer"):
            validator = Draft202012Validator(schemas[role + "_template.schema.json"], registry=registry)
            for row in core_library(role, "r2r-en"):
                with self.subTest(role=role, template=row["template_id"]):
                    validator.validate(row)

    def test_generator_prompt_core_then_dynamic_then_schema(self):
        source_text = "Walk through the doorway and stop beside the table."
        ids = select_examples("generator", "r2r-en", source_text)
        prompt, _ = compile_prompt("generator", "initial", profile="r2r-en",
                                   selected_ids=ids, original_instruction=source_text)
        core_header = "FIXED R2R-EN GENERATOR CORE: exactly 10"
        dynamic_header = "DYNAMIC R2R-EN GENERATOR EXAMPLES:"
        schema_header = "ACTIVE OUTPUT SCHEMA for this phase"
        self.assertIn("shared/dataset_rules/r2r_en.md", prompt)
        self.assertIn(core_header, prompt)
        self.assertIn(dynamic_header, prompt)
        self.assertEqual(len(set(__import__("re").findall(r"R2R-CORE-G\d{2}", prompt))), 10)
        self.assertLess(prompt.index("shared/dataset_rules/r2r_en.md"), prompt.index(core_header))
        self.assertLess(prompt.index(core_header), prompt.index(dynamic_header))
        self.assertLess(prompt.index(dynamic_header), prompt.index(schema_header))
        self.assertNotIn("RXR SHARED SEMANTIC RULES", prompt)
        self.assertNotIn("RXR ROLE GUIDANCE", prompt)
        self.assertNotIn("FIXED RXR", prompt)

    def test_reviewer_prompt_core_dynamic_and_verdict_independence(self):
        source_text = "Walk through the doorway and stop beside the table."
        ids = select_examples("reviewer", "r2r-en", source_text)
        prompt, _ = compile_prompt("reviewer", "review", profile="r2r-en",
                                   selected_ids=ids, original_instruction=source_text)
        core_header = "FIXED R2R-EN REVIEWER CORE: exactly 10"
        dynamic_header = "DYNAMIC R2R-EN REVIEWER EXAMPLES:"
        schema_header = "ACTIVE OUTPUT SCHEMA for this phase"
        self.assertIn(core_header, prompt)
        self.assertIn(dynamic_header, prompt)
        self.assertIn("not a vote", prompt)
        self.assertEqual(len(set(__import__("re").findall(r"R2R-CORE-R\d{2}", prompt))), 10)
        self.assertLess(prompt.index(core_header), prompt.index(dynamic_header))
        self.assertLess(prompt.index(dynamic_header), prompt.index(schema_header))
        self.assertNotIn("RXR SHARED SEMANTIC RULES", prompt)

    def test_request_and_bundle_record_fixed_core_separately_from_dynamic(self):
        source_text = "Walk through the doorway and stop beside the table."
        ids = select_examples("generator", "r2r-en", source_text)
        req = request("generator", "initial", {"original_instruction": source_text},
                      {"model": "fixture", "effort": "low"}, "r2r-en", ids)
        self.assertEqual(req["fixed_core_template_ids"],
                         [f"R2R-CORE-G{i:02d}" for i in range(1, 11)])
        self.assertEqual(req["template_bundle"]["fixed_core_ids"], req["fixed_core_template_ids"])
        self.assertEqual(req["template_bundle"]["dynamic_ids"], ids)
        self.assertFalse(set(ids) & set(req["fixed_core_template_ids"]))
        self.assertEqual(req["dataset_rules"]["version"], "v6.2-r2r-en")
        self.assertIn("shared/dataset_rules/r2r_en.md", req["dataset_rules"]["files"])
        bundle = template_bundle_metadata("reviewer", "r2r-en",
                                          select_examples("reviewer", "r2r-en", source_text))
        self.assertEqual(len(bundle["fixed_core_ids"]), 10)

    def test_r2r_rule_metadata_is_profile_scoped_and_not_shared_contract(self):
        metadata = dataset_rules_metadata("r2r-en")
        self.assertEqual(metadata["files"], ["shared/semantic_contract.md", "shared/dataset_rules/r2r_en.md"])
        self.assertEqual(metadata["version"], "v6.2-r2r-en")
        shared = (ROOT / "shared/semantic_contract.md").read_text(encoding="utf-8")
        rxr = (ROOT / "shared/dataset_rules/rxr_en_us.md").read_text(encoding="utf-8")
        self.assertNotIn("R2R-specific", shared)
        self.assertNotIn("R2R Core", shared)
        self.assertNotIn("R2R", rxr)
        self.assertIn("R2R-specific", (ROOT / "shared/dataset_rules/r2r_en.md").read_text(encoding="utf-8"))

    def test_rxr_v61_prompt_artifacts_remain_exact(self):
        manifest = json.loads((ROOT / "provenance/rxr_v61_frozen.json").read_bytes())
        expected_hashes = {entry["path"]: entry["git_blob_sha1"] for entry in manifest["compiled_artifacts"]}
        cases = [
            ("generator", "initial", "generator/compiled_rxr-en-us.txt"),
            ("generator", "repair", "generator/compiled_repair_rxr-en-us.txt"),
            ("reviewer", "review", "reviewer/compiled_rxr-en-us.txt"),
        ]
        for role, phase, path in cases:
            ids = select_examples(role, "rxr-en-us", "")
            actual, _ = compile_prompt(role, phase, profile="rxr-en-us", selected_ids=ids)
            data = actual.encode("utf-8")
            blob = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\\0" + data).hexdigest()
            with self.subTest(path=path):
                self.assertEqual(blob, expected_hashes[path])

    def test_rxr_v61_files_match_frozen_manifest(self):
        manifest = json.loads((ROOT / "provenance/rxr_v61_frozen.json").read_bytes())
        for entry in manifest["files"]:
            path = ROOT / entry["path"]
            data = path.read_bytes()
            actual = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\\0" + data).hexdigest()
            with self.subTest(path=entry["path"]):
                self.assertEqual(actual, entry["git_blob_sha1"])
        # Compiled artifacts are regenerated by host.compile during CI; their
        # v6.1 baseline hashes are checked against live compiler output above.

if __name__ == "__main__":
    unittest.main()
