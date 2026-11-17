# RxR Reviewer fixed core — 10 cases

These are the v5-format migrations of the ten original v1 Reviewer teaching cases. They are independent review demonstrations, not copies of Generator outputs. The JSON files in this directory are the runtime fixed core; the matching `legacy/` files remain archival provenance copies and are excluded from dynamic retrieval. Each core review is paired by `pair_id` with the corresponding Generator core template ID.

|Slot | File | Original review teaching purpose | Actual v1/v6 verdict |
|---|---|---|---|
| R01 | `G01_RxR-CORE-R01.json` | PASS for coherent stages and a supported exit-to-entry handoff | PASS |
| R02 | `G02_RxR-CORE-R02.json` | PASS; preserve the until endpoint and its continuing movement | PASS |
| R03 | `G03_RxR-CORE-R03.json` | PASS; do not invent a physical stop at a threshold | PASS |
| R04 | `G04_RxR-CORE-R04.json` | PASS; bind target-identifying information before selection | PASS |
| R05 | `G05_RxR-CORE-R05.json` | PASS; preserve source-supported execution order | PASS |
| R06 | `G06_RxR-CORE-R06.json` | PASS; apply a superseding correction to its intended action | PASS |
| R07 | `G07_RxR-CORE-R07.json` | PASS; preserve route history and explicit return semantics | PASS |
| R08 | `G08_RxR-CORE-R08.json` | PASS; preserve scoped constraints and return-visit semantics | PASS |
| R09 | `G09_RxR-CORE-R09.json` | PASS; preserve intermediate stops and conditional alternatives | PASS |
| R10 | `G10_RxR-CORE-R10.json` | UNRESOLVED for genuine source-level reference/direction ambiguity | UNRESOLVED |

The core is injected in R01–R10 order on every RxR en-US Reviewer call (R0 and R1). It is independent from the paired dynamic Reviewer cases. Dynamic retrieval adds 2–4 Reviewer cases paired to the Generator's dynamic IDs, then 0–2 relevant Diagnostics.

## Provenance caution

These ten cases are authored Reviewer demonstrations migrated from v1. They are not official RxR human review annotations, not model-generated empirical reviews, and not navigation ground truth. Their value is to teach evidence-grounded PASS/REVISE/UNRESOLVED distinctions and common semantic failure modes. Preserve the provenance on each case.

## Identifier convention

`R01`–`R10` are Reviewer core slot labels and file suffixes, not a separate template-ID namespace. Each Reviewer case retains the corresponding Generator core `template_id` (`RxR-LEGACY-G01`–`G10`) so its `pair_id` is an exact stable link to that Generator case. Role scoping keeps the Generator and Reviewer JSON files independent; do not infer that they share teaching content.
