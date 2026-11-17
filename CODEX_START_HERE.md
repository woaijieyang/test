# Codex start here｜LLM-decompose-v6 integration contract

## Hard constraints

- Work in a new branch or isolated worktree. Do not overwrite the existing repository implementation or prior R2R/RxR experiment outputs.
- This package is a candidate configuration and host adapter. Do not change AwareVLN Reason/Act, STOP, `last_reasoning`, image flow, action space, episode budget or navigation logic.
- Do not add online goal switching, memory, graph memory, a completion detector, a chief reviewer or a third semantic agent.
- Generator is the only candidate author. Reviewer only diagnoses and advises. Both must use `shared/semantic_contract.md`.
- Do not treat fixture replies or offline unit tests as real model calls or navigation results.

## Step 1 — locate the actual data and actor interfaces

Inspect the current repository's real R2R/RxR source loader, instruction field, task identity, double-role model transport, final instruction write site, complete-prompt serialization/tokenization and evaluation entrypoint. Do not guess function names or create a parallel actor pipeline. Document the actual call path and the exact field where the final string is consumed.

Normalize only the record envelope, not the instruction text. R2R input must be English and use `instruction.instruction_text` or `instruction_text`; RxR input must be `en-US` and use the guide JSONL `instruction` string or `instruction_text`. Include `dataset`, `split`, and `episode_id`/`instruction_id` or an explicit stable `task_key`.

## Step 2 — source and renderer integration only

Before making a paid model call, test adapter and renderer with source records that cover:
- R2R source suffix with one ASCII space;
- RxR no suffix, prefix space and suffix spaces;
- original internal double spaces;
- source CRLF and LF inside the body;
- unchanged source and technical fallback byte-for-byte;
- boundary-only cut, zero-width delimiter after punctuation, and no split inside a word/contraction;
- single-stage reassembly, multi-stage reassembly and ambiguous repeated source spans.

Do not globally `strip`, `splitlines`, `split/join`, normalize Unicode, decode `unicode_escape`, or force a dataset-specific suffix rule. Stage count comes from the candidate array and ledger, not physical line count.

## Step 3 — compile and test roles

Run:

```bash
python -m host.compile
python -m unittest discover -s tests -v
python -m examples.demo
python -m evaluation.smoke24
python verify_package.py
```

Read both compiled prompts and confirm they contain the same shared acceptance contract. Do not edit compiled files manually; change the source prompt/contract/schema and recompile. Reviewer must see the actual frozen candidate and rendered instruction. G1 must independently accept/partially accept/reject/unresolve each finding and return a complete candidate plus one response per finding. R1 is a fresh session but must receive the frozen R0 review, old candidate and old rendered text so it can verify every prior finding; no reviewer patch is auto-applied.

## Step 4 — connect the existing model transport

Use `host.run.run_record(source, transport, pins=..., separator='\n')`. The callback must execute one actual request and return parsed `output` plus a provider receipt with the actual model, effort and request ID. Do not echo requested aliases as if they were provider receipts. Fix model/effort and decoding parameters before a controlled comparison. The host permits at most G0/R0/G1/R1 and fails closed on technical errors.

## Step 5 — release to the existing AwareVLN slot

Pass only `result['instruction']` to the existing instruction field. The string sent to the actor must match `instruction_sha256`. Capture the real full prompt bytes, final input token IDs, tokenizer/template version, image IDs and order, truncation flag and request ID after the existing actor has assembled its full request. Do not tokenize each subtask separately and concatenate token IDs.

Do not use stage audit metadata as actor state or a completion certificate. Do not add goalAdapter, STOP interception, graph/event memory or `last_reasoning` reset in this integration.

## Step 6 — evaluation order

1. Blindly evaluate G0 language quality on a frozen set with manual labels for fidelity, closure/handoff and segmentation adequacy.
2. On the same frozen candidates, compare old/new Reviewer in a blinded protocol; measure true-defect detection, false positives, advice acceptance/rejection and net repair, not pass rate or comment length.
3. Freeze semantics, then run separately pre-registered LF vs space format arms; do not change semantic candidate while testing separators.
4. Run paired navigation with fixed model, prompt, images, budgets and full denominator. Report recoveries, regressions, SR/SPL/nDTW, steps/path, and common-success path efficiency. Preserve all fallback and technical-failure records.
5. Use a scene/path-disjoint held-out set after development. Do not select the best prompt by per-episode navigation outcomes.

No result from this package should be called a gain until the corresponding model and navigation experiment has actually run.


## Runtime schema v2 integration checks

Before connecting a paid transport, verify the three runtime schemas are Draft 2020-12 and the host uses their exact names. In particular, do not regress `subtask_index` to `index`, or `source_fidelity` to `fidelity`. Confirm the Generator output schema reuses the shared Stage Audit/Handoff schemas; confirm Reviewer findings allow evidence indices across stages independent of repair-target indices; confirm R0/R1 both use the Reviewer schema and R1 receives `prior_review`, `prior_candidate`, and `prior_rendered_instruction`. Read `host/README.md` as the source of truth for the runtime field table and final verdict/fallback rules.


## v6 RxR profile-specific integration requirements

The repository branch `LLM-decompose-v6` already contains the v6 profile implementation. When integrating this package into AwareVLN, preserve the profile dispatch and do not recreate it inside the actor:

- R2R English remains on the v5 common rules and dynamic selection path. It must not load any RxR-specific rule or fixed core.
- RxR en-US loads the shared RxR semantic rules and the role-specific Generator or Reviewer guidance.
- Every normal RxR Generator call injects the ten fixed v5-format core cases in G01–G10 order, then 2–4 dynamic examples. G0 and G1 reuse the same IDs and content hash.
- Every normal RxR Reviewer call injects the ten independent fixed Reviewer cases R01–R10, then the paired dynamic Reviewer cases corresponding to Generator IDs, then 0–2 Diagnostics. R0 and R1 reuse the same IDs and content hash.
- The original v1 JSON files under `legacy/` are provenance only. Runtime reads the migrated v5-format `core/` copies. Do not copy v1 output schemas or prompt wording into the live contract.
- Fixed-core identity, role, language, dataset scope, count, order and Reviewer pair linkage are validated before G0. Failure must be a technical exact-source fallback before transport.
- The Host freezes RxR rule hashes and per-role fixed+dynamic template hashes for the full G0–R1 task. Do not reload a changed template set midway through repair/review.

The actor still receives only the final rendered instruction string. No fixed core ID, dataset rule, audit field, reviewer finding, template annotation or template hash is passed into AwareVLN Reason/Act.
