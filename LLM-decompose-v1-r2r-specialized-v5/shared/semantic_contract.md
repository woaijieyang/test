# Shared semantic acceptance — roles-repair-1
This exact file is compiled into G0, G1, R0 and R1. There is one standard for R2R/en and RxR/en-US. Dataset selection changes examples, not truth conditions. The instruction is the only route evidence; examples teach editing, never facts about a new building. No GT, map, image, observed progress or score is available.

## Priority and execution setting
Keep source meaning and dependencies; build a complete local process; make handoffs interpretable; separate useful objectives; minimize rewriting. This experiment sends ALL stages together as ordinary English, separated by the existing renderer. It does not switch goals online or reset state. Stage boundaries must still support local focus. Never impose a fixed count, sentence length, one-verb-per-stage rule or short-instruction KEEP rule.

Five meanings are required where the source supplies them: (1) entry and relevant reference state; (2) complete prescribed process; (3) target identity and selection cues; (4) supported ending or faithful final directive; (5) applicable conditions, count origin, viewpoint and continuing restrictions. These are not five printed labels or five extra sentences. Do not invent missing world facts to fill slots. A start with no named room uses the actual episode start, not an invented location.

## The decisive boundary test: retain, bind, or merge
A cut needs both a supported prior outcome and a genuinely useful next objective. First assemble each coupled local maneuver; only then choose cuts. Do not separate an approach from its until/turn-at endpoint, an around movement from a direction whose frame that movement establishes, or a target choice from its later description.

**Retain inherited state when enough.** Ordinary current pose and one unique immediately selected entity can carry over. A stage that reaches the base of a single selected staircase can be followed by 'Ascend the stairs until the top step. Halt here.' No repeated 'From the base' is required. Similarly, 'Go through that door' can follow identifying the door without claiming the agent already reached it. A normal forward movement starts in the current pose; do not demand a preamble solely because there was a preceding turn.

**Bind a critical dependency in the actual English when needed.** An ordinal choice after an exit/turn, a right/left doorway selected from a newly entered region, or a next-turn trigger that depends on the prior maneuver needs a short source-supported anchor when otherwise its counting origin or frame is left outside the local instruction. For example, 'After exiting the kitchen and turning right, go down the hall ... second on the right' names the existing event rather than ordering a second exit/turn. 'Inside the bedroom, turn left ...' names the intended entry without asserting sensor-confirmed completion. Audit notes are not substitutes for these words. Use the minimum distinguishing context, not a recital of all history.

**Merge when the prior outcome is not specified enough.** 'Walk around the sofa, then walk straight at the island table' should remain one coupled maneuver when the source gives no independent side/heading endpoint for the around movement. An invented 'at the far side' or 'facing the island' is not a repair. If an anchor would assert an unsupported end of the first stage, move the boundary or merge instead. 'Then' proves order, not a unique completed pose.

Do not turn these examples into keyword tests: a directional word does not automatically require an anchor; a named object does not automatically make a valid boundary. The requirement is an evidenced dependency that affects execution or local target selection. Source-supported alternatives in granularity are allowed.

## Ending taxonomy — never force arrival
`explicit_event`: source prescribes reaching, passing, entry, placement, a stop/wait, or identifying an object through a stated condition. Identifying/seeing is NOT arriving.
`bounded_action`: a specified step count, halfway movement, or requested turn finishes that action without a new STOP or invented exact angle.
`linked_trigger_or_refinement`: a later clause uniquely closes/refines the SAME action, e.g. the halfway limit on a descent or 'at the doorway turn left' on its approach.
`terminal_goal_directive`: only the LAST stage may preserve a final target-directed approach with no stated arrival/stop distance and no later action dependent on arrival. 'Walk towards the center island with cushioned bar stools' stays an approach, not 'reach and stop'. This is a faithful executable directive with an unspecified physical stopping rule, NOT a closed-loop arrival certificate. The report's ending text must say that limit rather than inventing completion.
`unspecified`: the proposed intermediate cut has no support for the outcome the next stage needs, or genuine source ambiguity remains after sensible regrouping. Repair a bad cut first. A valid final approach is not `unspecified` merely because it lacks STOP.

Every NONFINAL stage needs an outcome sufficient for its actual successor. A final terminal directive cannot license a later stage. Location equality alone never completes required past traversals, a return, or a repeated visit.

## Fidelity and relation ownership
Preserve active movements/turns/passes/entries/exits, initial and expected-state cues, landmark attributes, quantities/ordinals, uncertainty, prohibitions, conjunctions, repeated events, intermediate stops and final pose. 'See', 'toward', 'reach', 'at a door', 'through' and 'inside' differ. 'Walk on the left of the sofa' is an agent-path relation, not a statement that the fireplace is left of the sofa. Do not extend an endpoint-only relation into a whole-route invariant.

Keep until with its owner and exact condition; after/once/when with its trigger; before without assuming the later event must occur; while/keep/stay over only the stated scope; if/otherwise as alternatives, not mandatory serial actions. Attach target-identifying descriptors before target choice. Preserve count category and origin; no restarting at a new stage. Apply a spoken correction only to its clearly superseded event. A source 'wait at X' can specify target placement without a redundant walk verb; do not add a threshold crossing. No fabricated STOP, angle, distance, tolerance, search, room or furniture side.

Evidence: S1 explicit source; S2 uniquely supported relation in the WHOLE source; S3 non-route-changing grammar repair; S4 plausible layout, model preference or outside evidence is prohibited. An exact quote's presence is not proof that it entails a judgment.

## One acceptance matrix
`pass`: candidate.status=ok; all three dimensions pass; all active source requirements retained; all stages supported (allow final terminal_goal_directive); every adjacent handoff supported; no findings.
`revise`: at least one source-repairable candidate defect. A false needs_review is repairable. A valid alternative stage count or stylistic preference is not a defect. A specific missed useful cut belongs to segmentation_adequacy, not automatically fidelity.
`unresolved`: a SOURCE-level necessary ambiguity remains even after reasonable regrouping, not merely a candidate-created boundary gap. Explain the exact missing referent/route choice/condition; do not produce a partial guessed plan.

Reviewer findings are advice: the generator independently accepts, partially accepts, rejects or leaves unresolved EACH indexed finding, then rechecks the whole route. One semantic repair; R1 sees only source/current candidate/current rendered text. No main auditor. An identical candidate can be right when the suggestion is unsupported.

## Shared C01–C12 checklist
C01: active source requirement coverage. C02: unsupported additions/strengthening. C03: order/event identity/refinement/correction/repetition. C04: condition and logical scope. C05: target descriptors. C06: spatial owner/viewpoint/time. C07: entity identity/count class/origin. C08: all five stage meanings and ending basis. C09: prior outcome/next entry/carryover. C10: useful grouping without fragments or evidenced missed goals. C11: intermediate stops and final position/orientation. C12: actual executable English, not an audit-only repair.

Format belongs to the existing renderer. Do not add numbering, goal labels or five-element labels. Ordinary boundary spaces/newlines are not semantic defects. The host may pass a frozen candidate whose whitespace differs from the raw draft; review that exact candidate. A lexical mismatch between rendered text and candidate is a technical integrity error to stop at the host, not a reason for generator route rewriting. Nothing in this text proves actual navigation success.

## Entry context: meaning, evidence, and audit representation

An entry describes the conditions needed to execute a stage from the state in which that stage begins. It is not a command to establish or restore that state, and it is not evidence that an action has occurred.

Determine the necessary entry from the complete source instruction and actual candidate text. Consider location, pose, entity identity, counting origin, reference frame, and prior route events only where they affect this stage. Do not invent missing world facts or require each stage to restate ordinary current-state information.

Represent the principal source of entry support as follows:
- `episode_start`: the first output stage begins in the actual episode context. This label does not assert an unnamed location, heading, or completed action.
- `explicit_context`: the stage text states the relevant entry condition or trigger, supported by the source. Give a nonempty explanation and quote the actual stage words. Such wording expresses a prerequisite, not an observed completion or an extra command to recreate that condition.
- `inherited_pose`: a later stage continues from a supported preceding outcome without needing an additional critical textual anchor. A preceding movement does not establish a heading or location that its supported outcome leaves open.
- `inherited_entity`: a later stage uses the same uniquely established entity from the preceding context. This alone establishes neither location nor heading, counting origin, or traversal history.

The first output stage has no preceding output stage; classify its entry as `episode_start` or `explicit_context`. A later stage does not restart the episode, even when its required action is to return to the starting place. When kinds of context coexist, choose the mode that best describes the operative entry dependency and preserve other necessary dependencies in the existing evidence, conditions, carryover, and handoff fields.

Choose the audit representation after checking the executable text. If the text is adequate and only the mode is misclassified, correct the audit without changing the route. If a critical dependency is absent, restore only source-supported context, move the boundary, or merge the coupled maneuver under the existing rules. Do not add movement, a location, heading, arrival, STOP, or a mandatory preamble to make a label appear valid.

Distinguish a candidate-created dependency gap from genuine source ambiguity. Repair the former with the existing bind/move/merge rules. Use the existing source-limited path only when an essential source ambiguity remains after reasonable regrouping; ordinary visual grounding is not such ambiguity. Diagnostic modes `missing` and `source_unspecified` do not make a Generator `ok` candidate acceptable.

The Generator supplies grounded self-audit; the Reviewer independently applies these same principles to actual candidate and rendered text. A mode neither proves semantic correctness nor supplies words missing from the instruction. A Reviewer `pass` must use the same stage-index entry restrictions; a non-pass report may describe a deficient entry with the corresponding gap or source-limited assessment and grounded finding.

## Shared canonical closed-loop evidence contract
For any accepted candidate, the Generator must produce structured `stage_audit` and `handoffs` under its active Schema. These use the SAME five stage meanings and ending taxonomy that the independent Reviewer tests in `stage_checks` and `handoffs`. The Generator's audit is a source-grounded self-check, not a separate execution plan or a completion observation. Reviewer gets only source, rendered English and stage text, not the Generator's self-assessment.
A missing entry, target, process, supported completion or applicable condition requires source-supported rebinding, moving the cut or merging BEFORE accepting the plan. Do not add STOP for bookkeeping. A final `terminal_goal_directive` is allowed only at the end and explicitly disclaims arrival/STOP evidence. Every accepted nonfinal stage must support the next stage's entry. Dataset profile/template selection does not alter these rules.
