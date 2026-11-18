import hashlib
import json
import unittest
from pathlib import Path

from adapter.source import Source
from host.compile import ROOT, compile_prompt, core_library, runtime_review_output
from host.run import request, dataset_rules_metadata, template_bundle_metadata
from host.template_selector import library, select_examples
from host import protocol


class R2RCoreTests(unittest.TestCase):
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
        for role, expected in (("generator", 25), ("reviewer", 52)):
            rows = library(role, "r2r-en")
            self.assertEqual(len(rows), expected)
            self.assertTrue(all(x["role"] == role and x["dataset_scope"] == "R2R"
                                and x["language"] == "en" for x in rows))
            self.assertFalse(any(x["template_id"].startswith("R2R-CORE-") for x in rows))
            core_rows = core_library(role, "r2r-en")
            promoted = {x["provenance"]["core_curated_from"] for x in core_rows}
            self.assertFalse(promoted & {x["template_id"] for x in rows})
            if role == "reviewer":
                dynamic_generator_ids = {
                    x["template_id"] for x in library("generator", "r2r-en")
                }
                dynamic_pair_ids = {x.get("pair_id") for x in rows if x.get("pair_id")}
                self.assertTrue(dynamic_generator_ids.issubset(dynamic_pair_ids))
                self.assertEqual(sum(not x.get("pair_id") for x in rows), 23)
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
        self.assertEqual(req["dataset_rules"]["version"], "r2r-en-profile")
        self.assertIn("shared/dataset_rules/r2r_en.md", req["dataset_rules"]["files"])
        bundle = template_bundle_metadata("reviewer", "r2r-en",
                                          select_examples("reviewer", "r2r-en", source_text))
        self.assertEqual(len(bundle["fixed_core_ids"]), 10)

    def test_r2r_rule_metadata_is_profile_scoped_and_not_shared_contract(self):
        metadata = dataset_rules_metadata("r2r-en")
        self.assertEqual(metadata["files"], ["shared/semantic_contract.md", "shared/dataset_rules/r2r_en.md"])
        self.assertEqual(metadata["version"], "r2r-en-profile")
        shared = (ROOT / "shared/semantic_contract.md").read_text(encoding="utf-8")
        rxr = (ROOT / "shared/dataset_rules/rxr_en_us.md").read_text(encoding="utf-8")
        self.assertNotIn("R2R-specific", shared)
        self.assertNotIn("R2R Core", shared)
        self.assertNotIn("R2R", rxr)
        self.assertIn("R2R-specific", (ROOT / "shared/dataset_rules/r2r_en.md").read_text(encoding="utf-8"))

    def test_rxr_compiler_matches_its_generated_artifacts(self):
        cases = [
            ("generator", "initial", "generator/compiled_rxr-en-us.txt"),
            ("generator", "repair", "generator/compiled_repair_rxr-en-us.txt"),
            ("reviewer", "review", "reviewer/compiled_rxr-en-us.txt"),
        ]
        for role, phase, path in cases:
            ids = select_examples(role, "rxr-en-us", "")
            actual, _ = compile_prompt(role, phase, profile="rxr-en-us", selected_ids=ids)
            expected = (ROOT / path).read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertEqual(actual, expected)

    def test_rxr_profile_assets_match_integrity_manifest(self):
        manifest = json.loads((ROOT / "provenance/rxr_profile_integrity.json").read_bytes())
        for entry in manifest["files"]:
            path = ROOT / entry["path"]
            data = path.read_bytes()
            actual = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
            with self.subTest(path=entry["path"]):
                self.assertEqual(actual, entry["git_blob_sha1"])


    def test_r2r_g0_r0_g1_r1_freezes_core_dynamic_rules_and_prompt(self):
        from test_runtime_contract_v2 import SOURCE, generator_candidate, reviewer_output
        src = Source("r2r-four-phase", "R2R", "en", SOURCE)
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
                    "request_id": f"r2r-{len(requests)}"
                }
            }

        from host.run import run_record
        result = run_record(
            src, transport,
            pins={role: {"model": "fixture", "effort": "low"}
                  for role in ("generator", "reviewer")}
        )
        self.assertEqual(result["disposition"], "accepted_candidate", result["error"])
        self.assertEqual([(x["role"], x["phase"]) for x in requests], [
            ("generator", "initial"), ("reviewer", "review"),
            ("generator", "repair"), ("reviewer", "recheck")
        ])
        for req in requests:
            self.assertEqual(req["profile"], "r2r-en")
            self.assertEqual(len(req["fixed_core_template_ids"]), 10)
            self.assertEqual(req["dataset_rules"]["version"], "r2r-en-profile")
            self.assertIn("shared/dataset_rules/r2r_en.md", req["dataset_rules"]["files"])
            self.assertNotIn("RXR SHARED SEMANTIC RULES", req["messages"][0]["content"])
            self.assertNotIn("RXR ROLE GUIDANCE", req["messages"][0]["content"])
        self.assertEqual(requests[0]["selected_example_ids"], requests[2]["selected_example_ids"])
        self.assertEqual(requests[1]["selected_example_ids"], requests[3]["selected_example_ids"])
        self.assertEqual(requests[0]["fixed_core_template_ids"], requests[2]["fixed_core_template_ids"])
        self.assertEqual(requests[1]["fixed_core_template_ids"], requests[3]["fixed_core_template_ids"])
        self.assertEqual(
            requests[0]["template_bundle"]["sha256"],
            requests[2]["template_bundle"]["sha256"]
        )
        self.assertEqual(
            requests[1]["template_bundle"]["sha256"],
            requests[3]["template_bundle"]["sha256"]
        )

    def test_all_four_r2r_phases_compile_with_fixed_core_and_dynamic_examples(self):
        source = "Walk through the first doorway, turn left, enter the second room, and stop beside the desk."
        for role, phases in (("generator", ("initial", "repair")),
                             ("reviewer", ("review", "recheck"))):
            selected = select_examples(role, "r2r-en", source)
            for phase in phases:
                prompt, _ = compile_prompt(role, phase, profile="r2r-en",
                                           selected_ids=selected,
                                           original_instruction=source)
                self.assertIn("FIXED R2R-EN", prompt)
                self.assertIn("DYNAMIC R2R-EN", prompt)
                self.assertIn("shared/dataset_rules/r2r_en.md", prompt)
                self.assertLess(prompt.index("FIXED R2R-EN"),
                                prompt.index("DYNAMIC R2R-EN"))
                self.assertLess(prompt.index("DYNAMIC R2R-EN"),
                                prompt.index("ACTIVE OUTPUT SCHEMA"))


    def test_r02_coverage_evidence_is_requirement_specific(self):
        row = next(x for x in core_library("reviewer", "r2r-en") if x["template_id"] == "R2R-CORE-R02")
        coverage = row["expected_review"]["source_coverage"]
        self.assertEqual(coverage[1]["candidate_evidence"], ["In the hallway take a right and go down the hall, keeping straight."])
        self.assertEqual(coverage[2]["candidate_evidence"], ["the next door on your right"])
        self.assertEqual(coverage[3]["candidate_evidence"], ["Stop in the room just past the door on the inside of the doorway."])
        self.assertEqual(coverage[2]["status"], "altered_or_missing")

    def test_reviewer_core_provenance_is_structured(self):
        for row in core_library("reviewer", "r2r-en"):
            provenance = row.get("provenance", {})
            self.assertFalse(any(str(k).isdigit() for k in provenance), row["template_id"])
            self.assertTrue(provenance.get("kind"), row["template_id"])
            self.assertTrue(provenance.get("source_status"), row["template_id"])
            self.assertTrue(provenance.get("curation_basis"), row["template_id"])

    def test_r01_teaching_notes_do_not_invent_stairs_or_doorway_stop(self):
        row = next(x for x in core_library("reviewer", "r2r-en") if x["template_id"] == "R2R-CORE-R01")
        notes = json.dumps(row["teaching_notes"]).lower()
        self.assertNotIn("source-selected doorway relative to the stairs", notes)
        self.assertNotIn("stop in the doorway", notes)

    def test_examples_false_disables_dynamic_but_never_fixed_core(self):
        prompt, _ = compile_prompt("generator", "initial", profile="r2r-en", examples=False)
        self.assertIn("FIXED R2R-EN GENERATOR CORE: exactly 10", prompt)
        self.assertIn("R2R-CORE-G10", prompt)
        self.assertNotIn("DYNAMIC R2R-EN GENERATOR EXAMPLES:", prompt)
        prompt, _ = compile_prompt("reviewer", "review", profile="rxr-en-us", examples=False)
        self.assertIn("FIXED RXR REVIEWER CORE: exactly 10", prompt)
        self.assertIn("RXR-CORE-R10", prompt)
        self.assertNotIn("DYNAMIC RXR-EN-US REVIEWER EXAMPLES:", prompt)

    def test_compiled_prompts_and_manifest_match_fixed_core_contract(self):
        cases = [
            ("generator/compiled_r2r-en.txt", "R2R", "R2R", "generator", "G"),
            ("generator/compiled_repair_r2r-en.txt", "R2R", "R2R", "generator", "G"),
            ("reviewer/compiled_r2r-en.txt", "R2R", "R2R", "reviewer", "R"),
            ("generator/compiled_rxr-en-us.txt", "RxR", "RXR", "generator", "G"),
            ("generator/compiled_repair_rxr-en-us.txt", "RxR", "RXR", "generator", "G"),
            ("reviewer/compiled_rxr-en-us.txt", "RxR", "RXR", "reviewer", "R"),
        ]
        for path, dataset, id_prefix, role, prefix in cases:
            prompt = (ROOT / path).read_text(encoding="utf-8")
            label = "R2R-EN" if dataset == "R2R" else "RXR"
            self.assertIn(f"FIXED {label} {role.upper()} CORE: exactly 10", prompt, path)
            for i in range(1, 11):
                self.assertIn(f"{id_prefix}-CORE-{prefix}{i:02d}", prompt, (path, i))
            selected_line = next((line for line in prompt.splitlines()
                                  if "Selected dynamic example IDs in order:" in line), "")
            self.assertNotIn("LEGACY", selected_line, path)
        manifest = json.loads((ROOT / "provenance/build_manifest.json").read_bytes())
        for entry in manifest.values():
            self.assertEqual(entry["fixed_core_count"], 10)
            self.assertEqual(len(entry["fixed_core_ids"]), 10)

    def test_generator_core_cards_expose_primary_boundary_and_case_rationale(self):
        from host.compile import teaching_card
        for row in core_library("generator", "r2r-en"):
            card = teaching_card(row, "generator", detailed=True)
            self.assertTrue(card.get("primary_decision_boundary"), row["template_id"])
            self.assertTrue(card.get("case_rationale"), row["template_id"])
            self.assertTrue(card.get("transfer_rule"), row["template_id"])

    def test_r09_r10_reviewer_teaching_metadata_matches_case_shape(self):
        rows = {row["template_id"]: row for row in core_library("reviewer", "r2r-en")}
        self.assertNotIn("single_stage_keep", rows["R2R-CORE-R09"]["teaching_notes"]["retrieval_tags"])
        r10 = rows["R2R-CORE-R10"]
        self.assertFalse(r10["provenance"]["candidate_corruption_is_authored_not_model_output"])
        self.assertEqual(r10["review_input"]["candidate"]["subtasks"], [])
        principle = r10["teaching_notes"]["review_principle"].lower()
        self.assertNotIn("check each stage", principle)
        self.assertNotIn("preceding exit", principle)

    def test_runtime_library_loads_only_schema_validated_templates(self):
        from host.template_selector import validate_template
        for role in ("generator", "reviewer"):
            for row in library(role, "r2r-en"):
                validate_template(role, row, source_path=row["template_id"])
            for row in core_library(role, "r2r-en"):
                validate_template(role, row, source_path=row["template_id"])

if __name__ == "__main__":
    unittest.main()
