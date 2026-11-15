# Host runtime contract — v2

This host revision updates only the existing `host/run.py`, `host/protocol.py`, this README, and the active runtime schemas. It preserves the current adapter, renderer, compiler, selector, transport callback, failure receipts, snapshot hashing and AwareVLN actor boundary. No new orchestration framework or semantic reviewer is introduced.

## 1. Authoritative contracts and phase matrix

The **runtime** contracts are these three Draft 2020-12 files:

| Phase | Role | Active response schema | Required input |
|---|---|---|---|
| G0 | Generator | `generator/output.schema.json` | `original_instruction` |
| R0 | Reviewer | `reviewer/output.schema.json` | source + frozen candidate + exact rendered instruction |
| G1 | Generator | `generator/repair.schema.json` | source + frozen candidate + complete R0 review |
| R1 | Reviewer | `reviewer/output.schema.json` | source + new frozen candidate + new rendered text + frozen R0 review + old candidate + old rendered text |

The four files in `shared/template_schemas_v1_5_2/` remain **teaching schemas**. The active Generator schema reuses `stage_audit.schema.json` and `handoff.schema.json` by reference. The Reviewer uses the same Stage Audit and Handoff nested contracts. Teaching examples retain their own wrapper keys (`input/output` or `review_input/expected_review`); they are not runtime wire objects. `compile.py` must include the phase-specific active schema, the corresponding role prompt, the shared semantic contract, and selected role/dataset examples. It must not validate teaching wrappers as if they were runtime responses.

## 2. Generator output schema: required fields and meanings

All root fields are required and non-null. Unknown fields are rejected.

| Field | Type / allowed values | Empty / null meaning |
|---|---|---|
| `status` | `ok` / `needs_review` | Never null |
| `subtasks` | array of nonempty English strings | `ok`: nonempty; `needs_review`: exactly `[]` |
| `issues` | array of `{code, source_quote, problem}` | `ok`: exactly `[]`; `needs_review`: at least one source-grounded issue |
| `stage_audit` | array of Stage Audit Schema objects | `ok`: exactly one per subtask; `needs_review`: exactly `[]` |
| `handoffs` | array of Handoff Schema objects | `ok`: exactly one per adjacent pair (0 for one stage); `needs_review`: exactly `[]` |

The Stage Audit Schema is authoritative for nested field names. The index is **`subtask_index`**, zero-based. It is not `index`.

- `entry.mode`: `episode_start`, `explicit_context`, `inherited_pose`, `inherited_entity`, `missing`, `source_unspecified`. `text` is a required nonempty string; `candidate_quotes` may be empty for episode start/inherited state. For `explicit_context`, Host requires nonempty text and exact candidate quotation(s).
- `target`: `text` is string or null; candidate quote array is empty only when text is null. A source-supported target must have text and exact quote(s).
- `process`: text is string or null in the schema, but an accepted `ok` stage requires nonempty text and candidate quote(s).
- `ending.kind`: `explicit_event`, `bounded_action`, `linked_trigger_or_refinement`, `terminal_goal_directive`, `unspecified`. Accepted stages cannot use `unspecified`; `terminal_goal_directive` is final-stage-only and its text must explicitly disclaim unsupported arrival/STOP.
- `ending.stop_scope`: required enum `none`, `intermediate`, `terminal`. `none` means no source-required stationary stop/wait/stand/remain at this stage ending. `intermediate`/ `terminal` must be supported by quoted stationary/stop evidence and match whether a later stage exists. A stage boundary alone is never a STOP.
- `conditions`: text string or null. Null is paired with `candidate_quotes=[]`; non-null conditions require exact candidate evidence.
- `source_quotes`: nonempty exact substrings of the original instruction.
- `carryover`: array of strings; `[]` means no inherited context needs to be carried. It is explanatory state, not a substitute for executable words.

Handoff objects use the shared schema: adjacent `from_subtask_index` / `to_subtask_index`; `status` = `supported`, `gap`, or `source_limited`; non-null `preceding_exit` and `next_entry` endpoint objects, each with text and exact candidate quote; `shared_context` array (empty means no additional shared context); `source_requirement_ids`; and nonempty `handoff_rationale`. For accepted `ok` candidates, every handoff must be `supported`.

## 3. Reviewer output schema: required fields and meanings

All root fields are required and non-null. R0 and R1 use the same schema.

| Field | Type / allowed values | Empty / null meaning |
|---|---|---|
| `verdict` | `pass`, `revise`, `unresolved` | Never null |
| `dimensions` | exactly `source_fidelity`, `closure_handoff`, `segmentation_adequacy`; each `pass`, `issue`, `source_limited`, `not_assessable` | No aliases such as `fidelity` |
| `source_coverage` | nonempty array of requirement rows | Each row groups a meaningful event/condition; not one giant route row and not one row per token |
| `layer_checks` | exactly ordered L0–L6 | All seven required |
| `findings` | array of material evidence-backed findings | `[]` means no blocking defect |
| `stage_checks` | one row per actual candidate stage | Empty only when candidate has no stages (`needs_review`) |
| `handoffs` | one row per adjacent pair | `[]` for one-stage or no-stage candidate |
| `prior_finding_reviews` | array of R0 finding dispositions | R0 must return `[]`; R1 returns exactly one row per R0 finding |

### Source coverage

Each row requires `requirement_id`, exact `source_quote`, semantic `requirement`, `candidate_evidence`, and `status`. Status is `covered`, `omitted`, `altered_or_missing`, `superseded`, or `requires_review`. Candidate evidence is an array of `{subtask_index, quote}`; indices identify the actual stage containing each exact quote. Empty evidence is allowed for a genuine omission/source ambiguity, not for a covered requirement. Cross-stage coverage may cite multiple stages.

### L0–L6 layer checks

Each layer row requires `layer`, `status`, `finding_indices`, and `conclusion`. Canonical layer names, in order:

1. `L0_integrity`
2. `L1_source_coverage`
3. `L2_dependencies`
4. `L3_stage_checks`
5. `L4_handoffs`
6. `L5_grouping`
7. `L6_route_readback`

Status is `pass`, `issue`, `source_limited`, or `not_applicable`. An `issue` or `source_limited` layer must reference at least one finding. Every finding must be referenced by its failed layer. A stage marked `gap`/`source_limited` must map to a finding that cites that stage and at least one of its source requirement IDs. A handoff marked `gap`/`source_limited` must map to a finding that cites at least one adjacent stage, overlaps the handoff's source requirement IDs, and identifies a closure/handoff issue.

### Findings and cross-stage evidence

A finding requires `code`, `failed_layer`, `c_check`, `dimension`, `related_dimensions`, `affected_subtask_indices`, `source_requirement_ids`, exact `source_quote`, `candidate_evidence`, `evidence_level`, `problem`, `execution_consequence`, and `repair`.

- Evidence level is blocking S1 or S2. S3 is not a blocking finding.
- Each candidate evidence item is `{subtask_index, quote}`; it must exist in that exact stage.
- `affected_subtask_indices` identifies stages implicated by the defect. `repair.affected_subtask_indices` identifies the stages the proposed local fix changes and must be a subset of the affected indices.
- **Candidate evidence is deliberately not restricted to repair-target indices.** A handoff finding may cite the preceding stage's exit and the next stage's entry, while targeting only the next stage for repair. Host validates each evidence index and quotation against its own stage.
- Repair operation is `bind_entry`, `merge`, `restore`, `remove`, `reorder`, `regroup`, `clarify_reference`, `abstain`, `correct_refusal`, or `preserve_uncertainty`. Protected requirements must be nonempty.

### Stage checks and handoffs

Each stage check uses `subtask_index`, `status` (`supported`, `gap`, `source_limited`), the five structured elements (`entry`, `target`, `process`, `ending`, `conditions`), `source_requirement_ids`, `source_quotes`, and `carryover`. The five nested elements follow the same schema and semantics as Generator stage audit. Each handoff uses the shared Handoff Schema and must cover every adjacent pair exactly once.

### R1 prior-finding dispositions

Each row requires `finding_index`, `status` (`resolved`, `partially_resolved`, `unresolved`), `candidate_evidence` from the **new** candidate, and `explanation`. R1 must report each prior blocking R0 finding exactly once, in order. A PASS is forbidden unless every prior finding is `resolved`. R1 still performs a complete fresh review and places newly introduced defects in ordinary `findings`.

## 4. Repair envelope

`generator/repair.schema.json` requires exactly `candidate` and `responses`.

- `candidate` reuses the complete Generator runtime schema. It is not a partial text patch.
- `responses` has exactly one item per R0 finding, in the same order. Each item contains `finding_index`, `decision` (`accept`, `partially_accept`, `reject`, `unresolved`), one or more exact `source_quotes`, and a nonempty `reason`.
- An empty responses array is valid only when R0 supplied zero findings. A response is a disposition, not permission to apply Reviewer text mechanically.
- Host verifies one-to-one index coverage and source quotation existence. It cannot determine whether the reason is semantically sound.

## 5. Deterministic workflow and release gates

`run_record(src, transport, *, pins, separator, example_count, selection_mode)` remains the public entry point. The call budget is bounded to G0 → R0 → optional G1 → R1.

1. **G0** receives only the complete original instruction. Host validates the active Generator schema, source quotations, one audit per stage, exact adjacent handoff coverage and stage indices.
2. **Freeze** renders the exact candidate, records source/whitespace ledger and hashes, and binds candidate + rendered text into one immutable snapshot.
3. **R0** receives source, frozen candidate and exact rendered text. It independently audits L0–L6. R0 `prior_finding_reviews` must be empty.
4. **G1** is called once for R0 `revise`, or for R0 `unresolved` only when G0 supplied an active `ok` candidate. An inactive G0 `needs_review` plus R0 `unresolved` goes directly to exact-source fallback. G1 receives source, frozen candidate and full R0 findings/review. It returns a complete candidate plus one response per finding; it may reject unsupported Reviewer advice with source evidence.
5. **Re-freeze** the G1 candidate. The new snapshot is distinct and independently hashed.
6. **R1** is a fresh Reviewer session. It receives source, new candidate and rendered text, plus the exact frozen R0 review, R0 candidate and R0 rendered text. It must disposition every old blocking finding and independently inspect the whole new candidate. It does not receive G1's response as proof.
7. R0/R1 `pass` releases only the exact frozen snapshot that reviewer saw. Any non-pass after the one repair returns the exact original source.

### Unresolved and technical failure

- A source-critical ambiguity may yield `unresolved` only after full-context reference resolution and sensible regrouping fail. Candidate-created gaps are `revise`, not `unresolved`.
- Active `ok` candidate + R0 `unresolved`: one G1 is allowed to reject an unsupported interpretation or propose a source-grounded regrouping.
- Inactive `needs_review` candidate + R0 `unresolved`: direct exact-source fallback; do not manufacture a partial candidate.
- A false `needs_review` or repairable omission may be `revise` and enter G1.
- Schema, exact-quote, index, renderer, snapshot, receipt or transport failures are **technical** failures. Preserve the actual failure receipt and call state, use exact original instruction for fallback, and record `fallback_technical`. If transport execution is unknown, do not retry the request. Technical failures remain in the total evaluation denominator and must not be relabelled semantic `unresolved`. For CLI use, pass `--recover-command '<lookup-only command>'` **before** `--transport`. The lookup command receives JSON with `operation='lookup_original_request'`, `request_sha256` and the original request; it must return `{\"found\":false}` or `{\"found\":true,\"reply\":<the original transport reply>}`. It must query the provider's existing request/receipt store and must not start a new model generation.
- A fallback is not a semantic diagnosis. The host records `semantic_correctness_verified: false` and `navigation_evaluated: false` until external evaluation supplies those results.

## 6. Interfaces deliberately unchanged

- Preserve `run_record(src, transport, *, pins, separator, example_count, selection_mode)`.
- Preserve the injected transport callback and actual provider receipt fields (`model`, `effort`, `request_id`, optional token/hash metadata).
- Preserve raw model outputs, request hashes, call states, `receipt_for_navigation()`, source identity and exact-source fallback.
- Preserve `renderer.freeze` and its source prefix/suffix/whitespace ledger. Renderer is mechanical and never rewrites semantic content.
- Preserve the existing AwareVLN actor boundary: only `result["instruction"]` enters the instruction slot. Audit, findings, template IDs and carryover are not actor state.
- Preserve the existing selector/compiler ownership. `compile.py` must use the phase matrix above; `template_selector.py` remains source-driven and freezes selected IDs per task.

This Host performs structural and provenance checks only. It does not prove semantic entailment, path/viewpoint alignment, physical completion or navigation success.
