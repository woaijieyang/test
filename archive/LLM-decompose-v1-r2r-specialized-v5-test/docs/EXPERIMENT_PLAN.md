# Experiment plan for final-best-v1

## Phase 0 — Freeze and identify

Freeze the original v1.3 prompts/schema, the previously tested p1/v2 prompt hashes, and final-best-v1 hashes separately. Fix the actual model and effort for Generator and Reviewer. Do not attribute a combined model/schema/template/role change to a single prompt edit.

## Phase 1 — Generator quality

Use a frozen development sample with short and long instructions. Blindly label fidelity, closure/handoff and segmentation adequacy. Include cases analogous to: multiple reached waypoints with separate turns (B-98); a compact kitchen-crossing/turn/stop maneuver (A-1205); route-side ownership (A-1148); later turn-at cue binding (A-630/B-1464); terminal `toward` vs intermediate `toward` (B-19/B-137). The casebook labels are diagnostic evidence, not navigation gold labels.

## Phase 2 — Reviewer diagnostic value

Run old/new Reviewer on the same frozen candidates with blinded order. Measure true-defect detection, false positives, missed C10 boundaries, exact quote accuracy, actionable repair quality, advice acceptance/rejection and net repair. Do not optimize for pass rate, number of findings or comment length. R1 must be fresh-context and not see R0 or G1 explanations.

## Phase 3 — Format-only ablation

Freeze semantic candidate and reviewer-approved snapshot. Compare LF and SPACE stage separators as separate registered arms. Preserve source prefix/suffix and all stage text. A reviewer receipt for one rendered hash cannot approve a different rendered hash; format-only ablation is an experiment arm with its own identity.

## Phase 4 — Navigation

Keep the existing AwareVLN visual input, Reason/Act, STOP, last_reasoning, model, budget and environment fixed. Compare full-denominator paired results, recoveries, regressions, SR/SPL/nDTW, NE, steps/path, and common-success path efficiency. Preserve all fallback and technical-failure cases. Capture first token/action divergence with a fixed prefix if studying format sensitivity.

## Phase 5 — Held-out validation

Use scene/path-disjoint held-out instructions that were not used to choose prompt wording or templates. Do not select per-episode winners. Report confidence intervals and all denominators. No result is attributable to final-best-v1 until this plan has been run.
