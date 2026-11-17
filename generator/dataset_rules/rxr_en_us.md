# Generator guidance — RxR en-US v6

Use the shared RxR rules together with the unchanged v5 Generator prompt, acceptance rules, repair rules, and active output schema. This file gives the RxR-specific work order; it does not create a new output contract.

## Required reasoning order

1. Read the complete original instruction once without segmenting it. Re-read later clauses before committing to any earlier target or boundary.
2. Reconstruct the ordered route events: initial context; each movement/action; each target; observations/reference landmarks; temporal triggers; spatial frames; counts/ordinals; constraints/prohibitions; intermediate and final completion events.
3. Resolve references and late descriptions globally. Attach target-identifying information before the action that requires target selection. Preserve unresolved ambiguity rather than guessing.
4. Bind temporal and spatial scope. Determine whether each later clause is a trigger, continuation, endpoint refinement, separate objective, branch, or descriptive observation.
5. Group coupled events into executable local navigation phases. Keep a maneuver together if a cut would detach its turn, approach, threshold condition, endpoint, count origin, or maintained spatial constraint.
6. Consider a boundary only after the preceding event has a source-supported completion and the next phase has a supported entry. A new stage must begin with a meaningful entry anchor in its actual natural-language text; an audit-only carryover cannot repair missing executable wording.
7. Write the ordered English subtasks. Preserve source semantics and natural instruction style. Make the local target and its completion event clear without inventing STOP, WAIT, distance, arrival, entry, or posture.
8. Complete the existing v5 Stage Audit for every stage and Handoff for every adjacent pair. Source quotes must be exact original substrings; candidate quotes must be exact substrings of that stage.
9. Run the two-way check: every active source requirement appears in the executable text, and every added executable requirement is supported by the source. Re-read the complete output as one route and inspect count origins, frame changes, repeated visits, and all handoffs.

## Boundary decision policy

Prefer SPLIT when a completed intermediate objective is followed by a distinct, source-supported objective and the new stage can start from the prior stage's actual endpoint without guessing. Prefer KEEP when the clauses form one continuous maneuver, a later description only identifies/refines an earlier target, or the cut would make the next stage depend on unspoken history. Use NEEDS_REVIEW only for unresolved source-level ambiguity after global resolution and sensible merging.

Do not preserve an awkward original sentence merely to avoid editing. You may make minimal grammatical changes, resolve a uniquely supported pronoun, move a later target description forward to its selection point, and make source-supported order explicit. Do not paraphrase beyond what is needed to make the task executable.

## RxR-specific failure checks

Before returning `ok`, explicitly check:
- later target description arrives before the relevant selection action;
- "you will see" has not become a required visit or stop;
- a reference landmark has not replaced the true target;
- a room/doorway entry has not been inferred from merely approaching or seeing it;
- a later endpoint refinement has not become a second movement;
- an ordinal has not restarted at a new stage;
- left/right/facing is evaluated in the correct temporal reference frame;
- a return/revisit includes its intervening route history;
- an intermediate STOP/WAIT is preserved but not promoted to terminal completion;
- a final goal directive has not been strengthened into unsupported arrival or STOP;
- every next-stage entry is anchored to the previous stage's actual exit;
- the five elements are reflected in the natural-language stage, not only in audit metadata.

If no meaningful split is supported, return one coherent stage. Do not split just to demonstrate decomposition. If the source cannot support a complete route, return the existing `needs_review` structure with no partial stages.
