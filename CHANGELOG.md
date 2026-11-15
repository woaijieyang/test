# Changelog

## final-best-v1
- Start from the RxR v1.3 semantic baseline; do not replace its global reading, dependency binding or complete-stage assembly.
- Align Generator and Reviewer to one shared five-property / five-dependency / C01–C12 acceptance contract.
- Restore explicit positive segmentation: short instructions may contain several distinct local objectives; do not collapse or over-fragment by length or verb count.
- Separate fidelity, closure/handoff and segmentation adequacy so a missed useful boundary is not mislabeled as route-semantic corruption.
- Add a terminal-goal-directive completion basis for a final `toward X` instruction without claiming arrival or inventing STOP.
- Add exact previous-exit / next-entry handoff checks, layered reviewer evidence, actionable local findings and one bounded generator repair.
- Make the adapter explicitly support R2R VLN-CE nested `instruction.instruction_text` and RxR en-US guide JSONL `instruction` strings, while preserving the decoded source exactly.
- Keep renderer provenance and source envelope behavior; stage boundaries are LF in the baseline experiment, source prefix/suffix and untouched source whitespace are preserved.
- No new navigation run, model call, SR claim, online goal switch, memory module or AwareVLN Reason/Act/STOP/last_reasoning change is included.


## runtime-contract-v2 (2026-11-15)
- Replace the incompatible runtime Generator, Reviewer and G1 repair schemas with Draft 2020-12 contracts aligned to the v1.5.2 teaching Stage Audit/Handoff structures.
- Canonicalize Generator stage index as `subtask_index`, Reviewer dimension as `source_fidelity`, and Reviewer candidate evidence as `{subtask_index, quote}`.
- Enforce `ok` versus `needs_review` array semantics; require `ending.stop_scope`; preserve the complete five-element audit and every adjacent handoff.
- Add `prior_finding_reviews` to the Reviewer contract. R0 returns an empty array; R1 returns one resolution status and new-candidate evidence for every prior R0 finding.
- Update Host protocol for cross-stage evidence: evidence may cite both adjacent stages while the minimal repair target is only one stage.
- Update Host run to pass the frozen R0 review, old candidate and old rendered text to independent R1; preserve the four-call maximum, request receipts, snapshot hashes and exact-source technical fallback.
- Migrate G1 repair teaching examples to the new runtime envelope.
- No model inference or navigation experiment was run during this schema/host update.
