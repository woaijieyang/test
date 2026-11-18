# Final-best-v1 shared acceptance contract (Generator = Reviewer)

This is the single semantic source of truth for both roles. Dataset profiles may select source parsing and format metadata; they may NOT select different route semantics. Both roles use this exact contract and the same C01–C12 checklist.

## Priority
1. Preserve source-supported route requirements and event dependencies.
2. Preserve target identity, event order, relation ownership, viewpoint, count origin and condition scope.
3. Assemble complete local execution processes with supported entry and completion/terminal objective.
4. Split at useful, source-supported boundaries without fragmenting coupled actions or burying distinct objectives.
5. Make the minimum source-grounded wording change.

## Five semantic properties of each stage
- Entry context: actual starting context or supported continuation from the previous intended exit.
- Prescribed process: all required actions/events in order.
- Target and identifying information: target and attributes needed to select it.
- Completion/terminal objective: explicit event, bounded action, linked trigger/refinement, or final target-directed command.
- Conditions/constraints: time, prohibitions, alternatives, count, reference frame, ongoing relation and final pose.

These are meanings, not mandatory literal fields or separate sentences. Do not invent missing elements. A valid stage can contain several verbs and sentences; one stage can also be the right result for a compact, indivisible maneuver.

## Five dependency families
- `until`: bind the continuing action to its termination condition.
- `after/once/when/then`: preserve event order and trigger ownership.
- `before`: preserve temporal/spatial meaning; do not infer the later event unless stated.
- `while/keep/stay`: preserve the full scope of an ongoing constraint.
- `if/otherwise/either/or`: preserve alternatives; do not serialize mutually exclusive branches.

Also preserve explicit corrections, conjunctions, negation, ordinals, count origin, repeats/returns and spatial relation ownership.

## Boundary legality and usefulness
A useful boundary requires a supported previous exit, a supported next entry, a distinct next objective/decision focus, and no loss of condition, identity, count origin, reference frame or same-event refinement. A boundary is not a physical stop. Do not split every sentence, verb or landmark; do not merge multiple clearly separable legs just to avoid segmentation. A short route may contain multiple local objectives. A multi-action approach-turn-enter-stop maneuver may be one coherent stage.

## Completion evidence taxonomy
- `explicit_event`: source explicitly states a location/action event such as reach, pass, enter, stop, wait or stand at/beside/between.
- `bounded_action`: source bounds the action, e.g. a number of steps or halfway down.
- `linked_trigger_or_refinement`: a later clause uniquely closes/refines the same earlier movement.
- `terminal_goal_directive`: the final source instruction is a target-directed command such as “walk toward the front door”, with no later route action depending on arrival. This is an executable terminal objective but is NOT proof of arrival, crossing or stopping.
- `unspecified`: after reattaching context or merging, the source still does not support the intermediate completion/handoff required by the candidate.

Do not strengthen `toward` into `reach`, `enter` or `stop at`. A final terminal approach may remain as stated; an intermediate approach followed by a later event must be bound to that event or merged. A target noun alone is not completion evidence.

## Source evidence hierarchy
- S1: explicitly stated in the source.
- S2: uniquely recoverable from the complete source (e.g. a later turn-at cue closes an approach, or a later phrase refines the same descent).
- S3: local grammatical repair that does not select a different route or manufacture a completion.
- S4: assumed layout, model imagination, GT, another episode, navigation score or outside route knowledge — prohibited as route evidence.

## Three independent acceptance dimensions
- Fidelity: same active route requirements, no omissions or unsupported additions.
- Closure/handoff: every stage has supported process and completion/terminal objective; every adjacent transition is executable from the prior intended exit.
- Segmentation adequacy: useful independent local objectives are separated; tightly coupled maneuvers are not fragmented.

A missed useful cut may be a segmentation-adequacy issue while fidelity remains pass. Do not relabel a granularity issue as a route-semantic contradiction. Style preferences and alternative valid stage counts are not findings.

## C01–C12 shared checklist
C01 coverage of all active movements/events/cues/waits/returns.
C02 no unsupported additions or strengthening.
C03 order, event identity, refinements, corrections and repetitions.
C04 condition ownership and scope, including alternatives and logical operators.
C05 target-identifying descriptors available before target selection.
C06 spatial relation owner, reference object, viewpoint and time.
C07 coreference, entity identity, count class and count origin.
C08 complete stage process and correct completion basis.
C09 previous-exit / next-entry handoff and carried state.
C10 both over-fragmentation and distinct objective left buried.
C11 intermediate stops and final position/orientation.
C12 actual final English contains all requirements and no audit/editorial leakage.

Both Generator and Reviewer must use this checklist. Generator uses it silently before output and when independently evaluating review advice. Reviewer uses it for layered evidence-based audit. Neither role may invent route facts to satisfy a checklist item.
