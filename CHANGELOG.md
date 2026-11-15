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
