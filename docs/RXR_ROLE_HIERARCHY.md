# RxR role-local rule organization and conversion record

## Scope and authorities

This change reorganizes the existing RxR role guidance; it is not a new decomposition policy, a navigation result, or a new runtime interface. The source baseline is commit `081db4b9ea0712ff720c137fe96c240c26f7b15c`. The earlier role prompts inspected for capability continuity are pinned at `739c00f1eeeb9a96234a26d37445dea049d5ec58`. Commit identifiers are provenance, not labels to insert into model instructions.

`shared/semantic_contract.md` remains the cross-dataset authority. `shared/dataset_rules/rxr_en_us.md` remains the separately loaded framework shared by the two RxR roles. Neither file is rewritten or placed inside P0/P1/P2. The R2R rules, all teaching examples, schemas, Compiler, Selector, Renderer, transport and bounded repair workflow are unchanged.

Only `generator/dataset_rules/rxr_en_us.md` and `reviewer/dataset_rules/rxr_en_us.md` change model-visible policy text. P0 identifies the role and responsibility. P1 organizes its existing general workflow, five-element framework, preconditions, handoffs and output/recheck responsibilities. P2 organizes existing local calibration. The hierarchy is not an error-severity scale, new JSON fields, three additional calls, or a fixed quota of rules. The two roles do not have matching procedures or a required one-to-one set of local rules.

## Historical comparison: capability versus obsolete interface

The historical Generator prompt begins by requiring one complete instruction to be transformed into coherent English stages, with complete-source reading before edits. Its Input and authority, Choose supported stages, Conditions and time, and Context assembly and handoff sections explicitly cover source-only facts, complete processes, supported completion, target descriptions, temporal dependencies, counts, reference frames and inherited context. The historical Reviewer reads source requirements first, independently compares the candidate in both directions, and distinguishes substantive defects from harmless wording and valid alternative segmentations.

Those semantic abilities are already represented in the active common prompts and RxR framework. They are not classified as lost just because the shorter role-specific file relies on a shared definition. This conversion makes role identity, the current five-element framework and prerequisite-to-handoff obligations visible in the correct role-local layer. It retains every substantive clause of the immediately preceding role files rather than importing old output fields.

| Historical element | Evidence in the inspected original | Current treatment |
|---|---|---|
| Source-only author, complete-source reading and stage construction | Generator opening, Input and authority, Choose supported stages | Explicit Generator P0 responsibility and retained P1 work order |
| Complete process, supported completion, constraints and carryover | Generator stage/context sections and Reviewer Stage audit | Current Entry/Target/Process/Ending/Conditions are applied in P1; historical fields are not substituted |
| Temporal reconstruction, later identification, bounded endings and genuine revisits | Generator Conditions and time / Context assembly and handoff; Reviewer What to check | Existing shared interpretations and role-local judgments retained |
| Independent source-first review and non-authorship | Reviewer opening and Codex primary ownership | Explicit Reviewer P0, complete P1 audit framework and unchanged gate |
| `ok` / `needs_review`, and `pass` / `revise` / `unresolved` | Generator Output semantics and Reviewer Verdict | Already present historically; no `reject`-label migration is claimed |
| Three alternative runtime context conditions | Both historical prompts | Not restored; the active single assembled instruction and supported inheritance contract remain unchanged |
| The primary conversation must personally review, not another reviewer child | Reviewer Codex primary ownership | Not restored as a deployment restriction; current independent Reviewer/Host responsibility remains authoritative |
| Historical stage_checks and non-null completion_condition pass requirement | Reviewer Stage audit | Not restored as a schema or acceptance override; current audit fields, ending types and permitted final directive remain authoritative |

The two historical source blobs are recorded in `provenance/rxr_role_conversion.json` and checked directly against Git history. This is a content comparison, not evidence that historical metrics were caused by one wording choice. No model trial in this change measures the causal effect of a particular instruction.

## What moved and what was retained

Generator P0 explicitly identifies the sole candidate author, source-only authority, complete-route objective and active initial/repair output contracts. P1 retains all nine existing work-order items verbatim. Five-element judgments and a precondition-to-handoff section apply the unchanged common definitions. Existing wording fidelity, no ungrounded action, whole-route checks and repair/needs-review paragraphs remain in P1. Existing calibration about repetition/return, scoped correction, conditional observation, bounded terminal refinement, lexical function and approximation/state changes is organized under P2. A valid single stage and supported multiple objectives remain general requirements, not optional scene rules.

Reviewer P0 identifies independent acceptance, evidence and non-authorship. P1 contains one item named `Ordered review framework: L0–L6`; all seven existing L paragraphs are retained verbatim under that item. Its other P1 items cover inputs, the five elements, prerequisite/handoff acceptance, grounded findings, the unchanged gate and full recheck. The existing false-positive details are organized by their own evidence risks under P2, not copied from the Generator's categories.

Every substantive sentence in the two preceding guidance files is retained verbatim and mapped to its destination. Headings and connective/application text are added; no previous condition, prohibition or exception is silently deleted. The conversion manifest records the source commit and baseline blob, new rule SHA-256 and byte size, original line and sentence ordinal, target section, historical comparison and baseline full-prompt fingerprints. This map is offline provenance, not runtime teaching. Its observed entry count is not a rule-count requirement.

The role files grow because the requested identity, five-element and handoff entry points are explicit. This is not compression or measured token savings. The additional text applies existing common requirements; it does not authorize a new route, mandatory anchor, extra STOP, fixed stage count or stronger default source-copy policy. Further deduplication or behavioral changes require their own reviewed comparison after the conversion baseline.

## Data flow and interface continuity

The existing adapter resolves the profile. The existing Compiler loads the common contract, RxR shared framework, the correct role guidance, schemas and frozen teaching selection. P2 is used during the applicable P1 task, not as an additional API phase or permission to skip ordinary checks. Initial generation, rendering, review, optional bounded repair, re-rendering and recheck remain unchanged. G0/G1 share the frozen Generator guidance; R0/R1 share the Reviewer system contract, while the new candidate and old findings are carried by the existing recheck payload.

Host checks output structure, exact quotation/index and artifact binding. It does not prove semantic entailment. Renderer assembles and freezes actual candidate text; it does not choose semantic boundaries or post-edit a passed instruction. Reviewer judges the actual frozen text, not an audit summary. Generator remains the only author of a revised candidate. Source ambiguity, candidate-created gaps and technical failures continue through their existing distinct paths.

No dataset split, episode success label, ground truth, trajectory or evaluator threshold is added to model rules. No evaluation source is promoted into teaching, and no template selection count or ordering is changed.

## Template and preservation checks

The inherited tests continue to validate Core, dynamic pairs, diagnostics, authored builders, source registry, actual teaching projection, citations, snapshots and closed-loop behavior. The conversion compares protected runtime/common files and every teaching source against the fixed baseline. Restoring only the old role block in each compiled prompt must reproduce its old complete-prompt SHA. This checks that unrelated shared text, examples, schemas and formatting were not changed along with the role conversion.

Clause retention is not natural-language certification. The authored framework review preserves established distinctions: a prohibition does not prove arrival; a door attribute does not prove entry; a supported later refinement may complete the same event; no STOP does not invalidate entry; explicit intermediate stopping and real return history remain required. No template is changed to fit a new heading. Previously disputed semantics are not certified by rearranging their section.

## Validation and expectation handling

`tests/test_rxr_role_hierarchy.py` is read-only. It verifies source-clause coverage, exact rule hashes, role-local layer order, L0–L6 inside one P1 framework item, explicit five elements and handoff responsibilities, unchanged protected/teaching sources, four-stage role-block isolation and the authentic historical source identity. It prints measured prompt hashes and byte lengths but never writes expected results.

The first conversion CI run reached 273 tests. It passed the conversion-isolation checks but failed seven inherited prompt-pin assertions and one incorrect historical fingerprint assertion. The inspected measurement values, not automatically generated current outputs, are now explicitly committed in the pin fixture. The historical fingerprints are corrected against the actual pinned files, and tests also check their stated output labels and primary-review ownership. No test has been removed or its acceptance weakened.

The fixture's query, selected IDs and schema hashes remain frozen. The full-prompt hashes change only because the approved role block changes; replacing that block restores the old hashes. CI must not rewrite source, tests or expected hashes to accept arbitrary output. The final validation record identifies what actually ran, and an absent external release companion remains separately reported rather than counted as passing.

No LLM blind review or navigation experiment is executed by this conversion. Engineering checks and authored review do not establish zero model-output drift or an SR gain. The result is a traceable structural candidate. Fixed-configuration paired navigation is necessary before claiming performance improvement. The original branch must remain unchanged, and concurrent target commits must not be overwritten.
