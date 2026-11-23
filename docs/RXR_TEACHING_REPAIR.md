# RxR teaching repair and evidence contract

## Scope

The source anchor is commit `da277a0f9a6ee7d8eebb78dafa852e469cd1a50e`. Work is limited to RxR authoring, teaching data and dataset-specific guidance. Common semantics, runtime schemas, Adapter, Renderer, Host state machine and R2R model inputs remain protected. A structural test is not a natural-language entailment certificate or a navigation result.

The active library remains 53 Generator and 90 Reviewer templates: ten fixed Core per role; 35 original plus eight training Generator examples; their 43 paired reviews; 29 original plus eight training diagnostics. Per-request counts remain two to four Generator examples, the matching reviewer pairs, and zero to two additional diagnostics. No new evaluation case is injected. Retrieval source strings, tags, identities and ordering remain frozen in this repair stage; scoring is unchanged.

## Repair stages and actual artifacts

Teaching-only corrections were materialized and verified before changing the three RxR guidance files. This separates the teaching intervention from rule clarification in Git history. `provenance/rxr_teaching_changes.json` records every old-library template, source digest, before/after digest, whether executable candidate text changed and each JSON field difference. The expected outputs are built from immutable Git objects rather than from mutable previously repaired inputs.

`tools/rxr_positive_repairs.py` contains explicit case-level author decisions. Core completion repairs use the actual second-door arrival, bathroom entry, and table-side proximity. The open-area entry remains an explicit completion without added STOP. Dynamic repairs distinguish complete action evidence from related object descriptions, align repeated turns to their actual occurrences, correct local handoff references, and distinguish the noun news stand from a required halt. The first repair stage changed positive routes 019, 023 and 035: remove an unnecessary table-arrival anchor, restore the approximate endpoint, and retain the narrated door state change. Their paired candidates and affected evidence are kept identical.

The subsequent `tools/rxr_teaching_focus.py` calibration preserves every Core source and executable route while making all ten lessons per role case-specific and replacing the 33 normal Core coverage rows with reviewed event-local evidence. Cases 002 and 020 receive only source-preserving wording refinements: remove source-analysis commentary while retaining contradictory auxiliary-window wording, and preserve expected viewing/standing states without adding new looking or continue-until movements. Dependent diagnostics 27 and 29 are rebuilt from the current parents. See `docs/RXR_TEACHING_FOCUS.md` for recommendation decisions, exact scope and remaining interpretive limits.

`tools/rxr_diagnostic_repairs.py` rebuilds declared source-based contrasts and parent-based single-defect contrasts. A source-identical candidate is not falsely called an omission. Aesthetic negation and emphatic right are not labeled route prohibitions or rightward directions. Unchanged requirements remain covered; only actual dependencies propagate a local fault to another stage or handoff. A grouping-only diagnostic may preserve every word yet still demonstrate an evidenced missed useful boundary; it must not allege fabricated source loss.

`tools/rxr_review_contract.py` supplies numeric local coverage identities and exact remaining evidence for omission examples. It does not infer semantics online or loosen the runtime schema. `tools/rxr_training_review.py` provides authored per-stage stop scopes for the eight training cases and updates actual explanations together with changed quotes and inherited state. `tools/build_rxr_teaching.py --verify-upstream` verifies the existing official training-source archive before reproducing those examples.

## Authoring and rebuilding

Use a full-history checkout with the frozen source object available. Install the existing requirements, then run:

```bash
python -B tools/build_rxr_reviewed.py --inspect
python -B tools/build_rxr_reviewed.py --write
python -B tools/build_rxr_reviewed.py --check
python -B tools/build_rxr_teaching.py --verify-upstream
python -B -m host.compile
python -B tools/check_rxr_selection_isolation.py
```

The inspector computes and validates the exact same outputs as the writer, without changing files. Before writing anything, the writer checks all current artifacts against either the frozen source or their prior recorded generated digest. Independently changed files are refused rather than overwritten. Check mode verifies the committed artifacts and ledger against authored specifications. A second rebuild must reproduce identical bytes. It must not rewrite runtime source or tests.

The source/archive validation proves provenance and exact text binding, not that every authored split is uniquely correct. All official, adapted and synthetic source declarations remain distinct. Source records, coverage IDs and trace ledgers are not extra navigation instructions.

## Semantic checks retained in the existing contract

Completion evidence describes the planned action completion or required state sufficient for the actual successor. A prohibition, target attribute or shared noun alone does not prove arrival/entry. Explicit seeing, bounded action and facing conditions remain valid when that is what the source requires. Event alignment includes occurrence identity, not only substring presence. The route can be legitimately reordered by explicit temporal relations; no monotonic text-alignment rule is imposed.

Ending kind and stop scope are separate. Entering a room may finish a stage without STOP. Explicit intermediate stops remain required. A required final stationary placement is distinguished from an intermediate expected-state narration. Local word function determines whether stand, right, once and or express an object, emphasis, repetition, approximation or actual navigation meaning.

The Reviewer must support the complete source requirement with precise actual candidate evidence. A valid quoted noun alone cannot cover a movement. For a bad candidate, source-required meaning and the candidate's current meaning must be explicitly distinguished. A blocking finding requires a material defect, not a template label, missing connective, stylistic preference or navigation score. One defect does not make unrelated coverage or all handoffs invalid.

The three current guidance files preserve existing global understanding, late-description binding, legitimate implicit completion, condition handling, return history and valid alternative grouping. They add no output fields, no extra role and no extra semantic repair iteration.

## Actual teaching projection and runtime path

Fixed Core is fully projected. The existing first dynamic example has detailed evidence; later dynamic and diagnostic cards remain compact. Tests inspect the real `teaching` wrapper plus `applicable_lesson` and `avoid`, not assumed fields. Compact diagnostics retain the actual source/candidate, verdict, complete finding and local repair explanation. The full expected review is checked against the active response schema before either projection. R2R projection is unchanged.

Case-specific Core lessons use the existing Generator `case_rationale` and Reviewer `case_specific_focus` precedence. No shared compiler priority is reordered. Local evidence retains enough context for compound constraints; whole-stage evidence is not categorically forbidden when the stage is itself the relevant requirement. Prompt sizes are recorded in bytes, not presented as tokenizer counts or proof of no transport truncation.

Runtime remains Adapter profile selection, task-scoped frozen rules/examples, G0, Renderer snapshot, R0, optional bounded G1, fresh Renderer snapshot and independent R1, then exact reviewed snapshot release or the existing source fallback. The Reviewer does not receive Generator self-audit as proof. No source download, author script or test score is called on this online path.

## Isolation and validation

`tools/check_r2r_isolation.py` compares protected common/R2R bytes and R2R selection plus all four compiled phases against the frozen source in independent processes. `tools/check_rxr_selection_isolation.py` separately compares RxR source identities, retrieval fields, order and actual selected IDs across every active source text, constructed controls, default counts and explicit counts. Its finite grid is not a proof about all possible instructions; unchanged source-based retrieval inputs and implementation provide the structural boundary.

All 143 active templates are checked through the unweakened runtime protocols and both teaching projections. Case-specific assertions cover known completion errors, repeated-event alignment, meaningful coverage, stop scope, retained qualifiers/state changes and real single-defect transformations. CI also exercises the existing four-phase workflow, model-receipt handling, renderer cases, deterministic regeneration and package integrity. The committed RxR prompt pin fixture is explicitly reviewed; CI cannot refresh expected test values to make itself pass.

`provenance/rxr_validation.json` reports actual engineering execution. The external release-transaction fixture requires a companion file outside this repository and is recorded separately when unavailable. No completed language-model blind study or navigation experiment is claimed. The original source branch is never updated by this work; automated artifact commits use a guarded push to the current target ref only.

## Remaining uncertainty and experiment boundary

Case 020 now retains the stated foot-of-bed result without authorizing another traversal, and case 002 retains the contradictory auxiliary-window description without source-analysis instructions in Actor text. These changes avoid unsupported additions; they do not resolve the underlying environment geometry or prove how every model interprets the original narration. Broad natural-language coverage remains authored and requires independent review; passing structural tests does not certify the full library as a semantic oracle.

Do not add the proposed three source groups or alter retrieval weights in the teaching/clarification comparison. Those are later, separate candidate experiments if the repaired library still lacks specific contrasts. Any new val-seen guide source requires official identity/text checks, overlap screening, paired candidate equality and an actually material single-defect diagnostic. Evaluation instructions and trajectory outcomes remain offline only.

For effect attribution, freeze actual Generator, paired Reviewer and diagnostic IDs and order, model configuration, input formatting and navigation environment. Compare original teaching, repaired teaching, clarified rules and their combination without per-episode outcome cherry-picking. Protect the existing successes as well as regressions, and retain all repeated-run outcomes. Used val-unseen evidence is development/regression material, not a fresh generalization set.

## Naming and preservation

New functionality uses semantic file names and existing template identities, without new release labels outside README. Historical schema identifiers, source records and protected compatibility paths are not rewritten for cosmetic cleanup. The validation report lists inherited label occurrences honestly. Hashes and commit anchors identify actual content and are not prompt version labels.
