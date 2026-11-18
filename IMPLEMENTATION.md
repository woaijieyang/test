# LLM-decompose-v6 implementation rationale

## What was preserved

The semantic backbone remains the RxR v1.3 line: read the whole instruction; jointly decide boundaries and context assembly; preserve all route dependencies; give each stage a supported entry/process/target/completion/conditions; keep stage boundaries separate from physical STOP; allow one coherent stage to contain multiple actions; allow source-supported edits when they improve executability. The package does not replace this with verb-by-verb rules or a small rule engine.

## What was tightened after the full audit

1. **Positive segmentation was restored.** The generator must test both boundary legality and segmentation benefit. It may not use a generic “could remain one segment” as a reason to bury a clearly distinct objective. A short route can have multiple local goals; a coupled approach-turn-enter-stop can remain one stage.
2. **Generator and Reviewer now share one contract.** The same five stage properties, five dependency families, S1–S4 evidence levels and C01–C12 checks are compiled into both prompts. Reviewer-only standards cannot drift from generator standards.
3. **Three quality dimensions are separated.** Fidelity, closure/handoff and segmentation adequacy are judged independently. Under-segmentation is not falsely called a route-semantic contradiction; it still matters when a supported next objective is buried.
4. **Handoff is explicit.** Each adjacent pair is audited for previous exit, next required entry, shared referent, completion evidence and a supported/issue/source-limited status. Stage audit notes cannot secretly add missing commands to the English.
5. **Completion semantics are more precise.** Explicit event, bounded action, linked trigger/refinement and terminal goal directive are distinguished. A final “walk toward X” may remain the final objective when no later event depends on arrival; it never licenses a claim of reaching, entering or stopping at X. An intermediate approach must be bound to the later trigger or merged.
6. **Reviewer findings must be actionable and factual.** Every material finding needs source evidence, candidate evidence, a concrete execution/focus consequence and a local nonbinding repair option. C10 findings must name the actual missed boundary and distinct objective, not simply recommend more segments.
7. **Renderer is a formatting/provenance component, not a semantic gatekeeper.** It freezes the exact candidate reviewed, preserves source prefix/suffix and reliably copied/moved whitespace, uses LF for newly created stage separators, and records ambiguous alignment instead of guessing. It never rewrites correct text after review.
8. **The adapter is explicit about scope.** R2R English and RxR en-US are the only supported profiles. The loader accepts their observed source-field shapes and rejects conflicting fields/languages. Dataset-specific counts are descriptive metadata, not different whitespace normalization rules.

## What is deliberately not added

No new primary reviewer, trained model, online goal-switch hook, graph/map memory, event memory, new STOP handler, completion detector, Reason/Act change, image pipeline change, budget change or `last_reasoning` reset. The current experiment supplies all ordered stages together to the existing instruction field. This package only prepares and validates the language plan and its exact rendering.

## Evidence and limitations

The uploaded source analysis covers 1,839 R2R evaluation instructions and 1,223 RxR en-US evaluation instructions, alongside the supplied train/eval instruction corpora and episode-level audit records. These counts describe the uploaded files only. No new model calls, navigation replay, tokenizer capture or frame-level causal analysis were performed while assembling final-best-v1. The package therefore makes no new navigation-performance claim.

The current tests cover schema validation, source identity, renderer provenance, source-exact fallback, bounded two-role workflow and smoke cases. Passing them is not proof of language correctness, tokenizer invariance or navigation improvement. A new fixed-model, blind-review and held-out navigation evaluation is still required.


## v6 RxR en-US extension and preservation boundary

The implementation baseline is the exact `LLM-decompose-v5` branch commit `c2243fdd3f8c3ae08f1ad6837e14b17a17e228f3`. The extension does not replace the v5 common prompt, semantic contract, active runtime schemas, Stage Audit/Handoff fields, C01–C12 checklist, L0–L6 review, Adapter, Renderer, G0–R0–G1–R1 workflow, or the existing AwareVLN actor boundary.

Only the `rxr-en-us` Adapter profile loads:
- one shared semantic rule file defining RxR long-instruction event reconstruction, action/observation/target/reference distinctions, late target-description binding, temporal scope, global coreference, route history, spatial reference frames, ordinal/count origins, endpoint refinement, conditional branches, and executable handoff requirements;
- separate Generator and Reviewer execution guidance, which share the same semantic definitions but use role-specific reasoning and audit order;
- ten fixed v5-format Generator teaching templates migrated from the original v1 G01–G10 cases;
- ten independent fixed v5-format Reviewer teaching templates migrated from the original v1 R01–R10 cases.

The fixed core is injected unconditionally for normal runtime calls and remains in stable order. It is not passed through retrieval, cannot be replaced by dynamic examples, and is reused unchanged in G0/G1 and R0/R1. Original v1-format files remain in the legacy provenance directories and are not runtime inputs. The migrated core JSON keeps per-case lineage; not all ten cases are raw RxR corpus records, and they must not be described as official human annotations or navigation ground truth.

RxR dynamic retrieval is deliberately complementary: 2–4 Generator examples from the 35-case val_seen pool; the corresponding 2–4 paired Reviewer examples; and 0–2 relevant Reviewer Diagnostics from the 29-case pool. R2R remains on its v5 dynamic pools and 6–8 Generator / paired Reviewer plus 2–4 Diagnostics policy. R2R receives no RxR rules or fixed core. The selector enforces the RxR range even when a caller supplies an explicit count.

At task start Host freezes the profile-specific rule-file digest and each role's complete fixed-core plus selected-dynamic template digest. G1 and R1 use the same frozen selections; every request recomputes and compares the bundle metadata before transport. Fixed-core loading and identity/pairing validation occur before the first model call. A missing, corrupted, reordered or mismatched core is a technical failure and returns the exact original source without entering model transport.

## Engineering validation status

GitHub Actions on `LLM-decompose-v6` has passed the profile compiler build, fixed-core and pairing tests, dynamic retrieval tests, teaching-schema and Generator protocol checks, runtime-contract v2 tests, prompt injection tests, role repair tests, adapter/workflow/targeted-feedback tests, and reviewer recovery/journal tests. These are offline engineering tests. No real-model semantic accuracy, navigation rollout, SR/SPL/nDTW improvement, or tokenizer invariance is claimed.
