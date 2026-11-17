# Generator — semantic author of executable local navigation stages

`prompt.md` is the role instruction; `shared/semantic_contract.md` is the single acceptance standard shared with Reviewer. `output.schema.json` is the active Draft 2020-12 runtime contract for both G0 and the candidate inside G1's repair envelope.

## Runtime output

The root response is `status/subtasks/issues/stage_audit/handoffs`. `ok` requires nonempty subtasks, no issues, exactly one five-element Stage Audit per stage and one Handoff per adjacent pair. `needs_review` requires empty subtasks/audits/handoffs and at least one source-grounded issue. Stage index is `subtask_index`, not `index`; `ending.stop_scope` is required. See `host/README.md` for every field's null/empty semantics and the shared Stage Audit/Handoff references.

The five meanings are entry, target, process, ending and conditions. `source_quotes` are exact original-instruction excerpts; each `candidate_quotes` array is exact text from its own executable stage; `carryover` is inherited context only and never replaces missing English. The navigator receives only the rendered natural-language subtasks.

## Boundary and repair policy

Before accepting a boundary, verify the previous stage's actual supported ending and the next stage's first unperformed action. Do not invent a pose, count origin, STOP, entry or environment fact. If a handoff is unsupported, bind a minimal source-supported entry, move the cut or merge. A final `terminal_goal_directive` may preserve an unbounded final approach but must explicitly disclaim arrival/STOP. One-stage output is valid only after a real KEEP decision; it must not silently revert to source merely because it has one stage.

## Teaching corpus

- `templates/R2R/val_seen/`: 35 R2R Generator examples.
- `templates/RxR/val_seen/`: 35 RxR Generator examples.
- `templates/RxR/legacy/`: 10 provenance-labelled legacy examples; not part of the 35 val_seen set.
- `repair_examples.json`: two G1 envelope examples, migrated to the active runtime schema.

Templates are prompt-development demonstrations, not official subtask labels or trajectory-verified ground truth. Retrieve 8–12 source-matched examples once per task; reuse the same Generator IDs in G1. G1 receives the complete R0 review and returns a complete candidate plus exactly one indexed response per blocking finding. It may reject unsupported Reviewer advice with source quotes. No reviewer patch is applied automatically.

Run `python -m host.compile` after changing role prompts, shared contract, schemas or examples. The Host/compile owner should regenerate compiled prompts and build manifests before model evaluation.


## v6 RxR en-US core and guidance

For `rxr-en-us`, the compiler always loads the ten migrated v5-format cases in `templates/RxR/core/` (G01–G10), followed by 2–4 dynamically retrieved cases from `templates/RxR/val_seen/`. The old v1 JSON is not loaded. The copied core files retain v1 lineage in `legacy_reference` while satisfying the v5 Generator Template Schema.

`dataset_rules/rxr_en_us.md` is role-specific execution guidance; `shared/dataset_rules/rxr_en_us.md` supplies the common RxR semantic definitions. G0 and G1 reuse the same core and dynamic IDs and their content hash. R2R does not load these files or core examples.
