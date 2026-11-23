# LLM-decompose-v6.6.3

**当前权威说明。** 本仓库面向 R2R English 与 RxR en-US。两者共享语义合同、Runtime Schema、Renderer 和 Host 工作流；由 Adapter 的唯一 Profile 选择数据集专属规则、固定教学 Core 和 Dynamic Library。Generator 是唯一候选作者，Reviewer 独立审查并提出局部建议，Host 控制调用与释放，最终只向 AwareVLN 现有指令入口交付一条渲染后的自然语言指令。

本仓库的工程测试不等于真实模型语义准确率或导航性能。没有明确记录的实验结果，不得表述为 SR、SPL、nDTW 或导航成功率提升。

## 入口文档

- `WORKFLOW.md`：端到端数据流、阶段输入输出、状态和失败回退。
- `provenance/R2R_CORE_INDEPENDENT_REVIEW.md`：R2R Fixed Core 双轮模型辅助语义审查及来源元数据修复记录。
- `IMPLEMENTATION.md`：模块职责、关键设计约束和可维护性原则。
- `CODEX_START_HERE.md`：开发、集成和验收步骤。
- `host/README.md`：Runtime Schema、Host 调派、状态机和 Release Contract。
- `docs/EXPERIMENT_PLAN.md`：当前双 Profile 系统的受控语义、审查、格式和导航评测流程。
- `docs/R2R_ENHANCEMENT.md`：R2R English 专属规则、检索、Host 接入、RxR 隔离和验收规范。
- `docs/RXR_TEACHING_REPAIR.md`：本轮 RxR 教学修复、规则澄清、作者构建、实际教学卡及未验证事项。
- `docs/FORMAT_CONTRACT.md`：Source 字节、Renderer 和真实 Actor 请求/tokenization receipt 合同。
- `docs/V1_V5_V6_RULE_COMPARISON.md`：历史比较档案，仅用于追溯，不是当前实现规范。
- `shared/semantic_contract.md`：Generator/Reviewer 共用的唯一语义验收标准。
- `generator/prompt.md`、`reviewer/prompt.md`：角色提示词源文件；运行时文本由 `host/compile.py` 编译。

## 系统工作流

```text
Dataset record
  │
  ▼
Adapter: exact source + task identity + Host-only Path/Scan provenance + profile + SHA-256
  │
  ▼
Host: freeze profile, rules, core IDs, dynamic IDs and hashes
  │
  ▼
Generator G0 → schema/protocol validation
  │
  ▼
Renderer: freeze exact candidate snapshot
  │
  ▼
Reviewer R0: source-grounded L0–L6 independent review
  ├── PASS → release the exact reviewed snapshot
  ├── REVISE → Generator G1 receives findings and protected requirements
  └── UNRESOLVED
        ├── G0=needs_review (inactive) → exact original-source fallback
        └── G0=ok (active) → G1 reassesses the source limitation
                    │
                    ▼
              Renderer freezes new snapshot
                    │
                    ▼
              Reviewer R1 rechecks old findings and new defects
                    ├── PASS → release the exact R1-reviewed snapshot
                    └── otherwise → exact original-source fallback
```

G0/R0/G1/R1 均绑定同一个 Source Identity。G0/G1 使用同一 Generator Core 和 Dynamic IDs；R0/R1 使用同一 Reviewer Core 和 Dynamic IDs。R1 必须核验 R0 的每一条阻塞 Finding，不能只根据 G1 的自述接受修复。

## 两个数据集的 Profile

| 配置 | R2R English | RxR en-US |
|---|---:|---:|
| Generator Fixed Core | 10（G01–G10） | 10（G01–G10） |
| Reviewer Fixed Core | 10（R01–R10） | 10（R01–R10） |
| Generator Dynamic Eligible | 25 | 43（35原有＋8训练源） |
| Generator Dynamic per task | 6–8 | 2–4 |
| Reviewer Paired Dynamic Eligible | 29 | 43（35原有＋8训练源） |
| Reviewer Paired per task | 6–8 | 2–4 |
| Reviewer Diagnostics Eligible | 23 | 37（29原有＋8训练源） |
| Reviewer Diagnostics per task | 2–4 | 0–2 |

磁盘来源数、Core 数、Dynamic Eligible 数和单任务实际选择数是不同概念，禁止混用。固定 Core 无条件加载且顺序稳定；Dynamic 只从当前 Profile 的白名单目录检索；Legacy 仅用于来源追溯，不进入运行时。

R2R 只加载 R2R Rules/Core/Library；RxR 只加载 RxR Rules/Core/Library。共享合同只保存两个数据集共同遵守的语义标准，不承载数据集专属例外。

## 模块边界

| 模块 | 唯一职责 | 禁止事项 |
|---|---|---|
| Adapter | 识别数据集、语言、Split、稳定任务身份，保留原始指令 | 改写、切分、推断路线或传递 GT/轨迹给模型 |
| Generator | 阅读完整 Source，决定 KEEP/SPLIT，输出完整 Candidate 和 Stage Audit | 读取导航分数、把 Reviewer 建议当命令 |
| Reviewer | 独立核对 Source/Candidate、阶段、依赖和 Handoff | 自己重写 Candidate、引入 Source 外事实 |
| Renderer | 来源可追溯的字符串装配、冻结和哈希 | 语义纠错、审核后改写 |
| Host | Profile 派发、Prompt 编译、调用、校验、修复和 Release | 跨数据集回退、跳过审查或技术失败时释放候选 |
| Shared | 语义合同、身份和哈希工具 | 复制或覆盖数据集专属规则 |

## 关键语义约束

每个 Stage 都要有可执行的 Entry、Target、Process、Ending 和 Conditions。切分必须有来源支持的前一阶段完成事件、下一阶段尚未执行的目标、连续 Handoff 和明确的局部焦点收益。动作动词数量、句子数量、房间名或标点不能单独决定切分。

观察线索不能自动变成导航目标；看到门不等于穿过门；靠近目标不等于到达；阶段边界不等于 STOP。Ordinal、方向参照、时间条件、否定、数量、目标身份和最终位置必须保留其原始作用域。

Reviewer 的 PASS/REVISE/UNRESOLVED 必须来自当前 Source 和 Candidate 的证据。教学案例的 Verdict 不是当前任务的投票。只有 Source 本身存在影响路线选择且无法消解的关键歧义，才允许 UNRESOLVED。

## Renderer 与交付边界

- 原始 Source 解码后精确保留；不得全局 `strip`、Unicode 规范化、`split/join` 或改写换行。
- `BOUNDARY_ONLY` 只在批准的阶段边界替换分隔空白；阶段内部文本保持原样。
- `ASSEMBLED_SINGLE/MULTI` 必须记录 COPY/MOVE/EDIT/EDIT_SEAM 来源。
- Reviewer 审查的冻结字符串必须与最终 Release 字符串完全一致。
- 技术失败和输入失败不能标记为 navigation-eligible；有效 Source 存在时回退到精确原文。
- AwareVLN 只接收最终 `instruction` 字符串，不接收 Template、Finding、Stage Audit 或 Profile 元数据。

## 构建与验证

在 Python 3.11 环境安装 `requirements.txt` 后执行：

```bash
python -B tools/build_rxr_reviewed.py --check
python -B -m host.compile
python -B verify_package.py
python -B -m unittest discover -s tests -v
python -m examples.demo
python -m evaluation.smoke24
```

作者侧重建和完整历史要求见 `docs/RXR_TEACHING_REPAIR.md`。`test_release_transaction.py` 需要仓库外的配套 `manage_release.py`；缺失时应单独记录未运行，不计为通过。CI 的实际测试数、限制和隔离结果保存在 `provenance/rxr_validation.json`。

编译后必须检查六份 Compiled Prompt 和 Build Manifest：每个 Profile/Role 都应有十条固定 Core；R2R/RxR Dynamic IDs 只能来自本 Profile 的允许目录；Legacy 不得进入 RxR 运行时；Schema 必须处于约定的 Prompt 位置。所有编译产物必须提交并通过完整性校验。

真实模型调用、盲审语义评估、Tokenizer 捕获和导航 Rollout 属于独立实验。离线 Fixture、Smoke 和 CI 不能替代这些实验。

## 数据来源与评测

教学来源与评测 Split 必须显式区分。R2R 教学沿用各文件的 val_seen 来源记录。RxR Core 包含可追溯训练来源以及明确标注的合成或改编案例；动态库包含原有 val_seen 来源和八组经过官方归档核验的 train/guide/en-US 来源。所有分割、审计和单缺陷负例都是作者教学标注，不是官方子任务或轨迹金标。

正式评测前按原始 split、instruction/episode/path ID、scene/scan ID 和原文哈希交叉核验。当前评测案例不注入 Runtime Few-shot。来源真实、引文存在与教学语义正确是不同验收条件，不能混用。数据定义参考 [R2R task data documentation](https://github.com/peteanderson80/Matterport3DSimulator/blob/master/tasks/R2R/README.md) 和 [RxR dataset repository](https://github.com/google-research-datasets/RxR)。

## 当前工程状态

当前分支从 `LLM-decompose-v6.6.2` 的固定提交建立，保留原分支不变。本轮先修正既有 RxR 教学，再加入六类局部语义判据澄清；不改变 R2R 专属资产、通用规则、运行 Schema、Renderer 或有界双角色工作流。固定 Core 身份、动态数量、来源和检索策略保持不变。

逐字段修正记录见 `provenance/rxr_teaching_changes.json`，作者规格和构建检查见 `tools/build_rxr_reviewed.py`。存在争议的足床位置解释和辅助玻璃方位叙述继续显式记录，不标为已证明。候选仍需真实语义盲审和导航对照；本轮不宣称追回任何固定数量的成功，也未将计划中的三组新增来源混入修复实验。

发布标识仅在 README 展示；新增规则、作者工具、测试和技术文档不加入发布后缀。继承的 Schema 身份、历史来源和兼容路径保留，不为清除字符串而破坏接口或追溯记录。全仓库历史标识与当前新增发布标识分别记录。

## RxR semantic calibration

RxR-only event, correction, relation and entry calibration with eight verified train-guide lesson groups. Fixed Core and per-request example counts are unchanged. R2R is protected by four-phase prompt/schema and selection comparisons. See [the implementation and validation contract](docs/RXR_ENHANCEMENT.md) and [the teaching repair contract](docs/RXR_TEACHING_REPAIR.md). Engineering checks do not establish navigation gains.
