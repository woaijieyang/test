# Integrated profile contract and full teaching

## Authority and migration boundaries

Common configuration and R2R are imported from immutable source `33d66756de8d545db001f3854194bf5d5b5a8592`. RxR semantic assets are retained from `b69e04ddc7097b47f8d201beed2fa5e2d9ffd34e`. The source branch is not modified. `provenance/profile_migration_inventory.json` inventories every difference before migration and records the policy used for it. Historical validation reports retain their original baselines and are not current combined acceptance results.

The imported R2R runtime, rules, teaching banks, manifests, phase-specific repair/recheck examples and authoring modules remain source-exact. The shared compiler and Host combine two conditional dispatch paths: R2R uses `host/r2r/`; RxR retains `host/rxr_teaching.py` and `host/rxr_contract.py`. There is no cross-dataset rule fallback and no new semantic role.

## File ownership

Runtime remains under `host/`; source-specific R2R operations are under `host/r2r/`. R2R offline authoring is under `tools/r2r_authoring/` and its tests under `tests/r2r/`. RxR retains its reviewed module locations rather than undergoing an unrelated directory rewrite. General project documents move to `docs/`, package verification to `tools/verify_package.py`, and the historical package report to `provenance/package_validation.json`. Obsolete duplicate root modules/documents are removed as in the source. Integration checks belong to `tools/check_profile_integration.py` and `tests/test_profile_integration.py`, not to model prompts.

## CLI and workflow

The packaged `host/role-pins.json`, CLI journal, transport receipts, recovery behavior and explicit configuration validation are retained from the source repository. A caller may override packaged pins with `--pins`. `--cli-ledger` retains durable request-bound invocation records; `--recover-command` performs lookup only and must not silently submit another generation. No local credentials, private CLI home, external datasets or untracked machine settings are copied. Only tracked repository settings are available to this migration.

Example entry points:

```bash
python -B -m host.run --help
python -B -m host.run --record INPUT.json --output RESULT.json --cli-ledger /path/outside/source/journal
python -B tools/verify_package.py
python -B tools/check_profile_integration.py --runtime
```

The bounded G0 -> R0 -> optional G1 -> R1 chain is unchanged. R2R source-family-aware selection, complete teaching and phase-specific repair/recheck examples are imported intact. RxR retains the complete P0/P1/P2 hierarchy, independent L0-L6 review, restored-stop calibration, exact evidence, profile-local structural checks and selective repair. Reviewer receives actual source/candidate snapshots, not Generator self-audit; R1 receives the prior actual review and frozen old/new candidates. A correct rejection of unsupported feedback may leave candidate English unchanged. Only the independently reviewed snapshot is released. No extra semantic round, Actor goal-switch or automatic semantic judge is introduced.

## Complete Dynamic input

Every selected Core, Dynamic and Diagnostic is now complete in every phase. Counts, selected IDs, ordering, source exclusion and paired alignment are unchanged within each imported/retained profile. R2R uses its source full `expected_output` representation. RxR retains its compatible teaching wrapper but preserves every active output field: status/subtasks/issues/stage_audit/handoffs for Generator; verdict/dimensions/source_coverage/layer_checks/findings/stage_checks/handoffs/prior_finding_reviews for Reviewer. Source and Reviewer candidate remain exact. Field aliasing in the teaching wrapper is not content summarization; tests reconstruct and compare the entire active output.

RxR's legacy `detailed=False` parameter is accepted for offline-call compatibility but returns the same full card. It cannot enable compression. No stage summary, process deletion, layer-summary reduction, word-limit truncation or model summarizer remains in the RxR projection. Runtime payloads still follow their active schema, not the teaching wrapper. Initial-output examples in G1 do not replace the required repair envelope. Prior-finding examples do not replace actual R1 obligations.

Full input can increase token use. The compiler does not silently remove examples or compress content to fit an assumed budget. Actual model context capacity, output budget and provider truncation must be checked with real receipts; UTF-8 size is not a token measurement. No live provider invocation or navigation gain is asserted by this integration.

## Independent verification

`tools/check_profile_integration.py` compares imported R2R/common assets to the source, retained RxR assets to the target, and full teaching outputs field-for-field. Its runtime mode runs independent Python processes in immutable Git worktrees: R2R selections, four-stage model prompts and schemas must equal the source; RxR selections and schemas must equal the retained target, with prompt changes limited to the explicit full-input policy and its explanation. Reversed profile order is checked for cache contamination.

Run all inherited tests, imported R2R tests and retained RxR tests, plus full-Dynamic and CLI regressions. An external `manage_release.py` companion is not part of this repository; missing-fixture tests remain separately reported, never counted as passed. The source's historical real-model experiment is not a new experiment on the combined branch. Current combined results are in `provenance/profile_integration_validation.json` and `provenance/profile_integration_checks.json`.

Old single-profile authoring/publishing scripts retain their source identities and safeguards. They must not overwrite the combined tree with an old opposite-profile baseline. Combined-branch CI validates committed assets without rewriting runtime sources or expected prompt fixtures.
