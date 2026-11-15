# Reviewer — independent, source-grounded L0–L6 audit

Reviewer uses exactly the same `shared/semantic_contract.md` as Generator. `prompt.md` and `checklist.md` define L0 rendered-text integrity, L1 source coverage, L2 dependencies, L3 five-element stage checks, L4 adjacent handoffs, L5 grouping, and L6 whole-route readback. The active `output.schema.json` is Draft 2020-12 and is shared by R0 and R1.

## Input independence

R0 receives the original instruction, frozen candidate stage strings and exact rendered text. It never receives Generator's `stage_audit` or Handoff self-assessment. R1 is a fresh independent session; it receives the new source/candidate/rendered text plus the frozen R0 review, exact R0 candidate and exact R0 rendered text so it can verify each prior blocking finding. It does not receive G1's response as proof and must independently re-audit the complete new candidate.

## Runtime output

- Dimensions are exactly `source_fidelity`, `closure_handoff`, `segmentation_adequacy`; do not use `fidelity`.
- `source_coverage` is event-level and candidate evidence is `{subtask_index, quote}`.
- `layer_checks` must report L0–L6 exactly once and in order.
- Each `stage_checks` item uses `subtask_index`, all five structured elements, source requirement IDs, source quotes and carryover.
- Each finding contains source evidence, candidate evidence, failed layer/check, dimension, affected stage indices, separate repair-target indices, concrete execution consequence and a local repair option.
- Candidate evidence may cite both sides of a handoff even when the repair target is only one stage. Evidence indices are validated independently from repair indices.
- R0 returns `prior_finding_reviews: []`. R1 returns exactly one `resolved/partially_resolved/unresolved` disposition for each R0 finding, with evidence from the new candidate. R1 may PASS only if all prior blockers are resolved and no new blocker exists.

A finding is advisory; Generator may reject it when the source does not support the proposed action. A PASS is not navigation success.

## Teaching corpus

- `templates/R2R/paired/`: 35 paired R2R Reviewer examples.
- `templates/R2R/diagnostics/`: 26 R2R adversarial diagnostics.
- `templates/RxR/paired/`: 35 paired RxR Reviewer examples.
- `templates/RxR/diagnostics/`: 29 RxR adversarial diagnostics.
- `templates/RxR/legacy/`: 10 provenance-labelled legacy Reviewer examples.

The 35 paired examples per dataset are not unique gold segmentations. Diagnostics teach material defects and must not be treated as positive examples. Retrieve 8–12 source-matched cases once for R0 and reuse the same Reviewer IDs in R1. Full schema, evidence and verdict gates are defined in `host/README.md`.
