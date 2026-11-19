# Controlled evaluation plan

This document defines how to evaluate the current R2R English and RxR en-US dual-Profile system. It is a protocol, not a report of completed semantic or navigation results. CI, fixtures and Renderer smoke tests establish engineering properties only.

## 0. Freeze the complete experimental object

Before collecting any comparison result, record and freeze:

- Git commit and tree SHA, `FILE_HASHES.json`, and `provenance/build_manifest.json`.
- Dataset Profile, exact source files and versions, split roster, `task_key`, source hash, instruction/episode/path identifiers and scene/scan identifier.
- Generator initial/repair and Reviewer prompt hashes; active Runtime Schema hashes; shared and dataset-specific Rules hashes; fixed Core IDs and hashes; Dynamic eligible pools and per-task selected IDs.
- Renderer mode, separator, source prefix/suffix behavior, frozen rendered instruction hash and Snapshot hash.
- Generator and Reviewer model/provider identifiers, actual model receipts, effort, decoding/sampling parameters and request IDs.
- AwareVLN checkpoint, tokenizer and chat-template identifiers, visual input configuration, image IDs/order, truncation state, simulator/environment version, action budget and any random seeds.

A change to any item above creates a new experiment arm. Do not attribute a mixed model, prompt, template, schema, renderer or Actor change to one component.

## 1. Dataset provenance and leakage control

Keep R2R English and RxR en-US as separate experimental strata. Do not pool their instruction records or transfer a selected teaching example across Profiles.

The current template manifests record these source lineages:

- R2R Generator: 35 source records in the val_seen pool, of which 10 are promoted to fixed Core and 25 remain Dynamic-eligible.
- R2R Reviewer: 35 paired and 26 diagnostic source records; 9 promoted source records are excluded from Dynamic, leaving 29 paired and 23 diagnostic Dynamic-eligible records. The ten fixed Reviewer Core cases are independently curated and their `pair_id` is provenance, not a runtime ordering dependency.
- RxR Generator: ten fixed Core cases migrated from the original v1 teaching cases, with source metadata pointing to RxR train guide records; 35 val_seen Dynamic-eligible examples.
- RxR Reviewer: ten fixed Core cases migrated from the original v1 Reviewer teaching cases, with source metadata pointing to RxR train guide records; 35 paired and 29 diagnostic Dynamic-eligible examples.

These are curated teaching cases, not official subtask labels, human navigation ground truth, or trajectory-verified judgments. Do not evaluate on the same instructions used to build the templates. Before choosing a held-out roster, compare template source records with evaluation records using all available identifiers: split, instruction/record ID, episode ID, path/trajectory ID, scene/scan ID and language. A scan-level overlap check is mandatory when the claim is unseen-environment generalization.

The official R2R task documentation distinguishes val_seen environments from unseen buildings; the RxR dataset publishes train, val_seen, val_unseen and test_standard splits and identifies records by split, instruction_id, path_id, scan and language. Val_seen is not an unseen-environment test. Verify the exact local dataset release and its metadata rather than inferring a split from a filename or record count. References: [R2R task data documentation](https://github.com/xjli/r2r_vln/blob/master/tasks/R2R/README.md), [RxR dataset repository](https://github.com/google-research-datasets/RxR), [RxR split description](https://ai.google.com/research/rxr/explore).

Freeze the full task roster before any model call. Do not select per-episode winners, remove failed episodes, or change the denominator after seeing outcomes.

## 2. Generator semantic quality

Run G0 on a frozen development roster with the exact same model and effort for all compared arms. Review outputs without navigation scores or knowledge of the arm identity.

Annotate at the source-requirement and episode levels:

- Source coverage: every commanded action, target, ordinal/count origin, direction/reference frame, condition, prohibition, intermediate stop and terminal directive is preserved.
- Unsupported additions or strengthened events: observation→goal, approach→arrival, pass→entry, stage boundary→STOP, inferred distance/posture, or guessed referent.
- Stage completeness: executable Entry, Target, Process, Ending and Conditions are present in natural-language stage text, not only in audit metadata.
- Boundary correctness: source-supported completion event, distinct next objective, supported next entry and actual local-focus benefit.
- Handoff correctness: previous stage's actual exit establishes the next stage's first unperformed action without inventing an intermediate stop.
- Output validity: active Schema, exact source quotes, candidate quote ownership, stage indices and adjacent handoff coverage.

Use at least two independent annotators for the frozen semantic sample and adjudicate disagreements before computing the reference labels. Report per-requirement coverage, false additions, split/keep confusion, stage-level defect rate and confidence intervals. A raw split count or shorter output is not a quality metric.

## 3. Reviewer diagnostic value

Run R0 on the same frozen Source/Candidate/rendered snapshots, with arm order blinded. Measure defect-level precision/recall, false positives, missed defects, exact source/candidate quote validity, affected-stage accuracy, execution-consequence quality and repair locality. Report results separately for `source_fidelity`, `closure_handoff` and `segmentation_adequacy`.

Do not optimize for PASS rate, number of findings, verbosity or agreement with a teaching-case verdict. Reviewer Core and Dynamic examples are calibration material only; each current verdict must be supported by the current Source and Candidate.

R1 is a new Reviewer session, but it is not a context-free review: the Host intentionally supplies the frozen R0 Review, old Candidate and old rendered instruction so R1 can disposition every previous blocker. R1 also receives the new Candidate and exact new rendered text. It does not receive the G1 response as evidence. Evaluate whether R1 correctly marks each old finding resolved/partially_resolved/unresolved and detects new defects in the complete new Candidate.

## 4. Closed-loop repair value

Evaluate the actual G0→R0→G1→R1 protocol. G1 must return a complete Candidate and one explicit response per R0 Finding; it may accept, partially accept, reject or mark unresolved when the evidence requires it. R1 must independently verify the new Candidate and every old blocking finding.

Include both ordinary R0=REVISE repairs and the supported R0=UNRESOLVED path: an active G0 Candidate may enter G1 for a bounded reassessment of the source limitation; an inactive G0 `needs_review` candidate confirmed unresolved falls back to exact Source. Track repair acceptance, overcorrection, regressions in previously covered requirements, unresolved findings, R1 rejection and exact-source fallback. The target is net defect reduction without breaking protected requirements, not the number of accepted suggestions.

## 5. Renderer and native-request ablations

Freeze one semantic Candidate and one reviewer-approved snapshot before testing format variants. Compare LF and SPACE separators as separate registered arms; preserve all stage text, source prefix/suffix and the same semantic candidate. Each rendered variant has a different snapshot/hash and must be reviewed as its own exact string. A Reviewer receipt for one rendered hash cannot approve another.

In the existing AwareVLN Actor, capture the complete native request only after the full text and visual inputs have been assembled. Use `host.run.receipt_for_navigation()` to bind the released instruction hash to the observed instruction, full prompt bytes, actual input token IDs, tokenizer ID, chat-template ID, image IDs in order, truncation flag and request ID. The helper computes hashes and checks the supplied values; the integration caller remains responsible for passing the actual request bytes/IDs and not reconstructed or per-stage tokenization.

## 6. Paired navigation evaluation

Only after semantic and closed-loop quality are measured should the system be evaluated in AwareVLN. Keep the Actor checkpoint, image flow, Reason/Act, STOP, last_reasoning, action space, simulator, budget, model and all other runtime settings fixed. Use the exact same frozen task roster and paired environment seeds where the simulator supports them.

For every task, retain baseline and candidate result plus Host disposition. Keep accepted Candidate, accepted source-exact, semantic fallback, unresolved fallback, input failure and technical failure in the frozen denominator. Do not silently drop fallback, timeout, malformed receipt or unresolved rows.

Report at least:

- SR, SPL, nDTW and NE using the evaluator's exact definitions and units.
- Path length, navigation steps/actions, model calls and input/output token costs when available.
- Recoveries (baseline fail→candidate success), regressions (baseline success→candidate fail), paired SR difference and common-success path-efficiency difference.
- Disposition counts, complete denominator and confidence intervals.

Use `evaluation/paired.py` with the frozen expected-key roster. It rejects duplicate/missing task keys and reports recoveries, regressions, SR delta, available paired metrics, common-success path-length difference and dispositions. Use paired bootstrap intervals; when several tasks share a scan, also report a scan-clustered sensitivity analysis. Do not infer navigation improvement from a small set of successful examples.

## 7. Held-out validation and release decision

After all wording, Core curation and retrieval choices are frozen on development data, run a scene/path-disjoint held-out evaluation that was not used to select prompts or templates. Report the exact split, roster hash, overlap audit, model/Actor pins, all denominators, paired metrics and confidence intervals. Pre-register acceptable semantic and navigation thresholds before opening held-out results.

A release decision requires both engineering integrity and the pre-registered evaluation criteria. Passing `verify_package.py`, unit tests, the 24-case Renderer smoke and the offline demo proves only their respective package, protocol, formatting and fixture contracts. It does not establish real-model semantic accuracy, tokenizer invariance, or SR/SPL/nDTW improvement.
