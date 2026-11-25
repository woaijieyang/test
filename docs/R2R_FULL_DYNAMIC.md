# R2R complete Dynamic runtime contract

All selected R2R teaching cards use the same full runtime demonstration representation as fixed Core. Generator expected_output equals the entire authored output, including status/subtasks/issues/stage_audit/handoffs. Reviewer expected_output equals the entire authored expected_review, including verdict/dimensions/source_coverage/layer_checks/findings/stage_checks/handoffs/prior_finding_reviews. Exact source and the complete Reviewer candidate are retained. Metadata needed only for authoring/source provenance is not a model instruction and remains Host-owned.

This is complete semantic/runtime demonstration loading, not injection of arbitrary raw authoring metadata. Selected template IDs/counts and order remain unchanged. Core10 per role, G Dynamic4-6, R paired4-6 plus diagnostics2-3. G0/G1 and R0/R1 retain their frozen bundles; R1 still sees the prior actual review and old/new frozen candidates rather than Generator explanations. Every phase compiles the full cases; the active phase schema remains last. Direct summary requests fail closed.

Only host/r2r/teaching.py changes runtime behavior. RxR compiler/selector/teaching assets, semantic rules, schemas, renderer and Actor are unchanged. Generated R2R prompt files and the package/build hashes are rebuilt, never hand-edited. Tests assert exact entire expected_output equality rather than only token counts or marker presence.

Tests and controlled role diagnostics establish engineering coverage; real smoke establishes observed model behavior on the selected examples. They do not establish universal semantic correctness or navigation benefit. Details, source pins and raw test/call logs live in case1 outputs/subtaskAdapter/v664-r2r-full-dynamic-20261126-r0.

## Verified snapshot — 2026-11-26

The runtime change was validated at commit `724c47e65fdd13e5d537571c318c9ed99c314520`:

- 395 repository tests passed in the local test layout with the companion release fixture present. A standalone checkout reports the absent external `manage_release.py` fixture separately; it must not count those tests as passed. The CI regression report is authoritative for the tests available in CI.
- 40 compiled prompts (10 records across G0/R0/G1/R1) preserved every selected case's complete expected output and deterministic template IDs/order.
- 10 normal R2R records completed through 20 actual Generator/Reviewer calls with exact source, receipt, snapshot and replay checks.
- Six additional actual calls were explicitly labeled diagnostics: a correct candidate passed; an authored prohibition/ordinal defect was detected, repaired and rechecked; an unsupported count suggestion was rejected by Generator and independently rechecked by Reviewer. Authored initial candidates/advice are not claimed as model-generated G0/R0 outputs.
- All 26 actual requests retained the complete experiment prompt and full selected Dynamic outputs. The actual model was `gpt-5.6-sol` with `high` effort. No navigation evaluation was performed, and no universal semantic-accuracy claim follows from this small validation set.

The publication follow-up updates documentation, validation provenance and the publication file allowlist only; it does not change prompts or runtime semantics. Raw run logs, local machine configuration, credentials, datasets and navigation assets are not part of this repository update.

## History prerequisite

Authoring and isolation checks use pinned historical commits, including evaluated commit `9dd24a655a845d59698e835c0326fbf73db5fbb8` on branch `LLM-decompose-v6.6`. CI checks out full history. For a single-branch clone, fetch that reference with `git fetch origin LLM-decompose-v6.6` before running authoring/replay checks; never substitute another baseline to make a check pass.
