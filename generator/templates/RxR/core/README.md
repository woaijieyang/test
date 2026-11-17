# RxR Generator fixed core — 10 cases

These are the v5-format migrations of the ten original v1 Generator teaching cases. The JSON files in this directory are the runtime fixed core; the matching `legacy/` files remain archival provenance copies and are excluded from dynamic retrieval. Each case retains its v1 lineage under `legacy_reference` and its v5 schema fields.

|Slot | File | Original teaching purpose |
|---|---|---|
| G01 | `G01_RxR-CORE-G01.json` | Initial context, turn-dependent doorway identification, and room-entry boundary |
| G02 | `G02_RxR-CORE-G02.json` | Until endpoint, intermediate landmarks, ordinal target selection, and prohibition |
| G03 | `G03_RxR-CORE-G03.json` | Turn-before-entry condition without inventing a threshold stop or room entry |
| G04 | `G04_RxR-CORE-G04.json` | Clause-order reconstruction and a multi-stage route with distinct completed objectives |
| G05 | `G05_RxR-CORE-G05.json` | Attach a later identifying description to the earlier target-selection action |
| G06 | `G06_RxR-CORE-G06.json` | Treat a later bounded-position clause as refinement of the same movement |
| G07 | `G07_RxR-CORE-G07.json` | Separate expected-state narration from action and preserve endpoint orientation |
| G08 | `G08_RxR-CORE-G08.json` | Apply explicit correction, scope a persistent constraint, and preserve a return visit |
| G09 | `G09_RxR-CORE-G09.json` | Preserve an intermediate stop and conditional alternatives with a shared outcome |
| G10 | `G10_RxR-CORE-G10.json` | Abstain when a route-critical reference and turn direction are not source-resolvable |

The core is injected in G01–G10 order on every RxR en-US Generator call (G0 and G1). It is not retrieved, ranked, truncated by selector logic, or replaced by dynamic examples. Dynamic retrieval adds 2–4 examples from the separate val_seen pool.
