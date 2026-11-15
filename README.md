# final-best-v1｜VLN 子任务生成、审核、装配与格式冻结

**定位：** 这是基于完整 R2R/RxR 轨迹审计、用户分析和 v1.3 语义基线整理出的最终综合版本，面向 **R2R English** 与 **RxR en-US**。Generator 仍是唯一语义作者；Reviewer 是独立诊断者；Adapter 只读取原始记录；Renderer 只做来源可追溯的机械装配与冻结；Host 只编排两角色调用并执行技术合同。

本包没有运行新的模型或导航实验。单元测试通过只能证明接口、来源追踪和技术合同可运行，不能证明分割语义准确或 SR/SPL/nDTW 提升。

## 先看什么

1. `WORKFLOW.md`：完整数据流、模块顺序和失败回退。
2. `IMPLEMENTATION.md`：最终设计取舍、关键边界和实验顺序。
3. `CODEX_START_HERE.md`：交给 Codex 的逐步接入合同。
4. `shared/semantic_contract.md`：Generator/Reviewer 唯一共同验收标准。
5. `generator/prompt.md`、`reviewer/prompt.md`：两角色可维护提示词；实际调用文本由 `host/compile.py` 编译。

## 工作流

```text
R2R en / RxR en-US source row
        │
        ▼
adapter: exact source + task identity + SHA-256 + source envelope
        │  (only original_instruction is sent to semantic roles)
        ▼
Generator G0 ── one candidate JSON
        │
        ▼
Renderer: freeze exact stage strings + source provenance + LF join
        │
        ▼
Reviewer R0: layered C01–C12 audit + per-stage checks + adjacent handoffs
        │
        ├── pass ───────────────────────────────► commit the same frozen snapshot
        │
        ├── unresolved/source-limited ──────────► exact original source fallback
        │
        └── revise ─► Generator G1 independently accepts / partially accepts /
                      rejects / leaves findings unresolved
                      │
                      ▼
                Renderer: freeze new snapshot
                      │
                      ▼
                Reviewer R1 in a fresh context; no R0 verdict/history is supplied
                      │
                      ├── pass ─► commit that exact snapshot
                      └── otherwise ─► exact original source fallback

Committed instruction ─► existing AwareVLN instruction slot
                         (no new goal switch, memory, STOP hook or state reset)
```

## Directory responsibilities

| Directory | Owns | Must not do |
|---|---|---|
| `generator/` | Full-source interpretation, boundary selection, local-context assembly, only candidate author, one independent repair decision | Read scores/GT, trust reviewer suggestions automatically, claim actions completed |
| `reviewer/` | Independent source-grounded C01–C12 audit, each stage and each handoff, factual findings and local repair options | Rewrite candidate, author a replacement route, see navigation scores, act as a third/primary reviewer |
| `adapter/` | R2R/RxR English schema intake, task key, exact decoded string, UTF-8 hash, read-only prefix/body/suffix features | Trim/normalize, segment, infer a route, pass trajectory/GT/score to LLM |
| `renderer/` | SOURCE_EXACT / BOUNDARY_ONLY / ASSEMBLED_SINGLE / ASSEMBLED_MULTI preview, whitespace provenance ledger, exact frozen string | Semantic correction, SR-based choice, post-review cleanup, reject a semantically valid split for style |
| `host/` | Compile prompts, validate schemas/quotes/hashes, bounded G0-R0-G1-R1 flow, same-snapshot commit or exact fallback | Add a chief reviewer, call online goal switches, change AwareVLN internals |
| `shared/` | The one semantic acceptance contract and identity/hash helpers | Duplicate or contradict role-specific standards |
| `generator/templates/` and `reviewer/templates/` | 35 examples per role/profile; default 8 selected once per role/task | Serve as hidden route facts or unique gold segmentations |
| `evaluation/` | Paired full-denominator summaries and technical smoke cases | Feed scores into Generator/Reviewer or delete failures from the denominator |
| `provenance/` | Input lineage, evidence summary, source analyses and build hashes | Claim new navigation results or unverified causal explanations |

## Acceptance principles

Each stage must preserve five semantic properties: entry context, prescribed process, target/identifying information, completion or terminal objective, and conditions/constraints. The roles also share five dependency families: until; after/once/when/then; before; while/keep/stay; if/otherwise/either/or. Both roles use the same C01–C12 checklist and the same evidence hierarchy S1/S2/S3; S4 (layout guesses, GT, scores or another episode) is prohibited.

A useful split requires a supported previous exit, a supported next entry, a distinct next objective, and no broken condition/entity/count/frame. Short instructions are not automatically single-stage; a multi-action maneuver is not automatically multi-stage. `toward X` may be a terminal goal directive when it is the final source command, but this never means the agent reached or entered X.

## Renderer and format contract

- Unchanged/fallback source is returned byte-for-byte after UTF-8 decoding/encoding; no global `strip`, `splitlines`, `split/join`, `unicode_escape`, NFC/NFKC or case normalization.
- `BOUNDARY_ONLY` replaces only the source whitespace at approved stage cuts with LF; copied stage interiors remain untouched.
- `ASSEMBLED_SINGLE` and `ASSEMBLED_MULTI` keep reliable source COPY/MOVE spans and record EDIT/EDIT_SEAM explicitly. Ambiguous repeated spans are not assigned arbitrarily.
- The source prefix/suffix are preserved exactly. Dataset-specific statistics are descriptive; there is no hard-coded “R2R must add one trailing space” or “RxR must trim” rule.
- Stage count comes from the array/metadata, not `splitlines()`; native LF/CRLF inside a stage may remain.
- The same frozen `rendered_instruction` reviewed by R0/R1 is the string committed to the existing actor input slot.

## Offline verification

Python 3.10+; install `requirements.txt`, then run:

```bash
python -m host.compile
python -B -m unittest discover -s tests -p test_entry_diagnostics.py -v
python -B -m unittest discover -s tests -p test_closed_loop_35.py -v
python -B -m unittest discover -s tests -p test_roles_repair.py -v
python -B -m unittest discover -s tests -p test_release_transaction.py -v
# Run the complete inherited suite separately and compare known baseline failures:
python -B -m unittest discover -s tests -v
python -m examples.demo
python -m evaluation.smoke24
python verify_package.py
```

The demo uses explicitly labeled fixtures and does not call a real LLM or run navigation. Real model integration requires an existing transport callback that reports actual model, effort and request ID. Do not treat a requested alias as a verified provider receipt.

## Evidence limits

The source analysis reports 1,839 uploaded R2R evaluation records and 1,223 uploaded RxR en-US evaluation records. Their whitespace statistics are descriptive for those files, not universal dataset rules. The report documents previous runs (R2R baseline 1207/1839, current tested p1/v2 1197/1839; RxR old D 848/1223 vs baseline 827/1223) but those are not results of final-best-v1. No new generator/reviewer calls, tokenizer capture, navigation rollout or independent held-out validation were run to create this package.

## Entry diagnostics release 1

This variant preserves the existing two-role call budget and renderer, adds one shared entry-context definition and located diagnostics, and aligns accepted Generator/Reviewer entry checks. It is an engineering revision; no new model or navigation results are claimed. `generator/acceptance.md` is a synchronized reference copy of `shared/semantic_contract.md`; only the latter is compiled.

Results retain `error` and add `diagnostic` (null on success). Failures identify module, phase, host step and JSON pointer. A technical entry violation does not prove route text wrong. Call state distinguishes request construction, transport entry/return and verified versus invalid receipt. Transport failure leaves remote execution unknown and never causes an automatic retry. Source-loading failure produces `input_failed` without invented instruction or identity.

Current regression commands above exercise offline fixtures only. The two inherited legacy test files are retained and still expose 18 baseline failures/errors associated with older interfaces and renderer expectations. They are not skipped or represented as passing. Full before/after evidence, exact diffs, original archive, installation journal and rollback tool are in `docs/stages/v5-entry-diagnostics-20261114-r0` under the case1 root. The release transaction test uses that companion tool.

This release does not repair the known terminal-disclaimer keyword rule, change missing-split policy, alter the active-candidate unresolved branch, add retries, or modify evaluation/model/STOP/image settings. Do not replay an old result with the new prompt or compare full result dictionaries across versions as if they were identical. Use its recorded frozen original package.
