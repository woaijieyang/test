# R2R detailed teaching and execution framework

## Change boundary and directory ownership

This refinement uses the existing development branch and the immutable evaluated source commit `9dd24a655a845d59698e835c0326fbf73db5fbb8` for R2R template evidence. The inherited integration parent is `081db4b9ea0712ff720c137fe96c240c26f7b15c`; the preceding reviewed runtime is `465635eb8dad310404dab0e1d684ade3b71ff70b`. These identifiers are engineering provenance, not model-visible release labels.

- Shared R2R interpretations remain in `shared/dataset_rules/r2r_en.md`.
- Named Generator/Reviewer responsibilities, workflows and scenario operations remain in each role's `dataset_rules/r2r_en.md`.
- Runtime selection and projection remain in `r2r/selection.py` and `r2r/teaching.py`.
- Offline source-local authoring remains in `r2r_authoring/`; `detail.py` is the active positive audit refinement used by `build.py`.
- Runtime templates remain in the existing `generator/templates/R2R` and `reviewer/templates/R2R` locations. Indexes remain under shared dataset rules; validation and source-change receipts remain under `provenance/`.
- R2R-specific regression tests are in `r2r/test_refinement.py`, included by the repository regression runner. Common tests and RxR golden behavior are not loosened.

No navigation Actor, Renderer, Adapter, common semantic contract, generic role prompt, Runtime Schema, RxR teaching source or RxR projection is changed. This is language organization, not online goal switching or a new STOP controller.

## P0, P1 and P2

P0 identifies the role, source authority, execution setting, useful output and repair responsibility. P1 gives the whole work sequence, including independent reading, dependency binding, grouping, actual English, Entry/Target/Process/Ending/Conditions, adjacent handoffs, bidirectional readback and phase-specific delivery. P2 names scenario operations and explicitly inherits its P1 and P0.

Generator scenarios distinguish property/action/observation, supported spelling repair versus new navigation facts, relation owner and ordinal origin, sustained path constraints, modifier attachment, same-event refinement and terminal scope, branches and returns, coupled transit versus independent targets, minimal entry, endpoint strength and selective repair. Reviewer scenarios independently check the same meanings and localize actual defects without copying Generator self-audit.

The rules protect useful splitting as well as coherent KEEP. Short sources may expose distinct targets; a supported placement/wait may form a separate goal. Neither a room word nor a turn/stop verb alone establishes a necessary cut. Reviewer rejects actual material defects, not alternative wording or an arbitrary preferred stage count.

## Source-local template refinement

`r2r_authoring.detail.author_generator` begins with the evaluated stage audit. It preserves evaluated candidate wording except four explicitly named source corrections: participial route attachment, retained window observation, staircase-relative room selection, and hallway-entry modifier attachment. It preserves meaningful explicit entry anchors such as the bedroom-exit origin of the first right-hand door.

Target/Ending changes are case-authored. Existing stage-relevant source quotes remain local. A listed condition override refines that case's evidence; an absent override retains the previous condition instead of becoming null. Each multi-stage example has a specific intended carrying-state mapping. That state is not a sensor-confirmed completion. Runtime contracts validate every actual quote against its owning stage.

The center/right door selection retains its selection relation. A source-directed destination is not automatically weakened to terminal_goal_directive merely because STOP is absent. The office route retains its evaluated useful contextual anchors and local source fragments. The staircase-relative first room and slight-right hallway entry retain their separately established semantic corrections.

Positive Reviewer examples are synchronized with their actual same-source Generator candidates and coverage ownership. Existing source-local diagnostic repairs remain. A valid coarse office example retains an explicit C10 explanation; this does not remove the common ability to diagnose evidenced under-segmentation. The provenance no longer describes that accepted contrast as a deliberately corrupted route.

No inspected evaluation outcome, partition label, score or trajectory is used as template content or a runtime retrieval feature. The 119 author assets remain curated teaching annotations, not official subinstruction ground truth or independently human-certified semantics.

## Complete demonstrations and focused remaining cards

All ten fixed Core cards for each role use complete current-schema output demonstrations. For each request, the first two Generator Dynamic examples are complete. Reviewer receives complete demonstrations for the corresponding first two paired cases and the first selected diagnostic. Remaining cards retain the actual stages/candidate, case lesson, reusable operation, counter-boundary, meaningful stage semantics, completion and continuity evidence, and local repair/protection when relevant.

The `detailed` argument is respected. `dynamic_is_detailed()` is called by the R2R compiler branch, not merely declared in an unused helper. The same ordered examples and detail policy apply in G0/G1 and R0/R1. The existing repair-envelope demonstrations remain unchanged. A summary is labelled as a lesson, not an incomplete object pretending to be an active Runtime Finding.

More detailed input is intentional. Measure actual provider tokens and truncation in the real transport; UTF-8 bytes do not establish either. Do not silently drop detailed cases or source requirements at a repair phase to meet a guessed budget. If the configured provider cannot accept the verified request, handle it as the existing technical error rather than claiming it received the full teaching.

## Complementary selection and actual trace

Production quantities remain four to six Generator examples, exact Reviewer pairs in that order, and two to three diagnostics. Match only the current source to authored teaching skills. At each base slot, prioritize actual incremental skills, then concrete relation fit, repetition cost and stable tie-breaks. Core overlap is a soft cost, not an absolute exclusion. Optional slots require an uncovered specific skill. Weak matching may use honestly marked broad calibration; hard asset, source, pairing or hash errors remain failures.

Selection returns its real eligible pool, exclusions, per-slot candidate order and score components. It also records the exact canonical projected bytes and SHA for each selected Dynamic card, with the same detail policy the compiler applies. These receipts are Host metadata, not extra model output fields. The full Prompt Hash remains the authoritative record of the actual compiled system text.

No count-based KEEP/SPLIT quota, navigation-score ranking, B-partition lookup or new retrieval model is introduced. Explicit IDs must also satisfy production quantities and exact eligible pair mapping. Source-archive and retained provenance pair assets are not filler examples.

## Validation and deployment sequence

Use a full-history checkout when authoring, because immutable Git source evidence is required by the offline build. Production request handling uses committed files and indexes; it does not run Git authoring or rewrite examples online.

1. Apply the exact checked integration: `python -B -m r2r_authoring.integrate --write`.
2. Materialize source-local teaching: `python -B -m r2r_authoring.build --write`, then `--check`.
3. Verify inherited explicit test expectations and compile via `python -B -m host.compile`.
4. Compare protected assets and all frozen parent RxR four-phase requests with `python -B -m r2r_authoring.verify --isolation`.
5. Refresh derived fingerprints and run `python -B verify_package.py`.
6. Run `python -B -m r2r_authoring.regression`; this includes inherited tests, actual four-phase Host replays and the new detail/preservation tests.
7. Run smoke and deterministic rebuild, refresh final records, and validate a clean candidate worktree before non-forced publication.

The authoring integration refuses unrecognized shared-runtime edits rather than overwriting concurrent work. CI publication checks that the branch still points to the tested input commit, builds a separate final worktree, repeats tests and integrity, then pushes without force. Restart workers after an asset update; task-level frozen bundles and cached libraries are not a hot-update interface.

The inherited deployment test needs a companion manage_release.py outside this repository. Its exact missing-file condition is reported separately, never counted as a passing test. Any other import error or test failure is fatal.

## What this verification does and does not prove

The regression suite checks complete Core demonstrations, at least two complete Dynamic examples in all phases, the full diagnostic, projection receipt equality, copy isolation, preserved explicit anchors/local source evidence, source-backed field corrections, stable pairing, true selection trace, rule parent links and complete Host release/fallback behavior. It checks unchanged RxR inputs and assets separately from changed shared-code provenance hashes.

It does not run a live Generator/Reviewer provider, visual navigation or counterfactual trajectory replay. No claim of improved SR/SPL/nDTW or elimination of all regressions follows from CI. Next evaluate semantic error/false finding/repair rates and paired navigation recovery/regression with frozen tasks, model, imagery, history, STOP policy and budget. Keep both prior successful cases and newly recovered cases in the regression roster.
