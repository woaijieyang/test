# final-best-v1 workflow and data contracts

## 1. Intake

`adapter.from_record()` accepts an explicit dataset profile and extracts only the instruction text and task identity:
- R2R VLN-CE: `instruction.instruction_text` or `instruction_text`; if language is omitted, R2R defaults to `en`.
- RxR en-US guide JSONL: string-valued `instruction` or `instruction_text`.
- Canonical rows may use `original_instruction`.

The adapter rejects unsupported language profiles, conflicting instruction fields, blank instructions and mismatched source hashes. When no explicit `task_key` is supplied, the row must include `episode_id` (R2R) or `instruction_id` (RxR). Supply the real `split`; the retained implementation defaults missing split to `unspecified`, a known identity limitation not changed in this release. Do not silently merge duplicated IDs across splits.

The decoded instruction is preserved exactly. JSON decoding happens once; no `unicode_escape`, normalization, global trim or whitespace cleanup. Source identity includes task key, dataset, language, split and SHA-256. Scene, trajectory, GT, path, score and role metadata are not sent to the language models.

## 2. Generator G0

The generator reads the complete instruction, performs the six-step decision procedure, assembles local execution units, tests boundary legality and utility, and returns the five-field JSON candidate (`status`, `subtasks`, `issues`, `stage_audit`, `handoffs`). The same shared contract is compiled into its prompt and the reviewer prompt. A one-stage candidate is valid only after analysis; it is not an automatic short-instruction policy. A multi-stage candidate must preserve all source requirements and every handoff.

## 3. Renderer preview

The renderer receives the source object and candidate `subtasks` array. It produces a `Preview` with mode, exact rendered string, stage array, source-span/whitespace ledger, render SHA-256 and snapshot SHA-256. It does not make semantic decisions. When a source match is ambiguous, the existing renderer keeps the candidate unit and records alternative spans instead of guessing a COPY span. This is mechanical provenance, not a semantic approval. Invalid technical inputs still fail the contract.

Four modes:
- `SOURCE_EXACT`: original instruction, exact bytes; used for unchanged and fallback, distinguished by host disposition.
- `BOUNDARY_ONLY`: source text is copied in order; only authorized stage-cut whitespace is replaced by LF.
- `ASSEMBLED_SINGLE`: one source-supported reassembled stage; it is not erased back to the original merely because there is one stage.
- `ASSEMBLED_MULTI`: source-supported reassembly into multiple stages with LF separators.

## 4. Reviewer R0

Reviewer receives the original source, frozen candidate strings and exact rendered instruction. It audits all C01–C12 items, every stage and every adjacent handoff. Its output is an evidence report, not a replacement route. A material finding must quote the exact source and candidate, state the concrete defect, explain the execution/focus consequence, and give a local nonbinding repair option.

Reviewer separately reports `source_fidelity`, `closure_handoff`, and `segmentation_adequacy`. A missed useful split can be a C10 issue while route fidelity remains pass. A terminal target-directed final command can be `terminal_goal_directive`; it must not be described as arrival.

## 5. Generator G1 and Reviewer R1

With the retained implementation, R0 `revise` enters G1; an active candidate with R0 `unresolved` also enters G1. An inactive source-limited candidate with R0 `unresolved` falls back directly. On entry to G1, the generator gets the original source, frozen candidate and findings. For each finding it independently chooses `accept`, `partially_accept`, `reject` or `unresolved`, quotes source evidence and explains why. Reviewer advice is not an instruction. A proposed fix may be wrong even when the review concern is valid.

After G1, the renderer creates a new frozen snapshot. R1 runs in a fresh independent session and receives the original source, new candidate and new rendered instruction, plus the frozen R0 review, exact R0 candidate and exact R0 rendered instruction. It must disposition every R0 blocking finding exactly once, verify whether each is resolved, and independently identify any newly introduced defect. It does not receive G1's response as proof or any navigation results. There is no third reviewer and no iterative sample-until-pass loop.

## 6. Release policy

- R0/R1 `pass`: commit the exact frozen snapshot reviewed by that reviewer.
- `unresolved`, source-limited result, or any remaining material issue after the one repair: return the exact original instruction.
- Schema, quote, source-hash, request-receipt or renderer technical error: return the exact original instruction and label `fallback_technical`.

A fallback is not a semantic failure diagnosis. An accepted candidate is not proof of navigation success. The host records `semantic_correctness_verified: false` and `navigation_evaluated: false` until independent evaluation supplies those results.

## 7. Actor boundary

Only the committed `instruction` string is sent to the existing AwareVLN instruction slot. This package does not introduce goalAdapter switching, stop interception, memory, graph memory, a new completion detector, or any modification to Reason/Act, image flow, budget, STOP, or `last_reasoning`. Actual runtime goal-completion decisions remain in the existing AwareVLN flow.

For tokenizer/input provenance, instrument the existing navigator after it constructs the full native request. Record full prompt bytes, actual token IDs, tokenizer/template versions, image IDs/order and truncation. Tokenize the final complete prompt once; do not tokenize each stage independently and concatenate token IDs. This capture is a caller responsibility; `receipt_for_navigation()` checks supplied identity but cannot independently verify the caller's tokenizer or image extraction.

## 8. Located technical diagnostics

`host.protocol` detects schema/linkage violations; `adapter.source` detects input identity/shape problems. The detecting module is distinct from the author of a candidate and from an unproven semantic cause. Schema pointers include the missing property; generator repair pointers include `/candidate`. Each stage diagnostic uses zero-based `stage_index` and one-based `stage_number`. Stage `explicit_context` requires a nonblank explanation plus actual candidate quotations. Reviewer pass follows the same stage-index mode restrictions, while non-pass reports can diagnose a deficient entry.

`host.run` retains raw outputs and legacy error strings, adding role/phase/step and call-state diagnostics. A receipt records verified invocation metadata, not semantic correctness. `input_failed` has no invented source fields and no model calls. Technical errors remain exact-source fallbacks when a valid Source exists. No diagnostic is automatically fed into another model call.


## 8. Runtime wire-schema v2

G0 and G1 use `generator/output.schema.json`; G1 wraps it in `generator/repair.schema.json` with a one-to-one `responses` list. R0 and R1 use `reviewer/output.schema.json`. Generator stage audits use `subtask_index` and required `ending.stop_scope`; Reviewer dimensions use `source_fidelity`. R0's `prior_finding_reviews` is empty; R1's contains exactly one disposition per R0 finding. The complete field table and empty/null semantics are in `host/README.md`.
