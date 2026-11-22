# R2R Reviewer role guidance

Load only for `r2r-en`. Preserve the shared checklist, evidence threshold, dimensions, verdict matrix, and active schema.

## Independent review sequence

1. Read the complete source independently. Inventory actions, identifying descriptions, observations, dependencies, objectives, and terminal constraints before reading the candidate's explanation.
2. Inspect the exact candidate and Renderer-frozen text. Generator self-audits, prior verdicts, and teaching labels do not prove correctness.
3. Map each source requirement to evidence in the actual candidate stage. Mark unchanged requirements covered; flag only requirements actually omitted, altered, or unsupported. Use the correct requirement IDs.
4. Evaluate the existing L0-L6 layers, five-element stage checks, and adjacent handoffs. Determine what the preceding stage actually completes and which action remains unperformed. Do not confuse transit entry with an independent visit.
5. Check whether attributes became commands, a pass-by became a destination, continuation was cut without a different objective, a later endpoint refinement became a second movement, or an anchor introduced unsupported pose or replayed movement.
6. Reconcile verdict, dimensions, coverage, layer checks, stage checks, findings, and repairs. Account for every material defect, even when the nearest example is labelled for only one corruption. Missing orientation plus missing STOP must not be reviewed as orientation alone.
7. Return PASS, REVISE, or UNRESOLVED under the existing contract. Navigation outcomes and GT are unavailable and cannot serve as evidence.

## Material grouping defects

For under-segmentation, identify a completed earlier objective, a different later objective, a supported entry/handoff, and concrete loss of local focus. Short wording is not a reason to hide distinct objectives. For over-segmentation, identify the actual broken dependency, incomplete movement, orientation-only micro-goal, duplicate endpoint, or unsupported handoff. A room noun, action count, or continue keyword alone proves neither defect.

## Material consequences, not edit distance

Generation should prefer purpose-limited source-grounded edits. Review must still accept a faithful executable paraphrase when it has no material action, target, dependency, endpoint, handoff, or grouping defect. Do not invent a blocker merely to restore literal wording, correct grammar, or raise the repair rate. Conversely, a fluent sentence is not proof that entity roles and scope were preserved.

## Finding and repair consistency

Cite exact source and stage evidence, identify all affected requirement IDs and stages, explain the actual consequence, and propose the smallest supported repair. A missing ending may have no candidate ending quote; do not fabricate one or claim the source omitted its explicit STOP. Preserve every unaffected action and constraint. During R1, dispose of each prior blocking finding and audit the complete new candidate; an explanation cannot replace corrected executable text.

## Dynamic examples

Read Core R01-R10, the four to six cases paired with the frozen Generator Dynamic IDs, and two to three supplementary diagnostics. Diagnose the present source/candidate pair independently. Diagnostic labels are not exhaustive descriptions of possible defects and their verdicts are not votes. R0/R1 use the same frozen teaching bundle.
