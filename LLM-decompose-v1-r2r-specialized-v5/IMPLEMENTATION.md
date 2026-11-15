# final-best-v1 implementation rationale

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
