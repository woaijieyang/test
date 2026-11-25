# R2R complete Dynamic runtime contract

All selected R2R teaching cards use the same full runtime demonstration representation as fixed Core. Generator expected_output equals the entire authored output, including status/subtasks/issues/stage_audit/handoffs. Reviewer expected_output equals the entire authored expected_review, including verdict/dimensions/source_coverage/layer_checks/findings/stage_checks/handoffs/prior_finding_reviews. Exact source and the complete Reviewer candidate are retained. Metadata needed only for authoring/source provenance is not a model instruction and remains Host-owned.

This is complete semantic/runtime demonstration loading, not injection of arbitrary raw authoring metadata. Selected template IDs/counts and order remain unchanged. Core10 per role, G Dynamic4-6, R paired4-6 plus diagnostics2-3. G0/G1 and R0/R1 retain their frozen bundles; R1 still sees the prior actual review and old/new frozen candidates rather than Generator explanations. Every phase compiles the full cases; the active phase schema remains last. Direct summary requests fail closed.

Only host/r2r/teaching.py changes runtime behavior. RxR compiler/selector/teaching assets, semantic rules, schemas, renderer and Actor are unchanged. Generated R2R prompt files and the package/build hashes are rebuilt, never hand-edited. Tests assert exact entire expected_output equality rather than only token counts or marker presence.

Tests and controlled role diagnostics establish engineering coverage; real smoke establishes observed model behavior on the selected examples. They do not establish universal semantic correctness or navigation benefit. Details, source pins and raw test/call logs live in case1 outputs/subtaskAdapter/v664-r2r-full-dynamic-20261126-r0.
