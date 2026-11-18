# Reviewer — independent source-grounded audit

Reviewer uses the same `shared/semantic_contract.md` as Generator. `prompt.md` and `checklist.md` define independent L0–L6 review. The active `output.schema.json` is used for both R0 and R1.

## Input Independence

R0 receives the original instruction, frozen Candidate stages and exact rendered text. It does not receive Generator Stage Audit or Handoff self-assessment. R1 receives the new Source/Candidate/rendered text plus the frozen R0 Review, old Candidate and old rendered text. It independently rechecks every prior blocking Finding and the entire new Candidate.

## Review Output

- Dimensions: `source_fidelity`, `closure_handoff`, `segmentation_adequacy`.
- `source_coverage`: event-level requirements and exact Candidate Evidence.
- `layer_checks`: L0–L6 exactly once and in order.
- `stage_checks`: every actual stage and its five elements.
- `handoffs`: every adjacent pair.
- `findings`: material, evidence-backed defects with execution consequence and a local nonbinding repair.
- R0 `prior_finding_reviews` is empty; R1 must disposition each R0 blocker exactly once.

PASS requires all material source requirements preserved, no unsupported additions, complete executable stages, supported handoffs and adequate grouping. REVISE requires a material repairable Candidate defect. UNRESOLVED is only for route-critical ambiguity in the original Source that cannot be resolved from context. Style preference is not a Finding. A PASS is not navigation success.

## Fixed Core and Dynamic Library

| Profile | Fixed Reviewer Core | Paired Dynamic | Diagnostics |
|---|---:|---:|---:|
| R2R English | R01–R10 (10) | 29 eligible; select 6–8 | 23 eligible; select 2–4 |
| RxR en-US | R01–R10 (10) | 35 eligible; select 2–4 | 29 eligible; select 0–2 |

Core is always loaded in stable order. Paired Dynamic is linked to selected non-Core Generator Dynamic IDs; Diagnostics supplement it. Pair IDs describe teaching lineage, not a verdict or forced runtime order. R2R and RxR libraries are isolated. Legacy is provenance only.

## Teaching Quality

Each case must have a source-grounded requirement map, Candidate Evidence from the correct stage, accurate semantic relation, defensible Verdict, material consequence and actionable local repair where applicable. Curated cases are not official human review labels or navigation ground truth. Schema and quote validation do not replace semantic review.
