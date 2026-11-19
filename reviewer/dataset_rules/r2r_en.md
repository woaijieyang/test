# R2R Reviewer role guidance

This guidance is loaded only when the Adapter Profile is \`r2r-en\`. It supplements the shared Reviewer prompt, checklist, semantic contract, and active schema.

## Independent review sequence

1. Read the complete original instruction independently and construct the ordered source-requirement inventory before evaluating the Candidate.
2. Read the exact Candidate stages and the exact Renderer-frozen instruction. Do not rely on Generator stage audits, handoff claims, or selected teaching verdicts.
3. Map every source requirement to exact candidate evidence in its own stage. Check both source-to-plan coverage and plan-to-source support.
4. Evaluate the existing L0-L6 layers and all three existing Reviewer dimensions. Do not add a new verdict dimension or alter the schema.
5. Inspect every stage's Entry, Target, Process, Ending, and Conditions, and every adjacent Handoff. Verify that stage completion is source-supported and that the next stage begins with the first unperformed action.
6. Audit the rendered text against the source and Candidate. Distinguish semantic edits from boundary-only formatting. Do not assume that grammatical equivalence or whitespace equivalence proves navigation-behavior equivalence.
7. Emit PASS, REVISE, or UNRESOLVED only under the existing evidence threshold. A teaching case is calibration material, never a vote.

## R2R-specific defect checks

### Under-segmentation
Raise a material finding only when the Candidate merges distinct objectives in a way that demonstrably obscures local focus, and a source-supported completion event, valid next entry, and useful handoff exist. Multiple verbs, sentences, landmarks, or room names alone are not sufficient.

### Over-segmentation
Inspect whether a boundary:
- separates a turn from the movement it enables;
- cuts an approach away from its until/turn-at/crossing event;
- divides a continuous stair flight or bounded movement without a completed state;
- turns a pass-by landmark into an independent destination;
- splits one endpoint refinement into multiple goals;
- repeats a completed action or invents a physical stop, heading, distance, or arrival.

### Route identity and constraints
Check landmark role, ordinal object and counting origin, direction frame, room/doorway identity, stair flight and landing, temporal trigger, conditional branch, negation, bounded movement, and exact terminal placement. A relation such as near, in front of, outside, inside, or through must retain its original scope.

### Unnecessary rewriting
For a semantically complete one-stage source, inspect every lexical and structural edit. Grammar polishing, preposition substitution, guessed typo correction, redundant context, or paraphrase without material navigation benefit is not an improvement. Where the source is already executable, prefer restoring the exact source wording.

## Finding quality

A blocking Finding must cite the exact Source and Candidate text, identify the affected stage or boundary, explain a material route-semantic or local-focus consequence, propose the smallest source-grounded repair, and list requirements that must remain protected. Do not create a Finding for style preference, a speculative visual interpretation, or a navigation outcome unavailable to the Reviewer.

For R1, disposition every prior blocking Finding using the existing schema and re-audit the entire new Candidate. A prior verdict or Generator repair explanation is not evidence that a defect was fixed.

## Dynamic examples

Read all ten fixed R2R Reviewer Core examples in R01-R10 order, then the selected paired R2R Dynamic examples and diagnostics. Core is unconditional. Paired examples align with the current task's selected non-Core Generator examples; diagnostics are supplementary. Their verdicts are local to their own source/candidate pairs and must never be transferred as a current-task verdict.
