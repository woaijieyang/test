# Reviewer guidance — RxR en-US

Use the shared RxR rules together with the shared Reviewer prompt, checklist, output schema, and L0–L6 protocol. Review the complete route independently from the original instruction and actual candidate text. Do not use the Generator's Stage Audit as proof and do not copy a teaching example's verdict.

## Required audit order

1. Read the entire original instruction and reconstruct its route events, including late descriptions, conditions, corrections, reference frames, repeated visits, and final state.
2. Read the complete candidate subtasks in order. Treat the stage strings as the executable plan; audit fields cannot repair omissions in those strings.
3. Build event-level source coverage. Each meaningful action, target identity, direction, ordinal/count, condition, prohibition, intermediate stop, and terminal requirement must map to actual candidate text. A source quote alone does not prove execution.
4. Check semantic dependencies: temporal order, until endpoint, before-entry scope, while constraints, conditional branches, pronoun references, target-description attachment, count origin, and route history.
5. Independently audit each stage's Entry, Target, Process, Ending, and Conditions. Distinguish actual navigation targets from reference landmarks and observations. Check that every element is evidenced by the corresponding candidate stage.
6. Check every Handoff by comparing what the preceding stage actually completes with the next stage's first unperformed action. A shared place name is insufficient if the required transition, orientation, count origin, or target identity is missing.
7. Check grouping. Identify both over-segmentation (a cut detaches a coupled action or condition) and under-segmentation (a completed independent objective is buried in a long phase and harms useful focus). Do not require a split solely because a sentence is long or contains several verbs.
8. Read the complete candidate as one route. Verify source-to-candidate coverage and candidate-to-source support, then apply the existing Verdict Gate and L0–L6 schema.

## Evidence and finding quality

A blocking Finding must cite exact source evidence and exact candidate evidence from the actual affected stage(s). For a handoff issue, candidate evidence may cite both the preceding exit and next entry even when the minimal repair target is only the next stage. Explain the concrete execution consequence and specify a minimal source-faithful repair. Do not report a style preference as a defect.

Do not mark a stage as a gap merely because it inherits an immediately established endpoint or entity. Conversely, do not accept a stage that starts from a location, orientation, count origin, or completed event that the preceding stage never established. A carryover note is not executable evidence.

## RxR-specific false-positive controls

- Do not treat an expected observation as a new navigation goal unless the source requires acting on it.
- Do not mistake a reference landmark for the target.
- Do not require a physical STOP at every boundary.
- Do not treat "enter", "exit", "reach", "pass", "stand", or a bounded movement as lacking an ending merely because the word STOP is absent.
- Do not split an endpoint refinement into a second visit or second movement.
- Do not reset ordinals at stage boundaries.
- Do not carry egocentric left/right through a turn without source support.
- Do not erase repeated route events because the final location matches an earlier location.
- Do not force a multi-stage decomposition when one complete stage is more faithful.
- Do not force KEEP when the source contains multiple completed, independently executable objectives.

## Verdict discipline

Use the active Reviewer schema and verdict semantics only. PASS requires complete source coverage, no unsupported addition, supported five-element stages, supported handoffs, and no material segmentation defect. REVISE is for candidate-created omissions, alterations, unsupported additions, or repairable boundary/handoff errors. UNRESOLVED is only for a route-critical ambiguity in the source that remains after full-context resolution and sensible regrouping. Missing images, maps, coordinates, or pose do not by themselves justify UNRESOLVED.
