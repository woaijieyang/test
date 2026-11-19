# V1 → V5 → V6: rule and runtime comparison

> **Historical archive — not a current runtime specification.** This document preserves a source-based comparison of earlier repository snapshots. Statements below such as “R2R has no fixed Core” or “only RxR loads dataset-specific rules” describe the historical snapshot being compared and are superseded by the current dual-Profile implementation. The current contract is defined by the root `README.md`, `WORKFLOW.md`, `host/README.md`, `shared/dataset_rules/README.md`, active prompt/schema files, template manifests and `provenance/build_manifest.json`. Current R2R and RxR each load ten fixed Generator Core and ten independent Reviewer Core examples, plus their own Profile-specific rules and Dynamic pools.

This note records the implementation-relevant differences between the original `LLM-decompose-v1` branch, the v5 baseline, and the v6 RxR en-US extension. It is a source-based comparison, not a claim that any version has higher navigation SR/SPL without a controlled run.

## 1. What v1 contributes

The v1.3 Generator prompt already contains the central long-route semantics that motivated this extension:

- read the complete instruction before segmentation and reconstruct execution order rather than copying sentence order;
- preserve `until`, `before`, `after/once/when`, `while/keep/stay`, conditional alternatives, corrections, negations and count origins;
- bind later target descriptions before the agent must select the target;
- resolve pronouns against the full instruction and preserve route history for repeated visits/returns;
- preserve the temporal reference frame of left/right/facing relations;
- distinguish expected-state narration and visibility cues from actual navigation actions;
- treat a later endpoint refinement (e.g. halfway down the stairs) as part of the same movement;
- repair segmentation-induced incompleteness by moving the boundary or merging, and reserve `needs_review` for route-critical source ambiguity.

The v1.3 Reviewer independently checks source coverage, temporal/spatial scope, late target descriptions, route history, handoffs, and over/under-segmentation. It explicitly rejects style-only preferences and ordinary missing-image/coordinate limitations as textual defects.

However, the v1 runtime contract is much lighter. The Generator output schema has only `status`, `subtasks`, and `issues`. The Reviewer output schema has `verdict`, `findings`, and a compact `stage_checks` representation. The ten Generator and ten Reviewer templates use the v1 structure. The three runtime context conditions described in the v1 Generator prompt are an experimental plan; they are not a structured five-element stage-audit and handoff contract.

## 2. What v5 adds and standardizes

V5 has already absorbed and formalized most of the useful v1 semantic principles in its common prompts and shared semantic contract. It should not be rewritten for this extension.

| Area | V1 | V5 common system |
|---|---|---|
| Generator semantics | Full-route reading, event order, conditions, target attachment, frame/time, route history | Retains these principles and adds explicit five-element evidence obligations and stricter source/candidate quote provenance |
| Stage representation | Natural-English subtasks; semantic checks mostly in prose | Natural-English subtasks plus structured `entry`, `target`, `process`, `ending`, `conditions` Stage Audit |
| Ending | Supported completion event discussed in prose | Explicit ending taxonomy: `explicit_event`, `bounded_action`, `linked_trigger_or_refinement`, `terminal_goal_directive`, `unspecified`; plus `stop_scope` |
| Handoff | Reviewer stage checks describe entry/completion/history | Explicit adjacent Handoff records with preceding exit, next entry, shared context, source requirement IDs and rationale |
| Reviewer | Verdict, findings, compact stage checks | Three dimensions, source coverage, L0–L6 layers, complete five-element stage checks, explicit handoffs and evidence-backed findings |
| Evidence | Exact source quote and candidate stage review | Separate source quotes and candidate quotes; source coverage maps requirements to actual stage evidence; cross-stage evidence is supported |
| Templates | 10 Generator + 10 Reviewer cases in v1 JSON format | Dataset-specific curated libraries in v5 template schema; paired Reviewer examples and diagnostics |
| Runtime | Original plan discussed three context conditions | Bounded G0 → R0 → optional G1 → R1; the Actor receives the existing rendered natural-language instruction |

V5's RxR library contains 45 Generator records (35 val_seen + 10 migrated legacy examples) and 74 Reviewer records (35 paired + 29 diagnostics + 10 migrated legacy examples). The ten migrated records are already v5-format teaching examples, but v5's selector treats them as part of the dynamic pool. They are not unconditionally loaded as a fixed core. V5 also uses the common rules for both R2R and RxR; there is no active RxR-specific rule bundle in the baseline.

## 3. What v6 changes — and what it deliberately does not

V6 preserves the v5 common Generator/Reviewer prompts, shared semantic contract, active runtime schemas, Stage Audit/Handoff schemas, Reviewer dimensions and L0–L6, Renderer, Adapter, Host call workflow and Actor boundary. It does not port v1 output schemas or its experimental current-subtask/history input modes.

The new capability is profile-specific:

1. `r2r-en` follows the v5 path: no RxR rule files, no fixed core, 35 Generator dynamic examples, 35 paired Reviewer examples and 26 Diagnostics. Its adaptive selection ranges remain 6–8 Generator/paired examples and 2–4 Diagnostics.
2. `rxr-en-us` adds a shared RxR semantic rule file and separate Generator/Reviewer operational guidance. The shared file defines the same semantic distinctions for both roles; role guidance only changes the order in which each role applies them.
3. RxR Generator always receives ten fixed v5-format core examples (the v1 G01–G10 teaching intentions) followed by 2–4 dynamic examples from the 35-case val_seen pool.
4. RxR Reviewer always receives ten independent v5-format Reviewer core examples (the v1 R01–R10 review intentions), then the 2–4 paired Reviewer examples matching the Generator dynamic IDs, then 0–2 relevant Diagnostics.
5. The old `legacy/` copies remain for provenance and are excluded from dynamic retrieval. Runtime loads the migrated v5-format copies under `core/`; it never loads v1 JSON or a v1 schema.
6. The Host freezes rule-file hashes and each role's fixed+dynamic template-content hash for the task. G0/G1 share the Generator bundle; R0/R1 share the Reviewer bundle. A mid-task change is a technical failure, not permission to silently switch rules or examples.

## 4. Why the v6 RxR guidance is not another common prompt rewrite

RxR-specific rules focus on long-instruction failure modes that benefit from a global event reconstruction pass: late descriptions that identify earlier targets, multiple similar objects, temporal relations spanning sentences, route-history dependencies, egocentric frame changes, ordinals whose origin precedes the current stage, and endpoint refinements that must not become a second movement.

The Generator guidance applies these in this order: reconstruct the complete route; identify actions/targets/references/observations/conditions; resolve global references and temporal scope; group coupled events; choose only supported boundaries; write natural-English stages; complete the existing five-element audit and handoffs.

The Reviewer guidance applies the same semantics independently: reconstruct the route; map event-level source coverage; inspect ordering and scope; audit each actual stage; compare actual adjacent exit/entry events; check both over- and under-segmentation; perform whole-route readback. It adds false-positive controls so that an observation is not turned into a goal, a reference landmark is not mistaken for the target, and an absent STOP is not treated as absent completion.

## 5. Core-template provenance and interpretation

The fixed core files are exact copies of the already migrated v5 legacy examples. This avoids rebuilding or silently changing their authored outputs while preserving their v1 lineage. The individual `provenance` and `legacy_reference` fields remain intact. The core must not be described as ten raw RxR dataset annotations: the provenance distinguishes the RxR train-derived source case from synthetic/adapted or user-supplied teaching cases. Reviewer cases are authored review demonstrations, not official human review labels or navigation ground truth.

The core examples are teaching priors, not mandatory segmentation recipes. The current source remains the only route authority; the model must transfer a semantic operation only when the live source supports the same relation.

## 6. Preserved boundaries

No change is made to:
- R2R semantic policy or dynamic retrieval range;
- v5 active Generator/Reviewer response schemas or shared nested schemas;
- five-element stage meaning, Ending taxonomy, stop scope, Handoff or Source Coverage semantics;
- G0/R0/G1/R1 call roles and bounded repair/review protocol;
- Adapter source parsing, Task Identity or source hashing;
- Renderer whitespace/prefix/suffix behavior;
- AwareVLN Reason/Act, STOP, goal switching, memory, image input, action space, or navigation budget;
- final Actor input: one complete rendered natural-language instruction. Rules, templates, audits and review evidence stay Host-side.

## 7. Validation boundary

The v6 CI workflow builds all profile prompts and indexes, validates the fixed core and dynamic libraries against the v5 teaching schemas, checks R2R/RxR profile isolation and paired selection, and runs the targeted v5 runtime/adapter/renderer integration tests. Passing these tests establishes structural and integration compatibility only. It does not establish model semantic accuracy or navigation improvement; those require real-model and navigation evaluation.
