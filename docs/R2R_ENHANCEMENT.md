# R2R English specialization

## Scope

This implementation refines only `r2r-en`. It preserves the shared semantic contract, generic Generator/Reviewer prompts, Runtime Schemas, Renderer, Actor interface, STOP behavior and RxR assets. The existing bounded G0 → R0 → optional G1 → R1 workflow remains the release authority. This document makes no navigation-performance claim.

## Rule ownership and execution

`shared/dataset_rules/r2r_en.md` defines entity roles, completion versus useful grouping, completion binding, minimum sufficient handoff, spatial ownership and purpose-limited editing. `generator/dataset_rules/r2r_en.md` applies these definitions in source-first candidate construction. `reviewer/dataset_rules/r2r_en.md` independently reviews the actual candidate, accounts for all material defects and reconciles every audit field. The fragment registry is Host-side retrieval evidence, never a navigation plan or a source fact.

The Generator must not convert attributes into actions, mistake transit regions for independent visits, split endpoint refinement into a second movement, replay completed movement, or invent exact poses. It still preserves useful boundaries between completed and distinct objectives. Literal-wording preference is not an additional Reviewer rejection criterion: a faithful executable paraphrase may pass. Reviewer findings require the existing material-evidence threshold.

## Fixed and complementary teaching

Each role retains ten ordered fixed Core cases. The eligible pools are 25 Generator examples, 29 paired Reviewer examples and 26 diagnostics. Generator selects four base Dynamic cases and adds a fifth or sixth only for a source-grounded relationship not already covered by Core and the selected cases. The Reviewer pair prefix is mapped from that exact frozen Generator list. Two diagnostics are selected; a third is permitted only for complementary uncovered evidence. Explicit configured counts are restricted to integers four through six. Offline `all` remains separate from adaptive production selection.

Core overlap is a soft redundancy penalty, not a hard exclusion. A more specific example can be useful even when a broad Core topic matches. Selection uses source-only relationship cues, temporal relations, lexical relevance and stable tie-breaking. Instruction length does not trigger extra cases or a single-stage preference. No group labels, scores, GT or trajectories are used.

`host/r2r_retrieval.py` owns the complementary algorithm and imports neither compiler nor runtime. The selector provides validated libraries, authored Core and extraction callbacks. Host resolves one R2R bundle per task; Generator and Reviewer do not independently choose incompatible base examples. Evidence logs retain matched source spans, new coverage, Core overlap and optional-case rationale. Request-specific source spans are not copied into teaching instructions as facts.

## Teaching changes

- DIAG-07: preserve covered ordinal selection; attach the omitted STOP finding to its actual source requirement; represent the missing ending without fabricating evidence.
- DIAG-19: account for both the missing hypothetical facing frame and missing terminal STOP; align coverage, dimensions, layers, stage checks and repairs.
- G09 and its real source/review counterparts: start the new forward approach by inheriting the completed descent and right turn. This is anchor minimization, not a rule forbidding the word bottom.
- Existing doorway, hallway-end and transit demonstrations: clarify applicability and counter-boundaries without changing their original source strings.
- DIAG-27: an authored candidate wrongly converts an open-door attribute into an opening command.
- DIAG-28: an authored candidate over-fragments a transit route and its same endpoint placement.
- DIAG-29: an authored candidate repeats an ascent instead of binding its completion condition to the original movement.

New diagnostic sources are exact existing val_seen teaching records, with lineage retained. Their corruptions are authored illustrations, not claimed model outputs or trajectory truth. No inspected val_unseen evaluation instruction has been inserted into the Runtime library.

## Prompt projection and freezing

Assembly remains common role prompt → common contract → R2R shared guidance → matching role guidance → role-specific checklist/repair material → fixed Core → Dynamic/diagnostics → active schema → independent task message. R2R teaching cards project the decisive transfer boundary and counter-boundary even in compact Dynamic form. Source JSON, executable candidate, evidence, handoffs and projected cards must stay consistent.

G0/G1 reuse the same Generator bundle; R0/R1 reuse the same Reviewer bundle. The R2R retrieval implementation is included in prompt-component hashes. Source identity, rule hashes, template hashes, actual prompt hashes and frozen renderer snapshots remain separate. Only the exact reviewed instruction is released. No post-review text restoration, online goal switch or memory mechanism is added.

## Isolation and reproducibility

Tests retain the existing frozen RxR compiled hashes and add 28 source/role/phase snapshots captured before the change. They exercise RxR → R2R → RxR calls in one process and compare ordered IDs, exact prompt hashes and schemas. Shared Python source hashes may change for R2R-only branches; RxR model-visible bytes and all protected assets must not.

Authored teaching schemas, runtime protocol checks, exact quotes, pair identities and source lineage are all validated. Package and R2R profile integrity manifests are regenerated only for reviewed changes. The source audit workflow remains available. CI validates before persisting generated artifacts, and a normal fast-forward push rejects concurrent branch changes.

## Validation commands and limits

Run `python -B verify_package.py`, `python -B -m host.compile`, the existing profile/closed-loop tests, `python -B -m unittest discover -s tests -p test_r2r_complementary.py -v`, `python -B -m evaluation.smoke24`, and `python -B -m examples.demo`.

The existing regression workflow excludes one historical external release-transaction fixture that is not shipped in this repository. It must remain disclosed; the fixture is not replaced by a claimed pass. The new tests verify mechanical contracts and authored evidence consistency, not model semantic accuracy. Real provider transmission and paired navigation results still require the user's evaluation environment. Report technical fallback and the full task denominator; do not infer navigation improvement from CI or Reviewer PASS.

Project release naming belongs only in README. Stable historical schema identifiers and external dependency revisions are compatibility references, not new project release markers; changing them would alter frozen shared/RxR contracts.
