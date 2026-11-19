# R2R Fixed Core — Independent Semantic Review Record

**Scope:** R2R English fixed Core, Generator G01–G10 and Reviewer R01–R10, plus the source records directly backing the promoted Reviewer Core cases R02/R08.

**Method and limitation:** Two separately structured model-assisted audit passes were recorded. Pass A checked source-to-candidate fidelity, event identity, target/ordinal/condition scope, unsupported additions, and abstention evidence. Pass B independently checked KEEP/SPLIT boundary validity, stage completeness, Handoff support, reviewer finding locality, and transfer-rule generality. A reconciliation pass compared disagreements and checked the actual source/template JSON. These are independent audit passes, not two human annotators or a human-adjudicated gold standard. Human double annotation remains required before treating the labels as research ground truth.

## 1. Generator Core

| Template | Authored decision | Pass A: source fidelity | Pass B: boundary / handoff | Reconciliation |
|---|---|---|---|---|
| G01 | KEEP | PASS | PASS | Keep the coach pass-by, preparatory left turn, and stair continuation together; no separately completed intermediate objective. |
| G02 | SPLIT | PASS | PASS | Three supported objectives: office/doorway crossing, hallway-to-room entry, and circular-table approach. The source's obvious transcription errors are repaired minimally; no scene fact is added. |
| G03 | KEEP | PASS | PASS | The between-landmarks movement, turn, bounded three-step ascent, and wait remain one coupled route; do not invent an intermediate stop. |
| G04 | SPLIT | PASS | PASS | The chandelier/window observation is a reference cue, not a destination; the doorway crossing completes the first transition, followed by a hallway/table/security-box route. |
| G05 | KEEP | PASS | PASS | Multiple verbs and turns do not establish an independent completed target; retain the continuous entranceway-to-doorway maneuver. |
| G06 | SPLIT | PASS | PASS | Entering the lobby establishes a supported region state; the stairway and dining-hall transition form the next objective. |
| G07 | SPLIT | PASS | PASS | The dining-table pass-by is complete before the stair ascent; the third-tile ordinal and top-step origin remain attached to the terminal stage. |
| G08 | SPLIT | PASS | PASS | The expected chandelier/table observation remains orientation context; the far-wall doorway is approached and crossed before the hallway/room stage. |
| G09 | SPLIT | PASS | PASS | Stair descent and right turn establish a completed transition; the later bench approach retains the 'once you reach' trigger and wood-between-bench/carpet placement. |
| G10 | NEEDS_REVIEW | PASS | PASS | 'Pack exit' is route-critical and not uniquely resolvable from the instruction. No speculative partial route is emitted. |

**Generator conclusion:** No source-fidelity or handoff blocker was identified in the ten current authored outputs. The Core has both KEEP and SPLIT demonstrations and one explicit source-level abstention case. The six-vs-three SPLIT/KEEP distribution is descriptive, not a target ratio; do not rebalance it mechanically. G01/G05 and G02/G06 contain related patterns but teach different boundary conditions and should not be deleted solely as duplicates.

## 2. Reviewer Core

| Template | Expected verdict | Pass A: finding validity | Pass B: review locality / transfer | Reconciliation |
|---|---|---|---|---|
| R01 | PASS | PASS | PASS | Candidate preserves left-turn orientation, far-wall door identity, approach/crossing, hallway traversal, and destination-room entry. |
| R02 | REVISE | PASS | PASS | 'first door on your right' changed to 'next door on your right'; this is a route-changing ordinal defect. Source metadata repaired; trajectory ID remains explicitly unknown. |
| R03 | PASS | PASS | PASS | The coupled pass-by/turn/stair-ascent/stop route remains one stage; no false split. |
| R04 | REVISE | PASS | PASS | The isolated 'Turn left' stage has no independent target or useful local objective; merge it with the stair ascent and explicit stop. |
| R05 | PASS | PASS | PASS | The dining-table pass-by supports the next stair/entryway objective; the third-tile ordinal remains attached to the terminal movement. |
| R06 | REVISE | PASS | PASS | The single stage collapses completed office/doorway/hallway-room transitions and the separate circular-table approach; the issue is grouping, not source coverage. |
| R07 | REVISE | PASS | PASS | The candidate assumes hallway entry but omits the source-required entry into the hallway to the slight right; this is a genuine source-coverage and Handoff defect. |
| R08 | REVISE | PASS | PASS | The candidate promotes an expected chandelier observation into a terminal stop and omits the far-wall door approach/crossing and subsequent room entry. Source metadata repaired. |
| R09 | PASS | PASS | PASS | The 'once you reach' trigger remains attached to the bench-relative stop/stand placement; the stair descent/right turn is a supported prior transition. |
| R10 | UNRESOLVED | PASS | PASS | The source itself contains an unresolved route-critical exit referent; the inactive empty Candidate correctly teaches abstention, not stage review. |

**Reviewer conclusion:** The Core contains hard PASS, source-fidelity REVISE, over-/under-segmentation REVISE, premature-Handoff REVISE, and source-level UNRESOLVED examples. Findings are localized to the affected requirement/dimension and do not convert stylistic preferences into blockers.

## 3. Provenance audit and corrections

The audit covered all 20 R2R fixed Core files. Every Core source record is marked `val_seen`, has record and episode identity, and now carries an explicit `scan_id` when a source `scene_id` is available. The scan value is derived only from the stored scene path; it is not inferred from instruction wording.

- **R02 / source R2R-DIAG-01:** recovered the val_seen viewer row for record/episode 37. The source viewer identifies scan `D7N2EKCX4Sj`; `scene_id` is now `mp3d/D7N2EKCX4Sj/D7N2EKCX4Sj.glb`. The inspected viewer row does not expose a trajectory ID, so `trajectory_id` remains null and the source key uses the scan identifier. No trajectory is fabricated.
- **R08:** restored the complete val_seen source identity from the matching R2R-REV-004 record and the R01 contrastive case: record/episode 4, scan `E9uDoFAP3SH`, trajectory 93. `split` is now the actual source split (`val_seen`); curation is represented in provenance, not misused as a dataset split.
- **R02's paired provenance source R2R-DIAG-01:** repaired to the same source identity as R02.
- **Other Reviewer Core records:** R01, R03–R07, R09 and R10 already contained record/episode/scene identity; missing explicit `scan_id` values were normalized from their scene paths. No absent scene/trajectory values were guessed.

## 4. Remaining evidence boundary

This review is a source-grounded model audit of the authored examples, not independent human annotation and not a navigation evaluation. The Core files explicitly remain curated teaching targets, not official subtask labels or trajectory-verified ground truth. Before publication claims, obtain two independent human annotations on a frozen sample, adjudicate disagreements, and measure Generator boundary accuracy and Reviewer defect precision/recall on held-out instructions.
