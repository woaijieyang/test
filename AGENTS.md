# Case2 HAMLET reconstruction

User authority 2026-10-31: use case1 published baseline d230f31, independently rebuild in case2 using its src/configs/scripts/tests/docs/runtime/data/models/outputs organization; then import exact historical CBEM aw4 seed10 candidate and reevaluate. This case-specific layout supersedes the older parent stage0/stageN layout.

Only /data/zy/vln/case2 is writable. Source case1 and specifically identified historical case0 plus required shared assets are read-only. Never change parent Git or other case processes. Existing source evidence is not a new case2 result.

Use scripts/with_runtime.sh for Python/model/simulator execution. Build and caches stay within case2; do not weaken Landlock or private mount protection. Localize paths without changing policy, metrics, episode budgets or input information boundaries. No GT, goal pose or evaluator-only information may enter model inputs. Keep complete/failed/interrupted evidence.

Record work using tools/case_autolog.py and experiments using tools/case_tracker.py. Current active plan: .planning/2026-10-31-hamlet-construct/task_plan.md. One writer. Refresh GPU and process identities before launching; do not stop external processes.

Git target woaijieyang/FirstPaper-VLN HAMLET-baseline. After baseline acceptance replace the target branch file tree through an ordinary commit HAMLET-construct, preserving branch history. Exclude data, weights, runtime, logs, caches and secrets; verify remote SHA/tree. Historical migration and reevaluation follow baseline publication.

The inherited evaluator keeps raw runs in outputs/<run-id>; case_tracker entries in runs/ are a bookkeeping index linked to those immutable evidence paths. Do not move or duplicate raw output into another run tree.
