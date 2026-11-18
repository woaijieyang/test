# RxR Reviewer fixed core — 10 cases

These are the v5-format migrations of the ten original v1 Reviewer teaching cases. They are independent review demonstrations, not copies of Generator outputs. The JSON files in this directory are the runtime fixed core; the matching `legacy/` files remain archival provenance copies and are excluded from dynamic retrieval. Each core review is paired by `pair_id` with the corresponding Generator core template ID.

|Slot | File | Actual review focus | Actual v1/v6 verdict |
|---|---|---|---|
| R01 | `G01_RxR-CORE-R01.json` | Initial context, turn-dependent doorway identity, room entry and final placement | PASS |
| R02 | `G02_RxR-CORE-R02.json` | Until-bound movement, ordinal doorway selection and explicit non-entry constraint | PASS |
| R03 | `G03_RxR-CORE-R03.json` | Turn-before-entry condition and final open-area goal | PASS |
| R04 | `G04_RxR-CORE-R04.json` | Temporal-order reconstruction and multi-leg route transitions | PASS |
| R05 | `G05_RxR-CORE-R05.json` | Late visual description bound to the intended doorway before selection | PASS |
| R06 | `G06_RxR-CORE-R06.json` | Halfway descent as a bounded endpoint followed by stop and wait | PASS |
| R07 | `G07_RxR-CORE-R07.json` | Expected-state narration, endpoint orientation and subsequent kitchen entry | PASS |
| R08 | `G08_RxR-CORE-R08.json` | Superseding correction, maintained sofa constraint and explicit return route | PASS |
| R09 | `G09_RxR-CORE-R09.json` | Intermediate stop followed by a conditional alternative entrance | PASS |
| R10 | `G10_RxR-CORE-R10.json` | Source-level ambiguity in the referent and turn direction | UNRESOLVED |

The core is injected in R01–R10 order on every RxR en-US Reviewer call (R0 and R1). It is independent from the paired dynamic Reviewer cases. Dynamic retrieval adds 2–4 Reviewer cases paired to the Generator's dynamic IDs, then 0–2 relevant Diagnostics.

## Provenance caution

These ten cases are authored Reviewer demonstrations migrated from v1. They are not official RxR human review annotations, not model-generated empirical reviews, and not navigation ground truth. Their value is to teach evidence-grounded PASS/REVISE/UNRESOLVED distinctions and common semantic failure modes. Preserve the provenance on each case.

## Identifier convention

Reviewer core records use their own canonical IDs `RXR-CORE-R01`–`RXR-CORE-R10`. Their `pair_id` values point one-to-one to Generator IDs `RXR-CORE-G01`–`RXR-CORE-G10`. The R01–R10 slot labels and filenames are not the pairing mechanism; the explicit `pair_id` is. Role scoping keeps the Generator and Reviewer JSON files independent; do not infer that they share teaching content.
