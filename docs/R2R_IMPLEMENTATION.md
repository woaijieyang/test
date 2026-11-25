# R2R implementation and verification

The current detailed operating specification is [R2R detailed teaching and execution framework](R2R_DETAIL_REFINEMENT.md). This page is the deployment entry point. It describes the committed implementation, not a navigation-performance certification.

## Baseline and isolation boundary

The development parent is commit `081db4b9ea0712ff720c137fe96c240c26f7b15c`. The evaluated R2R source evidence is `9dd24a655a845d59698e835c0326fbf73db5fbb8`. Their direct tree differences are recorded in `provenance/r2r_parent_isolation.json`. The parent contains later RxR teaching and training-source integration; the evaluated tree contains R2R evidence that is not all present in that parent. The implementation remains parent-based and preserves its RxR behavior rather than copying evaluated common files over it.

Common role prompts, semantic contract, Runtime Schemas, repair envelopes, Renderer, Adapter and Actor behavior are unchanged. New runtime logic is selected only for `r2r-en`. Parent RxR rules, templates, training-source assets, selected IDs, four-phase system prompts and schemas are checked independently. Shared implementation file hashes may change truthfully without implying that RxR model input changed.

## Functional ownership

| Location | Responsibility |
|---|---|
| `shared/dataset_rules/r2r_en.md` | Common R2R phrase, scope, grouping, entry and repair meanings |
| `generator/dataset_rules/r2r_en.md` | Named Generator P0 identity, P1 full workflow/five elements, P2 scenario operations |
| `reviewer/dataset_rules/r2r_en.md` | Independent review responsibility, L0-L6 workflow and scenario-specific evidence/repair |
| `generator/templates/R2R`, `reviewer/templates/R2R` | Source-traceable authored examples, candidates and full audit evidence |
| `r2r/selection.py` | Source-only complementary selection, strict pairing and true selection/projection trace |
| `r2r/teaching.py` | Complete or focused teaching projection, never Runtime schema modification |
| `r2r_authoring/detail.py` | Active offline field-local positive refinements from evaluated examples |
| `r2r_authoring/review.py` | Explicit source-local corrections for Reviewer teaching |
| `r2r_authoring/build.py` | Validate and materialize templates, teaching index and rule links |
| `r2r/test_quality.py`, `r2r/test_refinement.py` | R2R contract, teaching, selection and full Host replay regression |
| `provenance/r2r_*` | Actual integrity, source changes, isolation and test records |

The generated rule-link registry is a navigation/integrity aid for maintainers; it does not contain a second model-visible rule body. P0 identifies each role's job, authority and expected useful output. P1 specifies the complete workflow, including Entry, Target, Process, Ending, Conditions, Handoff and readback. Each named P2 specifies an applicable operation and inherits its P1 and P0. These levels neither determine defect severity nor add output fields.

## Evaluated evidence is refined, not uniformly reconstructed

All original source strings and source identities are preserved. The active positive author starts from each evaluated candidate and stage audit, keeping stage-local source quotations, explicit entry modes and operative conditions. Absence from a new condition override table does not erase an existing condition. Multi-stage examples carry case-specific intended context using the current canonical Handoff object format.

Candidate wording remains evaluated except four explicit source corrections: living-room participial attachment, the preserved window observation, staircase-relative first-room selection, and hallway-entry/chair modifier attachment. The original coherent single-stage and useful multi-stage examples are both retained. Fountain/turn and bedroom-traversal examples keep their evaluated two-stage organization with matching audits and reviews, while their lessons acknowledge a supported combined alternative.

Target and Ending are classified from the case's actual source event. A source-directed destination without STOP is not automatically a free approach; a true final towards instruction remains a terminal_goal_directive. Necessary bedroom-exit counting context remains explicit. Field-level corrections do not authorize inventing a route fact to fill an audit slot.

Source-local diagnostic corrections continue to preserve valid preceding entries/handoffs while locating later target or terminal errors. The office coarse alternative has an explicit C10 explanation; its acceptance does not abolish under-segmentation review. The source-limited church-exit example remains a model-assisted author judgment, not official subtask gold or independently human-certified correctness.

The immutable original inventory is 119 files (45 Generator and 74 Reviewer), plus six explicitly registered synthetic branch/return contrasts: two Generator, two paired Reviewer, and two diagnostics. The total is 125. Runtime has ten fixed Core per role, 27 eligible Generator Dynamic, 31 retained Reviewer pair assets and 28 eligible diagnostics. Only the 27 pairs of eligible Generator examples can form the adaptive paired prefix; four retained pairs and nineteen promoted source copies are not filler. Synthetic sources have no fabricated official episode or trajectory identity.

## Detailed teaching in actual four-phase requests

Every fixed Core card is a complete current-schema initial/review output demonstration. Generator Dynamic positions 0 and 1 are complete. Reviewer Dynamic positions 0 and 1 preserve those exact Generator pairs, and its first selected diagnostic is also complete. Remaining cases retain meaningful stage semantics, exact evidence, the reusable operation and counter-boundary rather than only a short route summary.

The `detailed` argument is honored, and the R2R compiler invokes `dynamic_is_detailed()` for the actual ordered selection. `examples=False` disables optional Dynamic only; ten complete Core cases remain. The common G1 repair-envelope examples are retained. Summary fields are labelled distinctly from Runtime Findings. The full author record remains available even when a focused card is selected.

Teaching is intentionally detailed. Actual input token counts and truncation must be measured by the provider. Canonical UTF-8 byte comparisons can describe payload size but cannot establish semantic effectiveness, tokenizer cost or whether a provider accepted the complete request.

## Selection, freezing and delivery

R2R selects four to six Generator Dynamic examples, exact Reviewer pairs in the same order, and two to three diagnostics. At each slot it considers relation applicability, actual incremental authored skills, redundancy and stable tie breaks. Core relation coverage is a soft cost during mandatory selection. Optional slots require an uncovered relation subtype or teaching polarity, or a genuinely uncovered skill; weak source matches can use transparently labelled broad calibration from the approved R2R pool. Missing assets, forged source identity, count, pair or hash errors remain hard failures.

Regex matches are source-quoted retrieval signals, not route facts or automatic KEEP/SPLIT decisions. The ranking sees no navigation score, outcome, evaluation partition label, GT or trace. Explicit dataset split, scene and path identity may form a Host-only exclusion key; these are not ranking features or model inputs. Fixed-Core overlap is reported, never silently removed. It records the real eligible candidate pool, excluded identities, per-slot ranking and projected Dynamic bytes/hash under the exact detail policy the compiler uses.

Host freezes this plan and the rules/templates before G0. G0/G1 reuse the Generator bundle; R0/R1 reuse the Reviewer bundle. Their active schemas and phase payloads remain distinct. Reviewer sees only source, candidate status/subtasks/issues and frozen English, not Generator's private audit. G1 may accept, partially accept or reject source-checkable advice; R1 can resolve an unsupported old complaint using unchanged candidate evidence. Host releases only the corresponding reviewed snapshot or follows the existing exact-source fallback.

## Reproduce and validate

Authoring needs the immutable Git evidence in a full-history checkout. Production requests use already committed assets and do not run authoring or Git transformations online.

```sh
python -B -m r2r_authoring.integrate --write
python -B -m r2r_authoring.build --write
python -B -m r2r_authoring.build --check
python -B -m r2r_authoring.test_expectations --write
python -B -m host.compile
python -B -m r2r_authoring.verify --isolation
python -B -m r2r_authoring.verify --refresh
python -B tools/verify_package.py
python -B -m r2r_authoring.regression
python -B -m r2r_authoring.smoke
python -B -m r2r_authoring.audit
python -B -m r2r_authoring.verify --refresh
python -B tools/verify_package.py
```

The integration guard accepts only its immutable parent, preceding reviewed integration or exact expected result and refuses concurrent unknown changes. The inherited test-expectation migration is an explicit previous-policy mapping; the detailed refinement tests independently check actual complete demonstrations, retained evidence and projection receipts. The terminal-approach capability test covers fixed Core plus Dynamic, rather than requiring a destination example in Dynamic to be incorrectly classified as an approach.

The CI publication stage checks the final changed-path allowlist and protected assets, creates a separate clean worktree, repeats compilation, integrity and full regression, and verifies the branch has not advanced before non-forced push. Worker processes must restart or use an explicit immutable snapshot after deployment; editing cached files during a task is not supported.

## Limits of the evidence

An inherited release-transaction test requires a companion `manage_release.py` outside this repository. Only that precise missing dependency is separately reported as unavailable and not counted as passed. Other failures remain fatal.

CI verifies structural/evidence integrity, actual prompt composition, deterministic selection, protected RxR behavior and scripted Host paths. It does not run a live semantic model or simulator. There is no new SR/SPL/nDTW improvement claim. Previously inspected tasks remain development/regression evidence. The next paired experiment must keep the model, images, history, Actor, STOP policy, roster and budgets fixed, and report both successful recoveries and newly introduced regressions.

Current detailed implementation and pending evidence are recorded in [R2R refinement report](R2R_REFINEMENT_REPORT.md) and `provenance/r2r_issue_ledger.json`.
