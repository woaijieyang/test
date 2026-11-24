# R2R implementation and verification

## Baseline and change boundary

The repository parent is commit `081db4b9ea0712ff720c137fe96c240c26f7b15c`. The evaluated R2R evidence is commit `9dd24a655a845d59698e835c0326fbf73db5fbb8`. They diverge from `cfd4c13010f105235d026ec14a9c2b4bbd7bf94e`: the parent includes later RxR teaching and training-source integration, while the evaluated tree contains R2R corrections that are not all present in the parent. Direct tree differences, not merge-base compare summaries alone, are recorded in `provenance/r2r_parent_isolation.json`.

The target branch descends from the parent. Only the evaluated tree's R2R source/provenance and authored cases are used as offline evidence; common runtime files are integrated through explicit parent-based local patches. RxR assets and its new authoring/training behavior are retained. The common semantic contract, role prompts, repair examples, Runtime Schemas, Renderer, Adapter and navigation Actor are unchanged.

## Rule ownership and priority inheritance

`shared/dataset_rules/r2r_en.md` defines five common interpretation boundaries: phrase roles, relation scope, useful boundaries, minimal entry and grounded repair. These meanings are written once. Generator and Reviewer have different operation hierarchies in their own R2R guidance files. Each role has its own P0 root, P1 mechanisms and P2 scenario operations. Every P2 names its P1 through its stable identifier and inherits that role's P0 plus the common contract. Levels are dependency levels, not defect severity and not new output fields.

Generator first establishes the complete source route, then groups coupled events, then expresses a candidate and checks it in both directions. Its scenario operations cover object-relative directions, ordinal origin, observation/attribute roles, temporal refinement, mutually exclusive branches, repeated visits, explicit intermediate and terminal stops, inherited entry and selective repair.

Reviewer independently inventories the source, checks actual text and conditions, localizes the material defect and proposes a minimal repair. It distinguishes a wrong later endpoint from an intact earlier handoff. Recheck may resolve an unsupported old objection using unchanged candidate evidence. Different faithful grouping remains possible, while evidenced grouping defects continue to use C10.

The generated rule-link registry is an offline integrity and navigation aid. It does not create a second model-visible rule body or a separate semantic judge. Tests validate its parent references and the presence of shared meanings; they cannot mechanically prove all natural-language rules mutually consistent.

## Concrete teaching changes

All source strings and source identity objects are preserved. The authoring functions specify exact, local edits and reject missing quotes rather than inferring replacements.

- The staircase-relative first-room selection retains the staircase as its left/right reference. A staircase-bottom start is not an assumed agent heading.
- The slight-right hallway entry retains the original chair modifier attachment. The related missing-entry diagnoses restore actual entry without inventing a separate chair-pass waypoint.
- Office traversal, identified doorway, hallway-end room and final table approach are taught in both faithful coarse and multi-stage organizations. The coarse example is not rejected solely for a preferred stage count.
- The preparatory turn example remains a C10 grouping contrast; its turn is executable, and the lesson concerns coupling in that source rather than a universal turn-stage ban.
- The bedroom-door wait example permits supported endpoint-placement granularity.
- The retained wall/brown-rug stop is explicitly represented as terminal in the landmark diagnostic. Later dining-hall entry, stair-side arrival and window-side target errors no longer erase a valid preceding region handoff.
- Direction repairs preserve unaffected later turns. Doorway-facing and final STOP omissions identify their real requirement, scope and actual candidate evidence.
- The window observation is preserved in the glass-window route. The living-room participial route retains its original attachment without asserting an extra temporal waypoint.

The authoring inventory has 119 files: 45 Generator and 74 Reviewer. Runtime lookup contains 25 Generator Dynamic and 55 Reviewer Dynamic rows; only 25 of the 29 retained Reviewer pairs are selectable with the non-Core Generator pool, plus 26 diagnostics. Nineteen promoted source copies and four retained provenance pairs never become filler. Fixed Core remains ten per role, in the same ID order. Core pair references are classified as same-source or analogy rather than assumed to be execution pairs.

The explicit source-limited church-exit case is retained with a whole-source contextual explanation, not a generic spelling-refusal rule. Its semantic interpretation remains a model-assisted curation decision, not an official task gold annotation. No independent human sign-off or live-model success is claimed.

## Teaching projection

R2R teaching cards carry one concrete lesson, its counter-boundary and exact source/candidate material. Compact cards use distinct summary keys such as `evidence_excerpt` and `local_repair`, instead of old incompatible objects named like Runtime Findings. Selected Core cases retain complete current-schema initial/review output examples, including multi-stage handoff, valid coarse grouping, a material finding and a source-limited result. Existing common G1 envelopes remain unchanged.

The full author records retain stage evidence for audit. Compact model input removes repeated universal prose, not the decisive relation or completion evidence. Changing only an unprojected note does not count as injecting a lesson. Actual four-phase requests and compiled hashes are checked after materialization; token counts must be measured by the real provider, not inferred from UTF-8 byte counts.

## Selection and data flow

R2R uses four to six Generator Dynamic cases, exact Reviewer pairs in Generator order, and two to three Diagnostics. Its dedicated `r2r/selection.py` reads an integrity-bound teaching index. A case's authored skills, rather than every word in its original instruction, determine teaching coverage. Source regexes provide quoted retrieval signals, not automatic route facts or KEEP/SPLIT decisions.

The base four examples use relation fit, actual new skill coverage, duplication cost and deterministic tie breaking. Fifth/sixth examples require an uncovered specific skill. Weak source matches can use honestly labelled broad-calibration cases from the approved R2R pool. Invalid files, identity, pairing, count or hash remain hard errors. The selector sees no split-subgroup performance label, success score, navigation trace or GT.

Host obtains one Generator/pair/diagnostic bundle, stores its real pool/ranking/exclusion trace and freezes it. G0/G1 reuse the Generator bundle; R0/R1 reuse the Reviewer bundle. Explicit IDs must also satisfy production bounds and paired-prefix/diagnostic-suffix ordering. Offline `all` mode uses the complete ordered library, not arbitrary bypass IDs. Core loading remains unconditional even when optional examples are disabled.

Request construction uses the existing profile dispatch and schemas. Reviewer sees source, candidate status/subtasks/issues and the frozen English, not Generator's private stage audit. Renderer freezes the candidate before each review. Host releases only the corresponding reviewed snapshot or follows the existing precise-source fallback. The implementation adds no online goal-switching, verified-pose state or new STOP controller.

## Reproducible authoring and integration

`python -B -m r2r_authoring.build --write` materializes the explicit R2R authoring specification from the evaluated evidence commit. `--check` compares without changing files. It validates all 119 cases against authored schema, exact evidence and active runtime contracts before writing.

`r2r_authoring/integrate.py` records the narrow initial integration into compiler, selector, Host and manifests. A file must match its immutable parent or exact expected result; concurrent edits are refused. The resulting runtime code is committed, not patched dynamically during model requests. Further development must explicitly update this offline specification rather than silently overwriting new edits.

`r2r_authoring/verify.py` compares the parent in a separate interpreter and worktree. It checks all RxR Dynamic-source queries plus boundary cases across initial/repair/review/recheck, selected IDs, Schema hashes, actual prompt hashes and mixed-profile calls. It also checks protected resources and generated RxR bytes. Shared implementation hashes may change legitimately and are recorded truthfully.

R2R authoring and the RxR auto-authoring workflow are trigger-isolated. The R2R pipeline publishes generated results only after validation and only if the branch still points at the tested input SHA; it never force-pushes over parallel work.

## Validation and limitations

Run the author check, integration check, prompt build, strict integrity verification, complete repository regression and `r2r.test_quality`. The new tests cover all active templates, role inheritance, candidate repairs, retained local handoffs, compact projection, explicit counts, honest weak matching, index drift, cross-process selection stability and actual four-phase Host replay. They include rejecting a false grouping complaint with an unchanged candidate, accepting only the supported part of a repair, unresolved-source fallback, and rejecting a fabricated resolution without evidence.

The inherited external release-transaction test needs a companion `manage_release.py` that is not in this repository. The runner identifies only that known missing dependency and reports it separately; it is not counted as passed. Any different import error or test failure remains fatal. Existing expected counts are updated only where the approved R2R policy or explicitly recalibrated teaching label changed; RxR golden expectations remain frozen.

No live language-model inference, simulator navigation or SR/SPL/nDTW improvement is established by these tests. Previously analyzed evaluation episodes are regression evidence, not newly independent generalization data. Measure first-pass semantic quality, false reviewer findings, new errors after repair, recovery and regression counts, path efficiency and actual provider costs in the next frozen paired experiment.
