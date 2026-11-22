"""R2R teaching-evidence checks: source text, candidate defects, and labels must agree."""
import json
import unittest

from host.compile import ROOT, teaching_card
from host.template_selector import validate_template


class R2RTeachingEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = ROOT / "reviewer/templates/R2R/diagnostics"
        rows = [json.loads(path.read_text(encoding="utf-8"))
                for path in sorted(folder.glob("*.json"))]
        cls.bank = {row["template_id"]: row for row in rows}
        if len(cls.bank) != len(rows):
            raise ValueError("Duplicate authored Reviewer diagnostic ID")

    def example(self, number):
        return self.bank[f"R2R-DIAG-{number:02d}"]

    def test_revise_teaching_must_change_actual_candidate(self):
        for name, row in self.bank.items():
            with self.subTest(template=name):
                if row["expected_review"]["verdict"] != "revise":
                    continue
                original = row["review_input"]["original_instruction"]
                candidate = "\n".join(row["review_input"]["candidate"]["subtasks"])
                self.assertNotEqual(original, candidate)

    def test_literal_preserved_requirements_are_not_marked_missing(self):
        for number in range(1, 21):
            row = self.example(number)
            candidate = "\n".join(row["review_input"]["candidate"]["subtasks"])
            for coverage in row["expected_review"]["source_coverage"]:
                if coverage["source_quote"] not in candidate:
                    continue
                with self.subTest(template=number, requirement=coverage["requirement_id"]):
                    self.assertEqual(coverage["status"], "covered")
                    self.assertTrue(any(
                        evidence in candidate for evidence in coverage["candidate_evidence"]
                    ))

    def test_findings_point_to_actual_changed_requirement_and_quotes(self):
        for number in range(1, 21):
            row = self.example(number)
            audit = row["expected_review"]
            if audit["dimensions"]["segmentation_adequacy"] == "issue":
                continue
            changed = {r["requirement_id"] for r in audit["source_coverage"]
                       if r["status"] in ("altered_or_missing", "omitted")}
            for finding in audit["findings"]:
                with self.subTest(template=number, finding=finding["problem"][:40]):
                    self.assertTrue(set(finding["source_requirement_ids"]) & changed)
                    self.assertIn(finding["source_quote"], row["review_input"]["original_instruction"])
                    candidate = "\n".join(row["review_input"]["candidate"]["subtasks"])
                    self.assertTrue(all(q in candidate for q in finding["candidate_evidence"]))

    def test_constraint_and_terminal_diagnostics(self):
        for number in (8, 18):
            audit = self.example(number)["expected_review"]
            self.assertEqual([x["requirement_id"] for x in audit["source_coverage"]
                              if x["status"] != "covered"], ["SRC-02"])
            self.assertEqual(audit["findings"][0]["source_requirement_ids"], ["SRC-02"])
            self.assertEqual(audit["stage_checks"][0]["ending"]["stop_scope"], "terminal")
        for number, ids in ((7, ["SRC-02"]), (17, ["SRC-02"]),
                            (19, ["SRC-02", "SRC-03"])):
            audit = self.example(number)["expected_review"]
            self.assertEqual(audit["dimensions"]["closure_handoff"], "issue")
            found = {rid for f in audit["findings"] for rid in f["source_requirement_ids"]}
            self.assertEqual(found, set(ids))
            self.assertEqual(audit["stage_checks"][0]["ending"]["stop_scope"], "none")
        audit = self.example(20)["expected_review"]
        self.assertEqual(audit["source_coverage"][2]["status"], "altered_or_missing")
        self.assertEqual(audit["findings"][0]["source_requirement_ids"], ["SRC-03"])
        self.assertIn("Stop beside the stairs.", self.example(20)["review_input"]["candidate"]["subtasks"][0])

    def test_grouping_diagnostic_is_precise_about_boundary(self):
        audit = self.example(28)["expected_review"]
        self.assertEqual(audit["dimensions"]["source_fidelity"], "pass")
        self.assertEqual(audit["dimensions"]["segmentation_adequacy"], "issue")
        finding = audit["findings"][0]
        self.assertEqual(finding["affected_subtask_indices"], [1, 2])
        self.assertIn("terminal", finding["problem"].lower())

    def test_revised_templates_validate_authored_schema_and_projection(self):
        for number in (4, 5, 6, 8, 10, 12, 15, 16, 17, 18, 20, 24, 28):
            row = self.example(number)
            with self.subTest(template=number):
                validate_template("reviewer", row)
                card = teaching_card(row, "reviewer", detailed=True)
                self.assertEqual(card["teaching"]["verdict"], "revise")
                self.assertTrue(card["teaching"]["findings"])


if __name__ == "__main__":
    unittest.main()
