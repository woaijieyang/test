# LLM-decompose-v6.6.4

**当前权威说明。** 本仓库面向 R2R English 与 RxR en-US。两者共享语义合同、Runtime Schema、Renderer 和 Host 工作流；由 Adapter 的唯一 Profile 选择数据集专属规则、固定教学 Core 和 Dynamic Library。Generator 是唯一候选作者，Reviewer 独立审查并提出局部建议，Host 控制调用与释放，最终只向 AwareVLN 现有指令入口交付一条渲染后的自然语言指令。

本仓库的工程测试不等于真实模型语义准确率或导航性能。没有明确记录的实验结果，不得表述为 SR、SPL、nDTW 或导航成功率提升。

## 当前 R2R 最小改动交付

运行时专属能力位于 `host/r2r/`，离线作者工具位于 `tools/r2r_authoring/`，测试位于 `tests/r2r/`；根目录旧模块已移除。详见 `docs/R2R_MINIMAL_REPORT.md`。当前380项回归通过；显式选例、真实规则链接和阶段教学的入口校验已补齐，RxR集成CI在本树只读验证。详见 `docs/R2R_STABILITY_REPORT.md`。RxR受保护文件与四阶段请求保持一致；原始1068条来源重放与前一提交逐字节一致，不代表真实LLM或导航收益。

## 入口文档

- `docs/WORKFLOW.md`：端到端数据流、阶段输入输出、状态和失败回退。
- `provenance/R2R_CORE_INDEPENDENT_REVIEW.md`：R2R Fixed Core 双轮模型辅助语义审查及来源元数据修复记录。
- `docs/IMPLEMENTATION.md`：模块职责、关键设计约束和可维护性原则。
- `docs/CODEX_START_HERE.md`：开发、集成和验收步骤。
- `host/README.md`：Runtime Schema、Host 调派、状态机和 Release Contract。
- `docs/EXPERIMENT_PLAN.md`：当前双 Profile 系统的受控语义、审查、格式和导航评测流程。
- `docs/R2R_ENHANCEMENT.md`：R2R English 专属规则、检索、Host 接入、RxR 隔离和验收规范。
- `docs/RXR_TEACHING_REPAIR.md`：本轮 RxR 教学修复、规则澄清、作者构建、实际教学卡及未验证事项。
- `docs/RXR_TEACHING_FOCUS.md`：Core案例级教学、局部覆盖证据、保守正文修订及建议采纳边界。
- `docs/RXR_DATA_BOUNDARIES.md`：训练来源、生成文件、配对、缓存与写入失败处理。
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
| Generator Dynamic Eligible | 27（25原有＋2合成教学） | 43（35原有＋8训练源） |
| Generator Dynamic per task | 4–6 | 2–4 |
| Reviewer Paired Library | 31（27可配对选择＋4保留源） | 43（35原有＋8训练源） |
| Reviewer Paired per task | 4–6 | 2–4 |
| Reviewer Diagnostics Eligible | 28（26原有＋2合成反例） | 37（29原有＋8训练源） |
| Reviewer Diagnostics per task | 2–3 | 0–2 |

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
python -B tools/verify_package.py
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

当前分支从 `LLM-decompose-v6.6.2` 的固定提交建立，保留原分支不变。已有 RxR 教学修复及六类局部语义判据继续保留。本轮进一步完善十组Core的案例级教学重点、33条正常覆盖证据及002/020的最小来源保留表达，连同对应Reviewer和依赖诊断一起重建。不改变 R2R 专属资产、通用规则、运行 Schema、Compiler优先级、Renderer 或有界双角色工作流。固定 Core 身份、动态数量、来源和检索策略保持不变。

逐字段修正记录见 `provenance/rxr_teaching_changes.json`，作者规格和构建检查见 `tools/build_rxr_reviewed.py`。足床终态现在保留为结果状态而不新增继续移动命令；玻璃窗的矛盾辅助描述不被擅自消歧，也不再将source审计说明放入Actor文本。它们的真实环境解释和导航收益仍未被证明。候选仍需独立语义盲审和导航对照；本轮不宣称追回任何固定数量的成功，也未将计划中的三组新增来源混入修复实验。

发布标识仅在 README 展示；新增规则、作者工具、测试和技术文档不加入发布后缀。继承的 Schema 身份、历史来源和兼容路径保留，不为清除字符串而破坏接口或追溯记录。全仓库历史标识与当前新增发布标识分别记录。

## RxR semantic calibration

RxR-only event, correction, relation and entry calibration with eight verified train-guide lesson groups. Fixed Core and per-request example counts are unchanged. R2R is protected by four-phase prompt/schema and selection comparisons. See [the implementation and validation contract](docs/RXR_ENHANCEMENT.md), [the teaching repair contract](docs/RXR_TEACHING_REPAIR.md), [the case-specific teaching calibration](docs/RXR_TEACHING_FOCUS.md) and [the data-boundary checks](docs/RXR_DATA_BOUNDARIES.md). Engineering checks do not establish navigation gains.

R2R 新实现、父分支差异和验证边界见 `docs/R2R_IMPLEMENTATION.md`。完整作者资产用 `python -B -m tools.r2r_authoring.build --check` 校验；当前模型和导航性能仍需独立实验。

## R2R 精细化整改与已知限制

当前 R2R 保留原119份来源资产，另显式登记6份合成教学资产，用于条件分支和返回路线的正反对照。这些不是官方R2R指令或评测失败样本。两个角色各10条固定Core保持不变；Generator选择4–6条Dynamic，Reviewer跟随相同配对并补充2–3条Diagnostics。

模块归属与36项实施台账见 [R2R整改记录](docs/R2R_REFINEMENT_REPORT.md)；机器可读状态见 `provenance/r2r_issue_ledger.json`。教学索引归属 `host/r2r/teaching_index.json`，作者来源清单归属 `tools/r2r_authoring/source_inventory.json`，完整性校验入口为 `python -B tools/verify_package.py`。根目录 `FILE_HASHES.json` 保留为全仓库完整性契约。

`python -B -m tools.r2r_authoring.audit` 对37条教学来源执行148个阶段编译与投影核对。这是开发自检，不是独立测试集。可以通过 `--records <JSON或JSONL路径> --output <报告路径>` 接入真实冻结来源清单，输入字段为 `original_instruction`、可选 `task_id`、`source`、`split`，不得将成绩或轨迹作为检索特征。

原始Excel、1068条原始运行记录及导航轨迹本次未提供，因此没有复算73条退化与52条恢复，也没有进行真实LLM或导航测评。尚缺有独立实质损害依据的C10欠分割金标准案例；不能将合法粗粒度分组改标为错误以补齐数量。固定Core仍含val_seen来源，重叠报告不等于正式测评隔离认证。

## R2R complete Dynamic loading (local experiment)

Every selected R2R Generator, paired Reviewer, and diagnostic Reviewer Dynamic case now uses a complete runtime demonstration in G0/R0/G1/R1. The summary path is disabled. Full `expected_output` fields, exact source and Reviewer candidate are retained; authoring provenance remains Host-side. Core IDs, selection counts, retrieval, pairing, semantic rules, Runtime Schemas, Renderer and RxR behavior are unchanged. See `docs/R2R_FULL_DYNAMIC.md` for the contract and validation boundary.
