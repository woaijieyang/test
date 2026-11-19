import unittest

from host.compile import compile_prompt, core_library
from host.run import dataset_rules_metadata, prompt_components_metadata
from host.template_selector import (
    PROFILES, library, r2r_features, select_examples, selection_evidence,
)


class R2RSpecializationTests(unittest.TestCase):
    def test_r2r_fragment_cues_rank_but_do_not_encode_a_segmentation_decision(self):
        coupled = "Turn right and continue past the piano. Turn left and stop in the archway."
        transition = (
            "Go down the stairs, turn left and enter the room. "
            "Wait near the chairs that are facing the fireplace."
        )
        coupled_cues, _ = r2r_features(coupled)
        transition_cues, _ = r2r_features(transition)
        self.assertIn("landmark_conditioned_navigation", coupled_cues)
        self.assertIn("doorway_selection_and_crossing", coupled_cues)
        self.assertNotIn("single_stage_keep", coupled_cues)
        self.assertNotIn("multi_stage_split", coupled_cues)
        self.assertIn("room_transition", transition_cues)
        self.assertIn("stairs_or_level_change", transition_cues)
        self.assertIn("intermediate_stop_or_wait", transition_cues)
        self.assertNotIn("single_stage_keep", transition_cues)
        self.assertNotIn("multi_stage_split", transition_cues)

    def test_r2r_dynamic_selection_ranges_and_reviewer_pairing(self):
        sources = (
            "Turn right and continue past the piano. Turn left and stop in the archway.",
            "Go down the stairs, turn left and enter the room. Wait near the chairs that are facing the fireplace.",
            "Walk to the second doorway on the left, pass the table, and stop near the rug.",
        )
        reviewer_rows = {row["template_id"]: row for row in library("reviewer", "r2r-en")}
        for source in sources:
            generator_ids = select_examples("generator", "r2r-en", source)
            reviewer_ids = select_examples("reviewer", "r2r-en", source)
            self.assertTrue(6 <= len(generator_ids) <= 8)
            paired = reviewer_ids[:len(generator_ids)]
            diagnostics = reviewer_ids[len(generator_ids):]
            self.assertEqual(
                [reviewer_rows[item]["pair_id"] for item in paired],
                generator_ids,
            )
            self.assertTrue(2 <= len(diagnostics) <= 4)
            self.assertTrue(all(reviewer_rows[item].get("pair_id") is None for item in diagnostics))
            self.assertEqual(len(set(reviewer_ids)), len(reviewer_ids))
            evidence = selection_evidence("generator", "r2r-en", source, generator_ids)
            self.assertEqual([item["template_id"] for item in evidence], generator_ids)

    def test_r2r_explicit_dynamic_count_is_fail_closed(self):
        source = "Walk through the doorway and stop near the table."
        for invalid in (1, 5, 9, 25):
            with self.subTest(count=invalid), self.assertRaises(ValueError):
                select_examples("generator", "r2r-en", source, count=invalid)
        self.assertEqual(len(select_examples("generator", "r2r-en", source, count=6)), 6)
        self.assertEqual(len(select_examples("generator", "r2r-en", source, count=8)), 8)

    def test_r2r_role_guidance_is_loaded_only_for_matching_profile_and_role(self):
        source = "Go down the stairs, enter the room, and wait near the chairs."
        for role, phases in (("generator", ("initial", "repair")),
                             ("reviewer", ("review", "recheck"))):
            selected = select_examples(role, "r2r-en", source)
            guidance_path = f"{role}/dataset_rules/r2r_en.md"
            for phase in phases:
                prompt, _ = compile_prompt(
                    role, phase, profile="r2r-en", selected_ids=selected,
                    original_instruction=source,
                )
                self.assertIn("shared/dataset_rules/r2r_en.md", prompt)
                self.assertIn(guidance_path, prompt)
                self.assertNotIn("RXR SHARED SEMANTIC RULES", prompt)
                self.assertNotIn("RXR ROLE GUIDANCE", prompt)
                self.assertNotIn("FIXED RXR", prompt)
                self.assertEqual(prompt.count("R2R ROLE GUIDANCE"), 1)

        rxr_ids = select_examples("generator", "rxr-en-us", source)
        rxr_prompt, _ = compile_prompt(
            "generator", "initial", profile="rxr-en-us", selected_ids=rxr_ids,
            original_instruction=source,
        )
        self.assertIn("RXR ROLE GUIDANCE", rxr_prompt)
        self.assertNotIn("R2R ROLE GUIDANCE", rxr_prompt)
        self.assertNotIn("generator/dataset_rules/r2r_en.md", rxr_prompt)

    def test_r2r_shared_and_role_guidance_have_non_overlapping_responsibilities(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        shared = (root / "shared/dataset_rules/r2r_en.md").read_text(encoding="utf-8")
        generator = (root / "generator/dataset_rules/r2r_en.md").read_text(encoding="utf-8")
        reviewer = (root / "reviewer/dataset_rules/r2r_en.md").read_text(encoding="utf-8")
        self.assertNotIn("## Role-specific execution order", shared)
        self.assertIn("## Required decision sequence", generator)
        self.assertIn("## Independent review sequence", reviewer)
        self.assertNotIn("Reviewer must independently", generator)
        self.assertNotIn("Generator alone authors", reviewer)

    def test_r2r_metadata_freezes_all_profile_rules_and_role_guidance(self):
        metadata = dataset_rules_metadata("r2r-en")
        self.assertEqual(
            metadata["files"],
            [
                "shared/semantic_contract.md",
                "shared/dataset_rules/r2r_en.md",
                "shared/dataset_rules/r2r_fragments.json",
                "generator/dataset_rules/r2r_en.md",
                "reviewer/dataset_rules/r2r_en.md",
            ],
        )
        for role in ("generator", "reviewer"):
            components = prompt_components_metadata(role, "initial" if role == "generator" else "review", "r2r-en")
            self.assertIn(f"{role}/dataset_rules/r2r_en.md", [item["path"] for item in components["files"]])
        rxr = dataset_rules_metadata("rxr-en-us")
        self.assertEqual(len(rxr["files"]), 4)
        self.assertNotIn("shared/dataset_rules/r2r_fragments.json", rxr["files"])

    def test_rxr_compiled_prompt_hashes_remain_frozen(self):
        from shared.identity import text_hash

        generator_ids = select_examples("generator", "rxr-en-us", "")
        reviewer_ids = select_examples("reviewer", "rxr-en-us", "")
        cases = (
            ("generator", "initial", generator_ids, "864e5a37a2c7b8b7fef45c4c58ceeebc87183d52d0db9ab26e0b73c1b75f4a21"),
            ("generator", "repair", generator_ids, "81dc6e312f6106937bafb2f317048e0bcae01e23748fc9c9749051581433894f"),
            ("reviewer", "review", reviewer_ids, "18c1f6a7611086f8d9a2888390f38b9c2224d2e1f749c3ea1059a2a6a032fb7b"),
        )
        for role, phase, selected, expected_hash in cases:
            with self.subTest(role=role, phase=phase):
                prompt, _ = compile_prompt(
                    role, phase, profile="rxr-en-us", selected_ids=selected,
                    original_instruction="",
                )
                self.assertEqual(text_hash(prompt), expected_hash)

    def test_fixed_r2r_core_remains_ten_per_role(self):
        self.assertEqual(len(core_library("generator", "r2r-en")), 10)
        self.assertEqual(len(core_library("reviewer", "r2r-en")), 10)


if __name__ == "__main__":
    unittest.main()
