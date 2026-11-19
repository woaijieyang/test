# R2R English specialization: rules, retrieval, Host integration, and validation

## 1. Scope and invariants

This document defines the R2R English specialization layered onto the existing dual-Profile system. It is selected only by Adapter Profile \`r2r-en\`.

The implementation preserves the existing ownership and runtime contracts:

- Adapter remains the sole authority for Dataset, Language, Split, task identity, and Profile.
- Generator remains the only author of the executable Candidate.
- Reviewer remains an independent source-grounded auditor.
- Host remains the sole controller of G0 → R0 → optional G1 → R1, validation, snapshots, recovery, and release.
- Renderer remains a source-traceable text assembler and does not make semantic decisions.
- AwareVLN continues to receive only the final instruction string through its existing instruction slot.
- The shared semantic contract, Runtime Schemas, generic prompts, Renderer, Actor, and RxR profile behavior are not redefined by this specialization.

The R2R-specific files refine how the existing contract is applied to R2R route language. They do not create a second segmentation policy, an extra semantic agent, a new output schema, or an online navigation controller.

## 2. Why R2R needs a separate specialization

The completed R2R experiments show that the existence of a dataset profile, a fixed Core, and a generic semantic contract is not sufficient to guarantee stable navigation behavior.

The B2 full-partition comparisons show that the tested enhanced configurations did not consistently outperform their paired baseline. In the GPT-5.6 B2 run, the reported SR/SPL/nDTW/NE values were 61.202% / 52.264% / 63.485% / 4.286m, compared with 66.667% / 57.134% / 66.065% / 3.777m for the paired baseline. The v6 GPT-5.6 and v6 GPT-6 Astra runs also remained below their paired baseline on the reported primary metrics. These results do not establish that segmentation is intrinsically harmful; they establish that the then-tested prompts, rules, retrieval bundles, and model configurations did not yet provide a reliable improvement.

The experiment evidence also distinguishes materially different implementation states. The v6 GPT-5.6 B2 run recorded no R2R fixed Core and did not load the R2R-specific rules bundle. The v7 GPT-5.6 B2 run did load the ten R2R fixed Generator and Reviewer Core cases and the R2R-specific rule files, but selected only two Dynamic examples per role in that run. Therefore, the v6 and v7 outcomes must not be treated as controlled ablations of one isolated rule change.

Episode-level evidence motivates the specialization. A compact sequence such as turning, passing a piano, turning again, and stopping in an archway can remain one coherent maneuver even when it contains several action verbs and two sentences. Conversely, exiting or entering a region and then pursuing a distinct local target can support a useful boundary when the transition is complete and the next objective has a supported entry. The policy must preserve both capabilities rather than biasing all cases toward KEEP or SPLIT.

A further risk is unnecessary rewriting. In the documented Episode 1060 comparison, the accepted one-stage Candidate changed only the source wording “passed” to “past”; the Reviewer passed it, yet the enhanced navigation rollout diverged from the paired baseline and failed. This is not proof that the lexical edit caused the failure. It is sufficient evidence to justify a strict minimal-change policy and to require separate testing of semantic edits, rendering changes, and navigation behavior.

## 3. R2R-only rule ownership

The R2R rule stack has three text layers and one Host-side retrieval registry.

| Asset | Owner | Runtime use |
|---|---|---|
| \`shared/dataset_rules/r2r_en.md\` | R2R shared guidance | Loaded by both R2R roles |
| \`generator/dataset_rules/r2r_en.md\` | Generator | Loaded only by R2R Generator G0/G1 |
| \`reviewer/dataset_rules/r2r_en.md\` | Reviewer | Loaded only by R2R Reviewer R0/R1 |
| \`shared/dataset_rules/r2r_fragments.json\` | Host retrieval | Read only by the R2R selector; not injected as route facts |

The shared R2R guidance defines route-event reading, the boundary test, landmark roles, ordinal/count-origin preservation, orientation frames, room/doorway/stair transitions, bounded movement, negation, terminal placement, minimal rewriting, and handoff rules.

The Generator guidance operationalizes the same semantics as a full-route analysis and candidate-authoring sequence. It requires the Generator to inventory the complete source, assemble coupled maneuvers, evaluate each proposed boundary, write the minimum necessary text, complete the existing five-element stage audit and handoff audit, and perform a full-route readback.

The Reviewer guidance independently checks source coverage, candidate support, L0–L6, stage closure, handoffs, under-segmentation, over-segmentation, and source-to-render differences. It does not add a verdict dimension or a new schema. A finding must cite the current source and candidate and explain a material execution or local-focus consequence. Style preference and speculative visual interpretation are not blockers.

The fragment registry contains deterministic lexical/semantic retrieval cues. The selector validates its structure and compiles its regular expressions. It is used only to rank R2R teaching examples. A fragment match is never a segmentation instruction and never overrides the complete source, current candidate evidence, shared semantic contract, or Reviewer evidence threshold.

## 4. Boundary semantics

A candidate split is eligible only when all four conditions are supported together:

1. The preceding event has a source-supported completion state.
2. A genuinely distinct next navigation objective follows.
3. The next stage has an executable and unambiguous entry, inherited from the completed state or stated with a minimal source-supported anchor.
4. The boundary provides a concrete local-focus benefit without breaking an active dependency.

The order of clauses is not sufficient evidence of a completed state. A turn is not automatically an independent goal. A landmark mention is not automatically a target. A room or doorway mention is not automatically an entry event. A stage boundary is not a physical STOP.

Coupled maneuvers are assembled before boundary selection. Examples include turn-plus-continuation, approach-plus-turn-at, turn-plus-doorway-entry, pass-by-plus-dependent-turn, and a bounded stair segment whose endpoint condition still governs the movement. These patterns are not hard-coded KEEP rules: a cut remains possible when the source establishes a distinct completed event and a genuinely different next objective.

Conversely, the system must not under-segment a completed transition followed by a new local target merely because the instruction is short. The decision is based on completion, target identity, entry, dependencies, and local focus—not a fixed number of verbs or stages.

## 5. R2R fragment retrieval

### 5.1 Feature inventory

The Host-side registry provides R2R cues for:

- room transition;
- doorway selection and crossing;
- stairs, flights, landings, and level change;
- landmark-conditioned navigation;
- temporal dependency;
- ordinal target selection;
- return or revisit;
- bounded movement;
- orientation/reference frame;
- intermediate stop or wait;
- negation;
- conditional observation;
- correction;
- path branch/junction;
- explicit source-level ambiguity.

The selector additionally derives two task-level retrieval labels from combined source structure: \`single_stage_keep\` and \`multi_stage_split\`. They identify useful teaching patterns for retrieval only. They are not model outputs, decision thresholds, or automatic cut rules.

### 5.2 Ranking

The generic \`features()\`, \`PATTERNS\`, and \`rank_examples()\` path remains the RxR path and is not modified by the R2R specialization. R2R uses \`r2r_features()\` and \`rank_r2r_examples()\`.

The R2R ranker combines:
- overlap between current-source cues and teaching-case cues/tags;
- source-only lexical overlap with inverse document-frequency weighting;
- matching temporal/route relations;
- authored semantic pattern and KEEP/SPLIT teaching annotations;
- diversity coverage so later selections add evidence not already covered;
- exclusion of an exact normalized source match.

It does not read navigation scores, ground-truth paths, trajectory outcomes, or validation labels. It does not use B2/A1/A2/A3 partition names to choose examples. Retrieval affects which teaching cases are shown, not the truth conditions for the current decision.

### 5.3 Runtime quantities

The ten fixed R2R Generator Core cases G01–G10 and ten fixed Reviewer Core cases R01–R10 remain unconditional and stable in order.

The runtime-eligible Dynamic pools remain:
- Generator: 25 R2R examples;
- Reviewer Paired: 29 R2R examples;
- Reviewer Diagnostics: 23 R2R examples.

Adaptive per-task selection is:
- Generator Dynamic: 6–8;
- Reviewer Paired Dynamic: exactly the selected Generator Dynamic count, 6–8;
- Reviewer Diagnostics: 2–4.

The Reviewer paired prefix must map one-to-one and in the same order to the selected non-Core Generator Dynamic IDs. Diagnostics are additional, unpaired examples. Fixed Core is never part of Dynamic retrieval and cannot be replaced. \`selection_mode=all\` remains an explicit offline ablation path, not a production default.

## 6. Prompt composition and phase consistency

R2R Generator composition:

\`\`\`text
common generator prompt
→ shared semantic contract
→ shared R2R rules
→ R2R Generator role guidance
→ ten fixed R2R Generator Core examples
→ selected R2R Generator Dynamic examples
→ active G0 or G1 schema
→ current immutable Source and phase payload
\`\`\`

R2R Reviewer composition:

\`\`\`text
common reviewer prompt
→ shared semantic contract
→ shared R2R rules
→ R2R Reviewer role guidance
→ reviewer checklist
→ ten fixed R2R Reviewer Core examples
→ selected paired R2R Reviewer examples
→ selected R2R diagnostics
→ active Reviewer schema
→ current Source, Candidate, rendered snapshot, and (for R1) frozen prior review context
\`\`\`

G0 and G1 use the same frozen Generator rules, role guidance, Core, Dynamic IDs, and bundle hash. R0 and R1 use the same frozen Reviewer rules, role guidance, Core, paired Dynamic IDs, Diagnostics IDs, and bundle hash. Phase-specific schema and repair/recheck payloads remain governed by the existing Host contract.

RxR keeps its existing prompt assembly path. No R2R rule, fragment, Core, Dynamic template, or role guidance is loaded for \`rxr-en-us\`.

## 7. Host provenance and immutability

For R2R, the task-level rules metadata records the shared semantic contract, shared R2R rules, fragment registry, Generator R2R guidance, and Reviewer R2R guidance. Per-role Prompt Components metadata records the role-specific guidance that actually contributes to that role's prompt, alongside the existing prompt, schema, compiler, selector, and checklist inputs.

The task record continues to freeze:
- Source Identity and Source SHA-256;
- Adapter Profile;
- rules metadata and hashes;
- Generator and Reviewer prompt component hashes;
- fixed Core IDs and bundle hashes;
- selected Dynamic IDs and bundle hashes;
- selection evidence and matched R2R cues/relations;
- model/effort/provider receipt;
- candidate/rendered/snapshot hashes;
- G0/R0/G1/R1 events and final disposition.

The fragment registry is a retrieval asset, not model-provided route evidence. It is included in the R2R rules hash so a change in retrieval semantics is visible in the task record. It is not copied into the model's user payload and does not expose Host-only Path, Scan, GT, trajectory, or navigation metrics.

## 8. RxR isolation contract

The following RxR behaviors are frozen relative to the pre-change baseline:

- shared semantic contract content;
- RxR shared and role-specific guidance;
- ten fixed RxR Generator and Reviewer Core cases;
- RxR Dynamic allowlists and eligible counts;
- RxR adaptive selection range and paired/diagnostic policy;
- RxR generic feature extraction and generic ranker;
- RxR prompt assembly order and compiled prompt bytes;
- RxR Runtime Schemas, Renderer, Host state machine, and Actor interface.

The implementation branches on the already-established Adapter Profile. The new R2R feature registry is loaded lazily only when R2R feature extraction is requested. The R2R ranker is called only for \`r2r-en\`. The RxR branch continues to call the original generic \`features()\` and \`rank_examples()\` functions.

A compiler source hash may change because the shared compiler file now contains an R2R-only branch. That does not constitute RxR behavior drift. RxR invariance is checked against the pre-change compiled prompt hashes and existing selector/profile tests. A changed RxR prompt hash, selected ID set, bundle, or output behavior blocks the branch.

## 9. Engineering validation

Run the existing validation workflow on the dedicated branch. Required checks include:

1. Package integrity and required-file checks.
2. Full prompt compilation and generated-index/build-manifest regeneration.
3. R2R Core, Host dispatch, R2R-specific fragment/selector/prompt tests.
4. RxR profile and frozen compiled-prompt hash tests.
5. Paired Dynamic selection and Reviewer alignment tests.
6. Existing closed-loop, Runtime Schema, repair, recovery, Renderer, and workflow regression tests.
7. Renderer smoke and integration demo.

The compiled RxR artifacts must match their pre-change hashes:
- Generator initial: \`864e5a37a2c7b8b7fef45c4c58ceeebc87183d52d0db9ab26e0b73c1b75f4a21\`;
- Generator repair: \`81dc6e312f6106937bafb2f317048e0bcae01e23748fc9c9749051581433894f\`;
- Reviewer: \`18c1f6a7611086f8d9a2888390f38b9c2224d2e1f749c3ea1059a2a6a032fb7b\`.

These hashes protect the compiled outputs, not the shared compiler source. The branch's CI must compile and persist all generated files on the branch itself; it must not push generated artifacts back to the v6.4 branch.

## 10. Evaluation boundary

Engineering tests establish package, dispatch, prompt composition, retrieval, and isolation properties only. They do not establish semantic accuracy or navigation improvement.

The next semantic evaluation should use a frozen source-disjoint roster and blind independent assessment of Generator and Reviewer outputs. Navigation comparisons must hold the Actor checkpoint, model, effort, visual inputs, tokenizer, action space, STOP behavior, environment, budget, and paired task roster fixed. Report the full denominator, fallbacks, technical failures, SR, SPL, nDTW, NE, steps, model calls, recoveries, regressions, and paired uncertainty intervals.

Previously inspected val_unseen episodes may be used as regression evidence for rule design, but not as a fresh held-out test set or as runtime teaching templates. No claim of improved SR/SPL/nDTW is made by this implementation or by passing CI.
