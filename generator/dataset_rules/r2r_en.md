# R2R Generator role guidance

This guidance is loaded only when the Adapter Profile is \`r2r-en\`. It supplements the shared Generator prompt and semantic contract; it does not replace the active output or repair schema.

## Required decision sequence

1. Read the complete original instruction as one route. Do not segment by sentence, punctuation, verb count, route length, or landmark count.
2. Inventory the ordered route events: initial context, movement, turns, landmarks, room/doorway/stair transitions, target choices, temporal and conditional relations, bounded movement, prohibitions, and terminal directives.
3. Assign each referenced entity its source-supported role: pass-by landmark, orientation reference, region anchor, or final target. Preserve multiple roles only when explicitly supported.
4. Assemble coupled local maneuvers before evaluating boundaries. Keep each turn with the movement it enables; keep approach/turn-at/crossing together when no completed state separates them; keep a landmark pass with the route segment it constrains.
5. Evaluate every candidate boundary against all four requirements: a completed source-supported prior event, a distinct next objective, an executable next entry, and a concrete local-focus benefit. Reject any boundary that depends on an invented stop, heading, distance, arrival, or intermediate pose.
6. Choose KEEP, SPLIT, or the minimum necessary REASSEMBLE based on the current source. A KEEP decision must preserve the complete route as an executable stage; a SPLIT decision must preserve every active dependency and produce a valid handoff. Use the existing needs_review path only for unresolved route-critical ambiguity in the Source.
7. Write the least text necessary. If the source is already executable and complete, preserve its wording and layout. Do not grammar-polish, paraphrase, expand context, or repair likely typos merely to improve fluency.
8. Complete the existing five-element audit for every stage and the existing handoff audit for every adjacent pair. The natural-language stage text must itself express the executable process; audit metadata cannot replace missing instructions.
9. Read the final Candidate from beginning to end. Verify event coverage, order, target identity, ordinal origin, direction frame, temporal scope, negation, bounded movement, terminal placement, and absence of repeated completed actions.
10. Return only the existing Generator schema. Do not add fields, confidence scores, dataset-specific output formats, or a second plan.

## R2R high-risk cases

- A compact two-sentence route may be one continuous maneuver. Do not split a turn/pass/turn/stop chain without a supported completed intermediate state.
- A room exit or entry can support a cut only if it is complete and a distinct next objective follows.
- A landmark used for passing is not automatically a destination. Keep its spatial relation attached to the movement.
- An ordinal target must retain its counting object, origin, and region after any cut.
- A left/right relation must retain the frame that defines it. A completed turn changes the current heading; do not carry the old frame forward.
- Stair flights, landings, step counts, and midway constraints must remain attached to the correct stair segment.
- A later clause may refine the same endpoint rather than create a second objective. Preserve that scope.
- Negative and conditional route constraints must remain active across all affected stages.
- A grammar or transcription irregularity is not permission to guess a different route.

## Dynamic examples

Read all ten fixed R2R Generator Core examples in G01-G10 order before the selected R2R Dynamic examples. Core is unconditional and cannot be replaced. Dynamic cases are retrieved by R2R-only source features and provide complementary examples; they do not vote on the current decision. A cue such as doorway, stairs, left/right, or stop never directly implies SPLIT or KEEP.

During repair, reassess each Reviewer finding against the complete immutable Source. Accept only source-supported changes, reject unsupported suggestions with evidence, protect already-correct requirements, and return the complete Candidate under the existing repair schema.
