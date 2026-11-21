# RxR semantic enhancement and integration

## Purpose and boundaries

This change calibrates RxR event identity, correction scope, spatial relation ownership, conditional observations, inherited entries and endpoint refinement. It does not modify the common semantic contract, active wire schemas, Renderer, navigation actor or bounded Generator/Reviewer state machine. R2R is protected by baseline compilation and selection comparisons, including interleaved Profile calls.

The development evidence contains 407 comparable tasks: baseline 275 successes, current 276, 44 recoveries and 43 regressions. These are development observations, not evidence that every regression is a linguistic defect. The runtime never receives success labels, trajectories, evaluation partitions or ground truth. No evaluation instruction is promoted into the teaching library.

## Data and teaching

Ten existing Core examples per role remain mandatory, in unchanged order. Dynamic teaching is supplemented with eight source-verified RxR train-guide/en-US examples and their paired reviews and single-defect diagnostics. Sources are verified against the official compressed JSONL SHA-256 and the exact original record bytes. Curated subtasks and authored corruptions are not official route/subtask ground truth. The offline builder checks quoted evidence and active Generator and Reviewer protocols; it does not certify semantic optimality or navigation performance.

Generator Dynamic remains 2–4. Reviewer uses the corresponding 2–4 pairs and 0–2 diagnostics. The RxR-only relational ranker prioritizes source relations and marginal coverage, not stage-count or verdict quotas. A repeated phrase does not itself choose SPLIT or another traversal. Fixed Core is never replaced. Exact query echoes and duplicate-source Dynamic examples are excluded.

## Workflow

Adapter resolves explicit dataset/language. Host freezes the source, Profile rules, role guidance, retrieval implementation, Core and selected Dynamic material. G0 generates actual English and audits; Renderer freezes a snapshot; R0 independently reviews that snapshot. PASS releases only the reviewed artifact. The existing repair path supplies R0 findings to G1 with the same teaching bundle, then rerenders and performs a fresh R1. Unresolved or technical failures retain the existing exact-source fallback. No post-review text cleaning and no third semantic role are introduced.

The Generator uses supported entry states without mandating redundant entry sentences. G1 edits affected executable text and necessary dependencies only. Reviewer checks reverse source support for added turns, traversal multiplicity, entry, arrival, certainty and maintained relations, and rejects only material defects. PASS is not a prediction of navigation success.

## Implementation and provenance

Shared and role-specific RxR rules remain separate. The selector imports the RxR helpers without reading training assets; it invokes the new ranker and training-library checks only for the RxR Profile. The source registry and retrieval implementation participate in RxR task hashes; R2R does not read them. The teaching builder is an offline maintenance tool and never downloads data during navigation. Dynamic pools retain explicit identity, language, source and pairing validation.

Use isolated checkout/output/cache namespaces for active R2R and RxR runs. Do not hot-edit shared workers. Record actual messages, active schema, source and rendered hashes, model receipt and token usage. Unknown provider context/truncation information must remain unknown, not be fabricated from byte length.

## Validation and release

Run inherited self-contained tests, new RxR calibration/provenance/protocol tests, four-phase R2R message-and-schema comparisons, selection comparisons and interleaved-cache tests. Keep the existing externally dependent release-transaction test limitation visible. Compile generated artifacts and update integrity records only after protected assets have been compared with the frozen base. Shared runtime source hashes necessarily change with an RxR-only dispatch addition; refresh only their approved integrity entries after proving R2R model messages, schemas and selection are unchanged. Record previous and current source fingerprints separately. Never retain an obsolete code hash to claim isolation.

Commit tested artifacts only to the checked-out branch, without force pushing or updating another Profile's model-message snapshots to conceal a regression. Use commit and content hashes for provenance. Project release labels belong in README only. External dependency pins and standard schema identifiers remain technical compatibility facts, not project release labels.

## Navigation verification still required

Stage changes: freeze the old per-task example IDs to test rules first; then test the added lessons at the same example counts; then test relational retrieval. Preserve the 44 recovered tasks as well as baseline successes. Report B1/B2/B3 separately, full denominators, technical fallbacks, SR/SPL/nDTW/NE and paired uncertainty. At least 288/407 successes would exceed the stated baseline by three absolute percentage points; this is a target, not an implementation claim. The development set cannot also serve as an untouched final generalization test.
