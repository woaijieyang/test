# Development and Integration Guide

## Hard Constraints

- Preserve the current working tree and experiment outputs; work on an isolated branch/worktree.
- Do not modify AwareVLN Reason/Act, STOP, last_reasoning, image flow, action space, episode budget or actor state.
- Do not add online goal switching, memory, graph memory, a completion detector, a chief reviewer or a third semantic agent.
- Generator is the only Candidate author; Reviewer is an independent auditor.
- Adapter Profile is the only dataset dispatch authority.
- R2R and RxR Rules/Core/Dynamic assets must remain isolated.
- Do not modify `shared/semantic_contract.md`, generic prompt rules, Runtime Schemas, Renderer behavior, or AwareVLN Actor behavior for an R2R-only enhancement.
- R2R retrieval changes must remain behind `profile == "r2r-en"`; do not modify the generic selector features/ranker used by RxR.
- Offline fixtures and CI are not real-model calls or navigation results.

## Source and Identity

Read the actual R2R/RxR source schemas and preserve original instruction text exactly after decoding. Include dataset, language, split and stable episode_id/instruction_id or task_key. Conflicting identity fields or same task key with different source hash must fail closed. Formal evaluation requires an explicit supported split.

## Prompt and Template Changes

Edit source prompts, Rules, schemas or teaching Templates only when required. Never hand-edit Compiled Prompt files. Run `python -B -m host.compile`, inspect all six generated prompt files and the Build Manifest, then run `python -B tools/verify_package.py`. Confirm each Role has exactly ten fixed Core examples and Dynamic IDs belong only to the selected Profile allowlist. Legacy is not a runtime source.

For teaching examples, verify Source Requirement → Candidate Evidence → Semantic Relation → Finding/Decision → Execution Consequence → Transfer Rule. JSON Schema and quote existence alone do not prove semantic correctness. Never label a curated teaching target as official subtask annotation or navigation ground truth.

## R2R-specific integration

R2R rules are loaded in this order: shared semantic contract, shared R2R rules, matching role-specific R2R guidance, fixed R2R Core, selected R2R Dynamic, active schema. The R2R fragment registry is Host-side retrieval input and must not be copied into the model payload. Generator and Reviewer role guidance are separate files. Keep the R2R rule/fragment/guidance hashes in task provenance and freeze them across G0/R0/G1/R1.

## Workflow Integration

Use `host.run.run_record(source, transport, pins=..., separator='\\n')`. The transport must return parsed output and a receipt containing actual model, effort and request ID. Do not echo requested aliases as provider receipts. Do not retry ambiguous remote execution. G1 must return a complete Candidate and one response per blocking R0 Finding. R1 must receive frozen R0 Review, old Candidate and old rendered text.

## Actor Boundary

Pass only `result['instruction']` to the existing instruction field and verify its hash. Capture complete prompt bytes, actual token IDs, tokenizer/template version, image IDs/order and truncation only after the existing Actor builds its full request. Do not tokenize each subtask independently and concatenate token IDs.

## Validation

```bash
python -B -m host.compile
python -B tools/verify_package.py
python -B -m unittest discover -s tests -v
python -m examples.demo
python -m evaluation.smoke24
```

Review all R2R and RxR prompt outputs, Core IDs, Dynamic IDs, Rules hashes, Build Manifest and full regression results. Any RxR prompt or selection drift blocks release. Any generated-file difference after compilation must be resolved and committed.

## Evaluation

Freeze model, effort, prompt, templates, renderer, data split and actor settings before comparisons. Blindly assess Generator and Reviewer separately before paired navigation. Preserve every fallback and technical failure in the denominator. Use source-disjoint held-out data; do not tune per episode from navigation outcomes.
