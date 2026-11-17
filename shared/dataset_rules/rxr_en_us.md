# RxR en-US shared semantic rules — v6

## Authority and scope

These rules apply only when the Adapter resolves the record to `rxr-en-us`. They refine how the v5 common semantic contract is applied to long, multi-sentence RxR instructions. They do not replace the v5 common contract, five-element Stage Audit, Handoff schema, evidence rules, Reviewer dimensions, L0–L6 checks, or output schemas. The original instruction is the only authority for route facts. No map, pose, image, trajectory, or environment truth is available to Generator or Reviewer.

Priority is: (1) source fidelity and no unsupported additions; (2) preserve action/condition/temporal/spatial semantics; (3) complete executable stages and supported handoffs; (4) useful segmentation; (5) concise wording. A lower priority must never override a higher one.

## 1. Reconstruct the complete route before considering cuts

Read the entire instruction, including later sentences, corrections, parentheticals, expected-state narration, and final completion wording. Build a private event sequence before choosing boundaries. Each event should distinguish: active navigation action; target/region; descriptive or expected observation; temporal trigger; spatial relation and its reference frame; quantity/ordinal; prohibition or persistent constraint; and completion/stop requirement.

Do not equate sentence boundaries with task boundaries. A sentence can contain several independent navigation objectives; multiple sentences can describe one tightly coupled objective. The output may split only after the event sequence and dependencies are understood.

## 2. Action, observation, target, and reference are different

- Navigation action: an instruction to move, turn, enter, exit, pass, cross, climb, descend, approach, return, stop, wait, stand, or otherwise change the agent's state.
- Target: the place, object, region, or spatial state the agent is instructed to reach or act upon.
- Reference landmark: an entity used to identify, orient, or disambiguate a target; it is not automatically a destination.
- Observation: something the instruction says the agent will see, notice, or find. It becomes an execution condition only when the source makes it a required trigger or selection cue.

Preserve the distinction between seeing and reaching, approaching and arriving, passing and entering, standing at a doorway and being inside, and a reference object and the actual target. Do not create a visit or stop merely because an object is described.

## 3. Bind later descriptions to the correct earlier target

A later clause may identify or disambiguate a target introduced earlier (for example, which of two nearby doorways is the bathroom). Attach the identifying description to the target-selection action before the agent must choose that target. Do not leave the description in a later stage where it arrives too late to guide selection.

Bind a description only when the complete source supports a unique referent. Preserve uncertainty when multiple referents remain plausible. Do not promote an adjacent object, a visual cue, or an expected observation into the destination unless the source explicitly makes it the goal.

## 4. Preserve temporal scope and event order

Interpret temporal relations by their semantic scope, not by word order alone:

- `before B, do A`: A precedes B. Do not infer that B is later required if the source only says to turn before entering.
- `after/once/when A, do B`: B is conditional on or follows A. Ensure A is completed before B starts. Do not move B ahead because it appears earlier in the sentence.
- `A until C`: keep the continuing action A bound to its actual termination event C. Do not separate C into a later stage that leaves A unbounded.
- `while/during/keep/stay`: preserve the constraint throughout exactly the source-scoped interval. Do not convert a local condition into a global one or drop it at a cut.
- `then/next`: preserve order, but do not infer a new stop or a new independent goal solely from the connective.
- Corrections: apply an explicit correction to its intended action only; do not execute the superseded wording.

A temporal phrase may describe a trigger, an endpoint refinement, or a separate later objective. Determine which event relation is supported before deciding whether it creates a boundary.

## 5. Resolve pronouns and route history globally

Resolve `it`, `there`, `that doorway`, `the same door`, and similar references against the complete instruction and event sequence. The candidate stage must identify the intended entity sufficiently for the action to be executable. Do not assume that a name introduced several stages earlier remains unambiguous after intervening similar entities.

A repeated location does not erase event history. If the source requires leaving a room, visiting another region, and returning, preserve all three events in order. Returning to a previously visited location is a new route event, not an already-satisfied endpoint. Preserve which doorway, side, route, or object is reused.

## 6. Preserve spatial relations and reference frames

For every left/right, ahead/behind, in-front-of, between, beside, across, through, past, around, and facing relation, identify what it is relative to and when it applies: initial orientation, orientation after a turn, maintained relation during motion, or endpoint-only relation.

A turn changes the egocentric frame. Do not carry an earlier left/right relation across a turn unless the source explicitly makes it persistent or the entity relation is world-relative. Distinguish `keep the sofa on your left as you cross` (a maintained process constraint) from `the table is on your left when you arrive` (an endpoint description). Do not silently change between, around, through, past, toward, and into.

## 7. Preserve ordinals, counts, and their origins

Keep the counting category and origin stable: second door is not second open door; third doorway on the left must be counted from the source-supported start and orientation. A stage boundary does not reset a count. If a count depends on a previously established corridor entry or direction, retain that anchor in the later stage's natural-language entry context. Never invent a new count origin.

Approximate quantities and vague descriptions remain approximate. Do not sharpen "a little", "near", "some", or "about halfway" into unsupported distances or exact thresholds.

## 8. Distinguish endpoint refinement from a new objective

A later phrase may refine the same movement's endpoint (for example, descend the stairs, about halfway down, and wait there). Keep it with that movement; do not create a false full-descent stage followed by a second descent or stop.

A genuinely new objective requires a distinct source-supported event after the prior objective is complete (for example, enter a room, then cross it to a separate target). A repeated stop/wait/stand phrase is not by itself proof of a second objective. Ask what source event requires additional movement between the two descriptions.

## 9. Conditions and alternatives

Preserve genuine conditional route alternatives and their outcomes. Do not turn `if`, `or`, or `otherwise` into two unconditional actions. A conditional observation such as "if you can see the door" is not necessarily a route branch; classify by its actual effect on action choice. If two branches converge to the same supported state, a later common stage may follow only when both outcomes establish the same required entry state. Otherwise keep the dependent route together or mark a genuinely source-level ambiguity.

Preserve prohibitions and negative constraints over their exact scope. A prohibition against entering the first door must not be generalized to all doors or omitted before the counted target.

## 10. Stage and handoff test

A proposed stage must be executable as a natural-language navigation instruction and auditable under the existing v5 five elements:

1. Entry: episode start or source-supported context/continuation.
2. Target: the actual local navigation target or state transition, not merely a nearby reference.
3. Process: all required ordered actions and route cues.
4. Ending: a source-supported event, bounded action, linked trigger/refinement, or final goal directive.
5. Conditions: all relevant temporal, spatial, count, branch, negation, and persistence constraints with correct scope.

For every boundary, compare the preceding stage's actual supported exit with the next stage's first unperformed action. The next stage may inherit a state only if the preceding text actually establishes it. Do not count the next stage's action as already completed in the prior stage. A boundary never implies a physical STOP.

## 11. Segmentation adequacy

Split when the source contains a completed, useful intermediate objective and a distinct next objective with a supported handoff. Keep tightly coupled maneuvers together when splitting would leave an action without its trigger, endpoint, reference frame, or necessary context. Do not optimize for a fixed number of stages or equal stage lengths. A long RxR instruction may need multiple stages, but length alone is not a reason to split.

## 12. Source uncertainty

First use full-context coreference and route reconstruction; then try a sensible regrouping or merge. Only if a route-critical referent, branch, or completion requirement remains genuinely ambiguous should the output become `needs_review` / `unresolved` under the existing contracts. Missing imagery, coordinates, metric distances, or simulator pose are ordinary grounding limitations, not automatically source ambiguity.

## Shared interpretation examples

- "You will see the open door at the end of the hall" is an observation cue unless a later action makes that door the selected target.
- "Stop at the restroom entrance; the fire extinguisher is next to you" makes the entrance the target and the extinguisher a reference.
- "Go down the stairs, about halfway, and wait" is one bounded descent ending at the halfway point, not a full descent plus a second task.
- "Turn left before entering the dining room and go into the open area" does not authorize a stop at the dining-room threshold or entry into the dining room.
- "Return through the same door" requires preserving the identity of the previously used door and the intervening route event.
