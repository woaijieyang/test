# Host Runtime Contract

Host 是唯一的 Profile 派发、Prompt 编译、模型调用、状态推进和最终释放控制器。Adapter 提供唯一 Source Identity；Host 不通过指令文本猜测数据集，不允许 Generator 与 Reviewer 使用不同 Profile。

## 1. Profile 与规则装配

| Profile | Rules | Generator Core | Reviewer Core |
|---|---|---|---|
| `r2r-en` | Shared Contract + R2R shared rules + role-specific R2R guidance; Host-only R2R fragments | R2R G01–G10 | R2R R01–R10 |
| `rxr-en-us` | Shared Contract + RxR shared rules + role-specific RxR guidance | RxR G01–G10 | RxR R01–R10 |

两种 Profile 均固定加载十条 Core。R2R 不得加载任何 RxR Rules、Core 或 Dynamic；RxR 不得加载任何 R2R Rules、Core 或 Dynamic。未知 Profile、缺失 Core、身份不匹配或模板 Schema 错误必须在模型调用前 fail closed。

## 2. Template 装配

R2R Generator 从显式允许的 `templates/R2R/val_seen/` 检索，使用 R2R-only fragment features/ranker；R2R Reviewer 从 `templates/R2R/paired/` 和 `templates/R2R/diagnostics/` 检索。Fragment 只影响教学案例排序，不决定 KEEP/SPLIT。Core 目录不属于 Dynamic Pool。RxR 使用其独立的 Core、val_seen、paired 和 diagnostics 目录；`legacy/` 仅用于来源追溯。

| Profile | Generator Dynamic | Reviewer Paired | Reviewer Diagnostics |
|---|---:|---:|---:|
| R2R | 4–6 / task | 4–6 / task | 2–3 / task |
| RxR | 2–4 / task | 2–4 / task | 0–2 / task |

磁盘来源数量、可检索数量、Core 数量和单任务选择数量必须分别记录。Reviewer Paired 选择依赖当前任务选中的非 Core Generator Dynamic IDs；Diagnostics 独立补充。Reviewer Core 的 `pair_id` 是教学来源关系，不是运行时强制配对顺序。

## 3. Prompt Assembly

R2R Generator：common role prompt → Shared Semantic Contract → R2R shared rules → R2R Generator role guidance → Fixed Core → Dynamic → active schema → current Source。

R2R Reviewer：common role prompt → Shared Semantic Contract → R2R shared rules → R2R Reviewer role guidance → Reviewer Checklist → Fixed Core → Paired Dynamic → Diagnostics → active schema → current Source/Candidate/rendered text。

RxR 保留其 Profile 专属规则与角色指导的既定装配顺序；RxR 静态构建结果必须与运行时编译一致。Generator Repair 使用完整 Generator repair schema 和相同冻结的 Generator Core/Dynamic；Reviewer Recheck 使用完整 Reviewer schema 和相同冻结的 Reviewer Core/Dynamic。

`examples=False` 只允许关闭可选 Dynamic，不得跳过固定 Core。显式 `selected_ids` 只能选择当前 Role/Profile 的 Dynamic Library，不能覆盖或替换 Core。

## 4. Runtime Wire Schemas

| 阶段 | Role | Schema | 必须输入 |
|---|---|---|---|
| G0 | Generator | `generator/output.schema.json` | 原始 Source |
| R0 | Reviewer | `reviewer/output.schema.json` | Source + frozen Candidate + exact rendered text |
| G1 | Generator | `generator/repair.schema.json` | Source + R0 Candidate + 完整 R0 Review |
| R1 | Reviewer | `reviewer/output.schema.json` | 新 Candidate/rendered text + frozen R0 Review/Candidate/rendered text |

Teaching Template Schema 与 Runtime Wire Schema 不可混用。Generator 的 Stage Index 使用 `subtask_index`；Reviewer dimension 使用 `source_fidelity`；Candidate Evidence 使用 `{subtask_index, quote}`。R0 的 `prior_finding_reviews` 必须为空；R1 必须按顺序逐条处置全部 R0 blocking Findings。

## 5. Release State Machine

```text
Source/Profile validation
  → freeze rules/core/dynamic/prompt hashes
  → G0 → validate → render/freeze S0 (or exact Source if G0=needs_review)
  → R0
      PASS       → release exactly S0
      REVISE     → G1 → validate → render/freeze S1 → R1
      UNRESOLVED
        G0=needs_review → exact source fallback
        G0=ok           → G1 reassesses the source limitation → R1
      R1
        PASS and all old blockers resolved → release exactly S1
        otherwise → exact source fallback
```

G1 由 R0=REVISE 触发；若 R0=UNRESOLVED 但 G0 Candidate 仍为 active（status=ok），Host 也允许 G1 对 Source ambiguity 作有界复核。只有 G0 本身为 inactive `needs_review` 且 R0 确认 UNRESOLVED 时才直接回退原文。G1 必须对每条 R0 Finding 给出 accept/partially_accept/reject/unresolved 的明确响应，并返回完整 Candidate。R1 必须在新 Reviewer session 中重新审查整个新 Candidate，逐条验证旧 Finding 是否真正解决，并检查新增缺陷；R1 会收到冻结的 R0 Review、旧 Candidate 和旧 rendered text，但不会收到 G1 的回复/解释作为证据。模型自述、旧 Verdict 或修复建议都不能替代新 Candidate 证据。

## 6. Snapshot、Failure 与 Fallback

R0 审核的 Snapshot 必须是进入 G1 的原始 Candidate Snapshot；R1 审核的 Snapshot 必须是最终 Release 的 Snapshot。审核后任何文本变化都必须重新 Freeze 和 Review。

技术失败、输入失败不得标记为 navigation-eligible。无效 Receipt、Schema/Protocol 错误、Snapshot 不匹配、Template/Rules Hash 变化均不得释放未经审核的 Candidate。存在有效 Source 时，安全回退必须返回精确原始指令。对远端调用状态不确定时不得盲目重试。

Provider Receipt 至少校验实际 model、effort、request_id；若提供 `provider_request_sha256`，必须与当前 canonical request hash 一致。未提供该字段时应明确记录为不可验证，而不是伪造验证通过。

## 7. Identity、Hash 与记录

每条结果记录完整 `source_identity`：task_key、dataset、language、split、source_sha256、profile。每次调用记录 role、phase、model、effort、request_id、request hash、Prompt Components Hash、Schema Hash、Rules Hash、固定 Core IDs、Dynamic IDs 和 Template Bundle Hash。

G0/G1 和 R0/R1 各自复用冻结的规则、Core、Dynamic 与组件 Hash。缓存、重启或并发不得让不同 Source/Profile 的选择结果互相覆盖。

## 8. Build 与 Integrity

`python -B -m host.compile` 是 Compiled Prompt、Template Index 和 Build Manifest 的唯一生成入口。禁止手工编辑 Compiled Prompt。编译结果必须包含正确 Core、Dynamic 和 active schema，Build Manifest 必须反映生成文件的实际 SHA、字节数、Core IDs、Dynamic IDs 和 Profile。

CI 必须在编译后再次运行完整性校验，并执行工作区差异检查；如果生成文件与提交文件不一致，构建失败。RxR 的 Prompt 组件、Core、Dynamic 选择和装配行为必须通过独立冻结测试。

## R2R Rules and provenance

R2R rules metadata freezes the shared R2R rules, Host-side fragment registry, Generator role guidance, and Reviewer role guidance. Per-role prompt metadata freezes only the role guidance that contributes to that prompt. G0/G1 reuse the same Generator bundle; R0/R1 reuse the same Reviewer bundle. The R2R fragment registry is not included in the model payload. The generic selector path and RxR feature/ranking behavior remain unchanged.
