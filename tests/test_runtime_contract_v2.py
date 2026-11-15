import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from host import protocol
from host.run import run_record
from adapter.source import Source
from host.compile import ROOT
from shared.identity import ContractError

SOURCE = (
    "Exit the kitchen and turn right, then go down the hall and stop by "
    "the second door on the right."
)

def generator_candidate(repaired=False):
    first = "Exit the kitchen and turn right."
    second = (
        "From the right turn at the kitchen exit, go down the hall and stop by "
        "the second door on the right."
        if repaired else
        "From the hallway, stop by the second door on the right."
    )
    return {
        "status": "ok",
        "subtasks": [first, second],
        "issues": [],
        "stage_audit": [
            {
                "subtask_index": 0,
                "entry": {
                    "mode": "episode_start",
                    "text": "Begin at the episode start.",
                    "candidate_quotes": []
                },
                "target": {
                    "text": "The kitchen exit and right-turn transition.",
                    "candidate_quotes": ["turn right"]
                },
                "process": {
                    "text": first,
                    "candidate_quotes": [first]
                },
                "ending": {
                    "kind": "explicit_event",
                    "text": "Complete the kitchen exit and right turn.",
                    "candidate_quotes": [first],
                    "stop_scope": "none"
                },
                "conditions": {"text": None, "candidate_quotes": []},
                "source_quotes": ["Exit the kitchen and turn right"],
                "carryover": ["The right-turn orientation established at the kitchen exit."]
            },
            {
                "subtask_index": 1,
                "entry": {
                    "mode": "explicit_context",
                    "text": (
                        "Begin from the right-turn state established at the kitchen exit."
                        if repaired else
                        "The candidate assumes the agent is already in the hallway."
                    ),
                    "candidate_quotes": [
                        "From the right turn at the kitchen exit" if repaired else "From the hallway"
                    ]
                },
                "target": {
                    "text": "The second door on the right.",
                    "candidate_quotes": ["the second door on the right"]
                },
                "process": {
                    "text": second,
                    "candidate_quotes": [second]
                },
                "ending": {
                    "kind": "explicit_event",
                    "text": "Stop by the second door on the right.",
                    "candidate_quotes": ["stop by the second door on the right"],
                    "stop_scope": "terminal"
                },
                "conditions": {"text": None, "candidate_quotes": []},
                "source_quotes": [
                    "go down the hall",
                    "stop by the second door on the right"
                ],
                "carryover": ["The right-turn orientation from the kitchen exit."]
            }
        ],
        "handoffs": [
            {
                "from_subtask_index": 0,
                "to_subtask_index": 1,
                "status": "supported",
                "preceding_exit": {
                    "text": "The first stage completes the kitchen exit and right turn.",
                    "candidate_quote": "turn right"
                },
                "next_entry": {
                    "text": (
                        "The next stage starts from the established right-turn state."
                        if repaired else
                        "The next stage assumes the hallway has already been reached."
                    ),
                    "candidate_quote": (
                        "From the right turn at the kitchen exit" if repaired else "From the hallway"
                    )
                },
                "shared_context": [
                    {"kind": "orientation", "text": "The right-turn orientation at the kitchen exit."}
                ],
                "source_requirement_ids": ["SRC-01", "SRC-02"],
                "handoff_rationale": (
                    "The new entry binds the next movement to the completed kitchen-exit turn."
                    if repaired else
                    "The candidate assumes hallway occupancy but omits the source-required hall traversal."
                )
            }
        ]
    }

def reviewer_output(candidate, repaired=False, r1=False):
    first, second = candidate["subtasks"]
    if repaired:
        coverage = [
            {
                "requirement_id": "SRC-01",
                "source_quote": "Exit the kitchen and turn right",
                "requirement": "Preserve the kitchen exit and right turn.",
                "candidate_evidence": [{"subtask_index": 0, "quote": first}],
                "status": "covered"
            },
            {
                "requirement_id": "SRC-02",
                "source_quote": "go down the hall",
                "requirement": "Execute the hallway traversal after the kitchen exit turn.",
                "candidate_evidence": [{"subtask_index": 1, "quote": "go down the hall"}],
                "status": "covered"
            },
            {
                "requirement_id": "SRC-03",
                "source_quote": "stop by the second door on the right",
                "requirement": "Preserve the final stop at the second door on the right.",
                "candidate_evidence": [{"subtask_index": 1, "quote": "stop by the second door on the right"}],
                "status": "covered"
            }
        ]
        dims = {
            "source_fidelity": "pass",
            "closure_handoff": "pass",
            "segmentation_adequacy": "pass"
        }
        layers = [
            {"layer": name, "status": "pass", "finding_indices": [], "conclusion": "The relevant check passes."}
            for name in protocol.LAYERS
        ]
        findings = []
        handoff_status = "supported"
        stage1_entry = candidate["stage_audit"][1]["entry"]
        prior = (
            [{
                "finding_index": 0,
                "status": "resolved",
                "candidate_evidence": [{"subtask_index": 1, "quote": "go down the hall"}],
                "explanation": "The new stage explicitly performs the previously omitted hall traversal from the established turn state."
            }] if r1 else []
        )
    else:
        coverage = [
            {
                "requirement_id": "SRC-01",
                "source_quote": "Exit the kitchen and turn right",
                "requirement": "Preserve the kitchen exit and right turn.",
                "candidate_evidence": [{"subtask_index": 0, "quote": first}],
                "status": "covered"
            },
            {
                "requirement_id": "SRC-02",
                "source_quote": "go down the hall",
                "requirement": "Execute the hallway traversal; do not assume hallway occupancy before traversing it.",
                "candidate_evidence": [{"subtask_index": 1, "quote": "From the hallway"}],
                "status": "altered_or_missing"
            },
            {
                "requirement_id": "SRC-03",
                "source_quote": "stop by the second door on the right",
                "requirement": "Preserve the final stop at the second door on the right.",
                "candidate_evidence": [{"subtask_index": 1, "quote": "stop by the second door on the right"}],
                "status": "covered"
            }
        ]
        dims = {
            "source_fidelity": "issue",
            "closure_handoff": "issue",
            "segmentation_adequacy": "pass"
        }
        layers = [
            {"layer": name, "status": "pass", "finding_indices": [], "conclusion": "The relevant check passes."}
            for name in protocol.LAYERS
        ]
        layers[1].update(status="issue", finding_indices=[0],
                         conclusion="The hall traversal is omitted.")
        layers[4].update(status="issue", finding_indices=[0],
                         conclusion="The right stage assumes hallway occupancy without the traversal.")
        layers[6].update(status="issue", finding_indices=[0],
                         conclusion="The complete route readback exposes the missing hall traversal.")
        findings = [{
            "code": "OMISSION",
            "failed_layer": "L4_handoffs",
            "c_check": "C09",
            "dimension": "source_fidelity",
            "related_dimensions": ["closure_handoff"],
            "affected_subtask_indices": [1],
            "source_requirement_ids": ["SRC-02"],
            "source_quote": "go down the hall",
            "candidate_evidence": [
                {"subtask_index": 0, "quote": "turn right"},
                {"subtask_index": 1, "quote": "From the hallway"}
            ],
            "evidence_level": "S1",
            "problem": "The candidate begins from the hallway but omits the required movement down the hall.",
            "execution_consequence": "The navigator may skip the corridor traversal and begin door selection from an unsupported state.",
            "repair": {
                "operation": "restore",
                "affected_subtask_indices": [1],
                "instruction": "Restore the source-required movement down the hall after the kitchen-exit turn.",
                "protected_requirements": [
                    "Preserve the kitchen exit and right turn.",
                    "Preserve the final stop by the second door on the right."
                ]
            }
        }]
        handoff_status = "gap"
        stage1_entry = candidate["stage_audit"][1]["entry"]
        prior = []
    stage_checks = []
    for i, text in enumerate(candidate["subtasks"]):
        audit = candidate["stage_audit"][i]
        stage_checks.append({
            "subtask_index": i,
            "status": "supported" if repaired or i == 0 else "gap",
            "entry": audit["entry"],
            "target": audit["target"],
            "process": audit["process"],
            "ending": audit["ending"],
            "conditions": audit["conditions"],
            "source_requirement_ids": ["SRC-01", "SRC-02", "SRC-03"],
            "source_quotes": audit["source_quotes"],
            "carryover": audit["carryover"]
        })
    return {
        "verdict": "pass" if repaired else "revise",
        "dimensions": dims,
        "source_coverage": coverage,
        "layer_checks": layers,
        "findings": findings,
        "stage_checks": stage_checks,
        "handoffs": [{
            **candidate["handoffs"][0],
            "status": handoff_status
        }],
        "prior_finding_reviews": prior
    }

class RuntimeContractV2Tests(unittest.TestCase):
    def test_all_three_runtime_schemas_are_valid_draft_2020_12(self):
        for rel in (
            "generator/output.schema.json",
            "reviewer/output.schema.json",
            "generator/repair.schema.json"
        ):
            schema = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            Draft202012Validator.check_schema(schema)

    def test_generator_ok_and_needs_review_array_gates(self):
        good = generator_candidate(repaired=True)
        protocol.generator(SOURCE, good)
        limited = {
            "status": "needs_review",
            "subtasks": [],
            "issues": [{
                "code": "SOURCE_AMBIGUITY",
                "source_quote": "the second door on the right",
                "problem": "The required door cannot be uniquely identified from the source."
            }],
            "stage_audit": [],
            "handoffs": []
        }
        protocol.generator(SOURCE, limited)

    def test_reviewer_can_cite_both_handoff_stages_but_target_only_stage_two(self):
        candidate = generator_candidate(repaired=False)
        review = reviewer_output(candidate, repaired=False)
        protocol.reviewer(SOURCE, {
            "status": "ok", "subtasks": candidate["subtasks"], "issues": []
        }, review)
        finding = review["findings"][0]
        self.assertEqual(finding["affected_subtask_indices"], [1])
        self.assertEqual(finding["repair"]["affected_subtask_indices"], [1])
        self.assertEqual([e["subtask_index"] for e in finding["candidate_evidence"]], [0, 1])

    def test_g1_responses_are_one_to_one_and_candidate_is_complete(self):
        old_candidate = generator_candidate(repaired=False)
        review = reviewer_output(old_candidate, repaired=False)
        new_candidate = generator_candidate(repaired=True)
        answer = {
            "candidate": new_candidate,
            "responses": [{
                "finding_index": 0,
                "decision": "accept",
                "source_quotes": ["go down the hall"],
                "reason": "The source explicitly requires the omitted hall traversal."
            }]
        }
        protocol.feedback(SOURCE, review, answer)

    def test_r1_receives_and_resolves_prior_r0_finding(self):
        old_candidate = generator_candidate(repaired=False)
        old_review = reviewer_output(old_candidate, repaired=False)
        new_candidate = generator_candidate(repaired=True)
        new_review = reviewer_output(new_candidate, repaired=True, r1=True)
        new_rendered = "
".join(new_candidate["subtasks"])
        old_rendered = "
".join(old_candidate["subtasks"])
        protocol.reviewer(
            SOURCE,
            {"status": "ok", "subtasks": new_candidate["subtasks"], "issues": []},
            new_review,
            rendered_instruction=new_rendered,
            prior_review=old_review,
            prior_candidate={"status": "ok", "subtasks": old_candidate["subtasks"], "issues": []},
            prior_rendered_instruction=old_rendered
        )
        self.assertEqual(new_review["prior_finding_reviews"][0]["status"], "resolved")


    def test_run_record_passes_frozen_r0_context_to_r1(self):
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
        def transport(request):
            requests.append(copy.deepcopy(request))
            output = replies.pop(0)
            return {
                "output": output,
                "receipt": {
                    "model": request["model"],
                    "effort": request["effort"],
                    "request_id": f"offline-{len(requests)}"
                }
            }
        result = run_record(
            Source("runtime-v2-smoke", "R2R", "en", SOURCE),
            transport,
            pins={
                "generator": {"model": "offline-fixture", "effort": "low"},
                "reviewer": {"model": "offline-fixture", "effort": "low"}
            }
        )
        self.assertEqual(result["disposition"], "accepted_candidate")
        self.assertEqual(len(requests), 4)
        r1_payload = json.loads(requests[3]["messages"][1]["content"])
        self.assertIn("prior_review", r1_payload)
        self.assertIn("prior_candidate", r1_payload)
        self.assertIn("prior_rendered_instruction", r1_payload)
        self.assertEqual(
            r1_payload["prior_review"]["findings"][0]["source_quote"],
            "go down the hall"
        )

    def test_r0_must_not_return_prior_finding_reviews(self):
        candidate = generator_candidate(repaired=True)
        review = reviewer_output(candidate, repaired=True)
        review["prior_finding_reviews"] = [{
            "finding_index": 0, "status": "resolved",
            "candidate_evidence": [], "explanation": "should not be present in R0"
        }]
        with self.assertRaises(ContractError):
            protocol.reviewer(
                SOURCE,
                {"status": "ok", "subtasks": candidate["subtasks"], "issues": []},
                review
            )

if __name__ == "__main__":
    unittest.main()
