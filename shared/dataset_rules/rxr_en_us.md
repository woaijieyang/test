# RxR en-US semantic guidance

## Scope and authority

Apply only to `rxr-en-us`. The original instruction is the only source of route facts. The shared semantic contract, evidence requirements, five-element audit, handoff definitions, active schemas and bounded review/repair workflow remain mandatory. No image, map, pose, navigation result or evaluation partition is available to either semantic role. These rules refine interpretation; they do not introduce new output fields or decision types.

Priority: source-supported meaning and constraints; complete events and dependencies; supported stage handoffs; useful local objectives; concise wording. Neither a preferred stage count nor polished English can override a higher priority.

## 1. Read globally, group events before cutting

Read the entire instruction, including later target descriptions, false starts, corrections and final placement. Identify each action, target, reference landmark, expected observation, temporal trigger, frame, count, prohibition and completion condition. Assemble complete event units before proposing boundaries. A sentence can contain several objectives; several sentences can describe one event. Shortness does not imply KEEP and length does not imply SPLIT.

Split only after a supported intermediate completion when a distinct next objective and executable handoff provide useful focus. Keep a maneuver together when a cut detaches its approach, turn, count origin, trigger, endpoint refinement or maintained spatial relation. Do not create a STOP or an arrival to justify a boundary.

## 2. Preserve event identity across oral repetition

Distinguish continuation, restatement, endpoint refinement and genuinely new traversal. Repeated wording is not itself evidence of another lap, visit or turn. Do not introduce `again`, `another` or `a second time` solely because a phrase occurs twice. Conversely, preserve an explicit return, repeated visit and all intervening route events; sharing a place name does not make an event redundant. If the full source does not settle a route-critical distinction, preserve its uncertainty instead of choosing a new event history.

## 3. Apply corrections to the smallest supported scope

For `sorry`, `actually`, `I mean`, `or rather` and similar corrections, identify the exact action, target, direction or modifier being replaced. Execute the corrected meaning, not the superseded command. Do not erase unrelated preceding movements or constraints merely because they share a sentence with the correction. A correction of LEFT to RIGHT does not cancel the earlier room entry; a final top-of-stairs correction can cancel a proposed descent only when the complete source establishes that relation. Genuine uncertainty is not permission to guess.

## 4. Separate actions, observations and references

An object mentioned or expected to become visible is not automatically a destination. Seeing, approaching, reaching, passing and entering are different events. Classify `if you turn/look ... you will see ...` from the full instruction: it can explain a viewpoint, prescribe an action, or govern a real alternative. Do not automatically upgrade conditional observation to an unconditional turn or visit, and do not discard a turn that later text actually requires. Approximate quantity or descriptive `or` is not a route branch. Never use token occurrence alone to choose this interpretation.

## 5. Bind identifying descriptions without inventing observations

Attach uniquely supported later descriptions to the earlier target before its selection action. Do not create description-only stages or move a future observation into a claim about what has already been observed. Keep the target distinct from adjacent furniture, colors and other reference objects. When a later description could identify multiple entities and would change the route, retain the uncertainty. Target binding may change descriptive placement, not the required order of route events.

## 6. Preserve spatial relation ownership and temporal scope

For each relation, identify its subject, reference entity or frame, relation type, and the time or interval in which it applies. These are internal interpretation questions, not additional output fields. `The rightmost of two doors`, `a door to the right of both doors`, and `a door on your right` are not interchangeable. Agent path relative to a sofa is not the position of another object relative to that sofa. Keep between, beside, around, through, past, near, toward and into distinct.

A turn updates the egocentric frame. Do not carry a pre-turn left/right relation forward without source support. Do not turn an endpoint description into a maintained path constraint. Preserve final facing requirements as well as final location. Grammar repair must not silently decide an ambiguous spatial relation.

## 7. Preserve trigger, condition and count scope

Keep `A until C` bound to C as actually stated: seeing C is not reaching C. `After/once/when A, B` retains A's completion before B; do not execute A twice. `Before entering B, turn` does not itself authorize entering B. Preserve `while/keep/stay` for exactly its supported interval. Preserve prohibitions and real route alternatives, including branch-specific entry states before a common continuation.

A new stage does not restart ordinal counting. Keep the object category, origin, direction and previously counted events: second door is not second open door. Preserve approximate quantities. Do not sharpen near, a little or halfway into unsupported metrics.

## 8. Use supported entry states, not mandatory new entry sentences

Every stage requires an intelligible, supported entry state; it does NOT require a newly written `From`, `After` or `Inside` sentence. Prefer immediate, unambiguous inheritance of current pose or a uniquely established entity. Add the shortest source-supported anchor only when needed for count origin, changed frame, revisited entity, competing similar targets, or a still-active constraint. Never repeat a completed action as a new instruction simply to make a stage look self-contained.

For every boundary, compare the preceding stage's actual completion with the next stage's first unperformed action. A shared landmark name is not proof of arrival or entry. Necessary information must be recoverable from the actual ordered stage text; audit notes cannot repair omitted executable meaning.

## 9. Keep bounded movement and endpoint refinement intact

A final `one step inside`, `halfway down`, `near the foot of the bed` or facing clause can refine the same preceding event rather than create a new objective. Keep the refinement with that event when separating it adds no supported local objective. Do not infer a full descent before a halfway refinement, or arrival at an object after a bounded step toward it.

A bounded movement may itself establish a meaningful state for a distinct subsequent objective. Do not mechanically merge all short stages. Explicit intermediate stops remain intermediate; a boundary alone is not a physical STOP. Preserve the exact final spatial configuration, not just its destination noun.

## 10. Preserve source wording where it is already useful

Retain route-bearing wording unless an edit has a specific purpose: supported target-description binding, unique coreference, explicit temporal ordering, local correction, necessary entry information, or a real semantic defect. KEEP can retain exact source text; it can also perform a necessary local reassembly. Do not rewrite the whole route merely for grammatical polish or uniform style. Ordinary synonymous wording is not itself a defect and does not justify a blocking review finding.

## 11. Bidirectional audit and local repair

Check both directions: every active source requirement survives, and every added executable requirement has source support. Pay particular attention to added turns, entry, repeat traversal, arrival, resolved ambiguity and persistent constraints. The five audit elements must describe actual stage text, with exact source and candidate evidence. Check all adjacent handoffs and the complete final route.

Repair the affected text and its necessary dependencies only. Preserve unaffected executable wording and order, then regenerate consistent audits and handoffs. A reviewer finding is evidence to inspect, not an automatic rewrite command. The reviewer judges semantics, not navigation scores; PASS is not a prediction of navigation success.

## 12. Source uncertainty

Use full-context interpretation and sensible regrouping first. Only route-critical ambiguity remaining in the source can justify the existing needs_review/unresolved path. Missing visual grounding, map, coordinates or model capability is not automatically source ambiguity. Do not output a guessed partial route.
