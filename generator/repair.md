# One bounded, independent Generator repair (G1)

Keep the shared semantic contract unchanged. Input keys are `original_instruction`, the frozen `candidate`, and the complete `review` object. Reviewer findings are advisory evidence, not commands. Generator independently checks every finding against the original instruction and the shared acceptance rules.

## Required response procedure

For every zero-based index in `review.findings`, emit exactly one `responses` item in the same order:
- `finding_index`: exact zero-based index of the finding being answered.
- `decision`: `accept`, `partially_accept`, `reject`, or `unresolved`.
- `source_quotes`: one or more exact substrings of the original instruction that support the decision. These are source quotes, never candidate quotes.
- `reason`: concise, evidence-based explanation of why the finding is accepted, partly accepted, rejected, or cannot be resolved.

If there are no findings, return `responses: []`. Do not omit a finding, duplicate an index, reorder responses, or answer only findings you agree with.

A correct diagnosis may propose an unsupported action. Accept the valid part of the diagnosis and reject the unsupported addition when appropriate. In particular, do not add a STOP, entry, threshold crossing, distance, angle, arrival or target that the source does not require. A rejected suggestion must cite the source wording that makes it unsupported.

## Candidate reconstruction

Only Generator edits the candidate. Return the complete updated `candidate` using the exact active Generator output schema:
- `status`: `ok` or `needs_review`.
- `subtasks`: complete ordered English stages.
- `issues`: empty for `ok`; nonempty and source-grounded for `needs_review`.
- `stage_audit`: complete five-element audit for every accepted stage, using `subtask_index` (not `index`) and required `ending.stop_scope`.
- `handoffs`: complete adjacent-pair handoff records using the shared Handoff Schema.

Do not return only revised English, a partial patch, or only the affected stage. After any edit, rebuild every affected stage audit and handoff; recheck the entire source for omissions, unsupported additions, order, reference frames, target identity, counts, restrictions, endings and carryover. Keep unaffected source-supported text and stage boundaries unchanged where possible.

## Bounded execution and return format

Prefer a minimum local correction: bind a source-supported entry, move a cut, or merge a coupled maneuver. Do not rewrite the entire route to satisfy a stylistic preference. A source-limited source returns `needs_review` with no speculative partial route. An unsupported Reviewer suggestion may leave the candidate unchanged, with a `reject` response and source evidence.

Return exactly `{ "candidate": ..., "responses": [...] }` under the active repair Schema. Do not use `feedback_response`, `review_feedback`, an envelope-level `status`, or the teaching-template wrapper. Preserve the per-task selected example IDs; do not request another retrieval. One semantic repair is the maximum; R1 is an independent recheck, not another repair loop.
