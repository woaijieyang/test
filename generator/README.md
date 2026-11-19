# Generator — semantic author of executable navigation stages

`prompt.md` defines the Generator role. `shared/semantic_contract.md` is the single shared acceptance standard. `output.schema.json` is the active G0 schema; `repair.schema.json` wraps a complete Generator candidate and one response per blocking Reviewer Finding.

## R2R English specialization

When Adapter Profile is `r2r-en`, `generator/dataset_rules/r2r_en.md` is loaded after the shared R2R rules and before the fixed R2R Generator Core. It adds the R2R route-event inventory, completed-boundary test, coupled-maneuver protection, minimal-text-change policy, and R2R-specific readback sequence. It does not change the Generator schema or the generic prompt. RxR does not load this file.

## Runtime Output

The response contains `status`, `subtasks`, `issues`, `stage_audit` and `handoffs`. An accepted Candidate has one five-element Stage Audit per stage and one Handoff per adjacent pair. A `needs_review` response has no executable subtasks and includes a source-grounded issue. Stage indices use `subtask_index`.

Each Stage preserves Entry, Target, Process, Ending and Conditions. Source quotes must be exact excerpts; candidate quotes must exist in their own executable stage. Carryover records inherited context and never substitutes for missing executable words.

## Boundary and Repair Policy

A split requires a completed source-supported prior event, a distinct next objective, a supported entry and a concrete benefit to local navigation focus. Do not split by verb count, sentence count or landmark count. Keep coupled turns with the movement they enable. Preserve ordinal origins, temporal scope, direction references, threshold crossing, explicit stop/wait and final placement. A boundary is not a physical stop.

G1 receives the complete Source, prior Candidate, R0 Review and protected requirements. It must decide on each finding and return a complete Candidate; it must not blindly accept unsupported Reviewer advice.

## Fixed Core and Dynamic Library

| Profile | Fixed Core | Dynamic source | Dynamic per task |
|---|---:|---:|---:|
| R2R English | G01–G10 (10) | 25 eligible from R2R val_seen pool | 6–8 |
| RxR en-US | G01–G10 (10) | 35 RxR val_seen examples | 2–4 |

Fixed Core is always loaded in stable order. Dynamic retrieval cannot replace Core. R2R loads only R2R assets; RxR loads only RxR assets. Legacy files are provenance only.

## Teaching Corpus

Templates are curated teaching demonstrations, not official subtask labels or trajectory-verified ground truth. Each example must explain its primary decision boundary, source evidence, candidate organization, transfer rule and anti-pattern. A schema-valid file is not automatically a semantically correct lesson.

Run `python -B -m host.compile` after changing prompts, rules, schemas or examples. Review the generated Prompt and Build Manifest; do not edit compiled files manually.
