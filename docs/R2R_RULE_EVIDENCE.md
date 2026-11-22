# R2R evidence and regression requirements

This document maps the uploaded historical paired navigation results to the R2R-only semantic rules and examples currently implemented. It is an offline engineering review; it is not a runtime teaching template, and neither navigation outcomes nor ground-truth trajectories enter Generator, Reviewer, or retrieval.

## Observed paired behavior

The complete historical paired evaluation has 1,839 tasks, with 1,207 original-instruction successes and 1,212 enhanced-instruction successes. There were 131 recoveries and 126 baseline-success regressions, so net gains conceal large bidirectional variance.

| Final text mode | Tasks | Recoveries | Regressions | Net success |
|---|---:|---:|---:|---:|
| ASSEMBLED_MULTI | 1,051 | 110 | 90 | +20 |
| ASSEMBLED_SINGLE | 165 | 12 | 18 | -6 |
| BOUNDARY_ONLY | 206 | 9 | 18 | -9 |
| SOURCE_EXACT | 417 | 0 | 0 | 0 |

The multi-stage subset has positive net gains, so an unconditional KEEP or source-exact policy would discard a demonstrated capability. The single-stage and boundary-only losses motivate an edit-necessity check and caution about stage boundaries, not an unverified change to the shared Renderer. Per-episode failures can also reflect downstream visual and control behavior; these summary associations do **not** establish causal effects from any particular phrase or line break.

In the 183-task B2 analysis slice, original instructions succeeded in 122 tasks and the enhanced instructions in 117. Twelve failures were recovered and 17 baseline successes regressed. B2 remains strictly offline evaluation metadata, not a runtime Profile, retrieval feature, or prompt conditioning signal.

## Existing R2R specialization that preserves the useful behavior

The three R2R rule layers already implement event-role classification, coupled maneuvers, source-supported completion, distinct local targets, executable handoffs, downstream-condition binding, reference-frame ownership, exact terminal placement, and purpose-limited editing. They deliberately require *both* legitimate multi-goal SPLIT and coherent-maneuver KEEP. The fixed ten-case Generator Core includes coherent single-stage examples (G01, G03, G05), completed transitions followed by distinct local goals (G02, G04, G06, G07, G08, G09), and route-critical ambiguity (G10). Reviewer R04 and R06 contrast over- and under-segmentation. Reviewer R01/R08 contrast a valid target choice against an invented stop at an observation. These are authored semantic teaching cases, not official trajectory-alignment ground truth.

## Specific failure modes and why the Reviewer teaching needed repair

- Unnecessary rewriting must not become a material rejection purely because grammar or punctuation differs from the source. A newly invented command (for example, turning an *open doorway* attribute into an instruction to open the door) is different: it is a source-support defect.
- Entering a region is only a *candidate* boundary. A transit route that continues through the region may be one maneuver; a completed transition followed by a separate objective may be worth splitting. The final target and arrival condition must remain attached to the movement they govern.
- A bounded movement or later endpoint qualification must be bound to its actual action, not executed after the unbounded movement completes.
- Source requirements that remain literally present cannot be labeled *missing* simply because another source clause is corrupted. Findings must identify the particular altered requirement, and terminal STOP/WAIT must be represented consistently in coverage, stage checks, dimensions, and repairs.
- A REVISE teaching diagnostic cannot use the exact source text as its unchanged candidate and simultaneously claim a deictic or route change. Teaching errors are repaired in their authored candidate and audit fields; they are not new observations of navigation performance.
- A legitimate earlier crossing boundary does not justify isolating a subsequent WAIT as a new objective at the same endpoint. Flag the *specific* unnecessary cut, preserving the meaningful preceding transitions.

## Guardrails and evaluation

The active R2R selector keeps ten fixed Core examples, a source-conditioned complementary four-to-six Generator Dynamic selection, the exact paired Reviewer Dynamic cases, and two-to-three supplemental Diagnostics. This review changes no global ranking, actor interfaces, shared semantic contract, common prompts, Renderer, RxR rules, RxR templates, or RxR selection counts.

The new tests verify Reviewer teaching consistency against the actual candidate, requirement IDs, evidence quotes, unchanged source spans, terminal scope, and active protocol. They do not demonstrate improved model outputs or SR/SPL/nDTW. A valid navigation claim still requires an independently frozen model, tokenizer/chat template, visual input, Actor, STOP, environment and task roster; report paired recoveries, regressions, efficiency, fallbacks and uncertainty, reserving a source-disjoint held-out set.
