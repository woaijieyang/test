# RxR role-local rule organization and conversion record

## Scope and authorities

This change reorganizes the existing RxR role guidance; it is not a new decomposition policy, a navigation result, or a new runtime interface. The source baseline is commit `081db4b9ea0712ff720c137fe96c240c26f7b15c`. The earlier role prompts inspected for capability continuity are pinned at `739c00f1eeeb9a96234a26d37445dea049d5ec58`. Commit identifiers are provenance, not labels to insert into model instructions.

`shared/semantic_contract.md` remains the cross-dataset authority. `shared/dataset_rules/rxr_en_us.md` remains the separately loaded framework shared by the two RxR roles. Neither file is rewritten or placed inside P0/P1/P2. The R2R rules, all teaching examples, schemas, Compiler, Selector, Renderer, transport and bounded repair workflow are unchanged.

Only `generator/dataset_rules/rxr_en_us.md` and `reviewer/dataset_rules/rxr_en_us.md` change model-visible policy text. P0 identifies the role and responsibility. P1 organizes its existing general workflow, five-element framework, preconditions, handoffs and output/recheck responsibilities. P2 organizes existing local calibration. The hierarchy is not an error-severity scale, new JSON fields, three additional calls, or a fixed quota of rules. The two roles do not have matching procedures or a required one-to-one set of local rules.

## Historical comparison: capability versus obsolete interface

The historical prompts explicitly identify an instruction-understanding Generator and an independent Reviewer, require complete-source reading before cuts, use Entry/Target/Process/Ending/Conditions, and check the preceding completion against the successor's first unexecuted action. They preserve cross-sentence target descriptions, temporal dependencies, entity identity, real return traversal, bounded/refined endings, conditions and minimal edits. These abilities are already present in the active common prompts and RxR framework. They are not assumed lost merely because they are less visible in the short role-specific file.

This conversion makes role identity and the framework visible at the appropriate role-local level while retaining the current detailed requirements. It does not restore historical `current_only` or `current_and_history` experiment modes, a main-conversation personal verdict with only advisory delegated review, historical response shapes, or the historical `reject` label. Those conflict with the active single assembled navigation instruction, explicit Reviewer gate and current schemas. Historical semantic competence is the comparison target; historical runtime authority and fields are not imported.

## What moved and what was retained

Generator P0 explicitly identifies the sole candidate author, source-only authority, complete-route objective and active initial/repair output contracts. P1 retains all nine existing work-order items verbatim. Five-element judgments and a precondition-to-handoff section apply the unchanged common definitions. Existing wording fidelity, no ungrounded action, whole-route checks and repair/needs-review paragraphs remain in P1. Existing calibration about repetition/return, scoped correction, conditional observation, bounded terminal refinement, lexical function and approximation/state changes is organized under P2. A valid single stage and supported multiple objectives remain general requirements, not optional scene rules.

Reviewer P0 identifies independent acceptance, evidence and non-authorship. P1 contains one item named `Ordered review framework: L0–L6`; all seven existing L paragraphs are retained verbatim under that item. The surrounding P1 items explicitly describe inputs, the five elements, prerequisite/handoff acceptance, grounded findings, the unchanged gate and full recheck. Its existing false-positive paragraph is organized by its own evidence risks under P2, not copied from the Generator's scene categories.

Every substantive sentence in the two previous guidance files is retained verbatim and mapped to its destination. Headings and connective/application text are added; no previous condition, prohibition or exception is silently deleted. `provenance/rxr_role_conversion.json` records the immutable source, original Git blob IDs, reviewed rule hashes, source line and sentence ordinal, target section, historical decisions and baseline full-prompt fingerprints. The map has no runtime function and is not loaded as teaching data. Its observed entry count is an audit result, not a rule-count requirement.

The role files grow because the user-requested role, five-element and handoff entry points are explicit. This is not described as compression or measured token savings. Additional text applies current common requirements; it does not authorize a new route, fixed stage count, mandatory anchor, extra STOP or stronger default source-copy policy. Further deduplication or behavioral policy changes require a separate reviewed change after this conversion baseline.

## Data flow and interface continuity

The existing adapter resolves the profile. The existing Compiler loads the common contract, RxR shared framework, the correct role guidance, schemas and frozen teaching selection. P2 is used during the applicable P1 task, not as an extra API phase or as permission to skip ordinary checks. Initial generation, rendering, review, optional bounded repair, re-rendering and recheck remain unchanged. G0/G1 share the frozen Generator guidance; R0/R1 share the Reviewer system contract, while the new candidate and old findings are carried by the existing recheck payload.

Host checks output structure, exact quotation/index and artifact binding. It does not prove semantic entailment. Renderer assembles and freezes actual candidate text; it does not choose semantic boundaries or post-edit a passed instruction. Reviewer judges the actual frozen text, not an audit summary. Generator remains the only author of a revised candidate. Source ambiguity, candidate-created gaps and technical failures continue through their existing distinct paths.

No dataset split, episode success label, ground truth, trajectory or evaluator threshold is added to model rules. No source instance is promoted into a new teaching template, and no template selection count or ordering is changed.

## Template and preservation checks

The full inherited checks still validate Core, dynamic pairs, diagnostics, authored builders, source registry, actual teaching projection, citations, snapshots and closed-loop behavior. The conversion adds a byte comparison of every teaching source and protected runtime/common asset against the fixed baseline. Exact restoration of the old role block in each actual compiled prompt must reproduce the old complete-prompt SHA. This tests that unrelated shared text, examples, schemas and rendering have not changed along with the role conversion.

Clause preservation proves retention, not natural-language correctness. Five-element and handoff review protects the already established distinctions: a prohibition does not prove arrival; a door attribute does not prove entry; a supported later refinement may complete the same event; no STOP does not invalidate entry; actual intermediate stopping and real return history remain required. No new interpretation is introduced to make a template fit a new heading. Existing disputed semantics are not certified by relabeling their section.

## Validation and expectation handling

`tests/test_rxr_role_hierarchy.py` is read-only. It verifies complete source-clause mapping, exact new rule hashes, role-local layer order, all L layers inside the P1 framework, explicit five-element and handoff responsibilities, unchanged protected/teaching sources, four-stage role-block isolation and historical reference identity. It emits measured hashes and byte lengths; it never writes expectations.

Inherited prompt snapshot expectations must be updated explicitly only after the new role blocks are reviewed and normalization reproduces the old hashes. The snapshot's query, selection IDs and schema hashes remain frozen. CI must not rewrite source, tests or expected hashes to make an arbitrary output pass. The final validation record is the evidence for which tests actually ran; an absent external release companion remains separately reported, not counted as passing.

No LLM blind review or navigation experiment is executed by this conversion. Engineering checks and authored semantic review do not prove zero behavioral drift or a success-rate gain. The result is a traceable structural candidate; fixed-configuration paired navigation remains necessary before claiming performance improvement. Original branches are not modified, and concurrent target commits must not be overwritten.
