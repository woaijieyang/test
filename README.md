# LLM-decompose-v6.3｜R2R / RxR 统一导航指令分割系统

**当前权威说明。** 本仓库面向 R2R English 与 RxR en-US。两者共享语义合同、Runtime Schema、Renderer 和 Host 工作流；由 Adapter 的唯一 Profile 选择数据集专属规则、固定教学 Core 和 Dynamic Library。Generator 是唯一候选作者，Reviewer 独立审查并提出局部建议，Host 控制调用与释放，最终只向 AwareVLN 现有指令入口交付一条渲染后的自然语言指令。

本仓库的工程测试不等于真实模型语义准确率或导航性能。没有明确记录的实验结果，不得表述为 SR、SPL、nDTW 或导航成功率提升。

## 入口文档

- `WORKFLOW.md`：端到端数据流、阶段输入输出、状态和失败回退。
- `IMPLEMENTATION.md`：模块职责、关键设计约束和可维护性原则。
- `CODEX_START_HERE.md`：开发、集成和验收步骤。
- `host/README.md`：Runtime Schema、Host 调派、状态机和 Release Contract。
- `shared/semantic_contract.md`：Generator/Reviewer 共用的唯一语义验收标准。
- `generator/prompt.md`、`reviewer/prompt.md`：角色提示词源文件；运行时文本由 `host/compile.py` 编译。

## 系统工作流

```text
Dataset record
  │
  ▼
Adapter: exact source + task identity + profile + SHA-256
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
  ├── UNRESOLVED → exact original-source fallback
  └── REVISE → Generator G1 receives findings and protected requirements
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
| Generator Dynamic Eligible | 25 | 35 |
| Generator Dynamic per task | 6–8 | 2–4 |
| Reviewer Paired Dynamic Eligible | 29 | 35 |
| Reviewer Paired per task | 6–8 | 2–4 |
| Reviewer Diagnostics Eligible | 23 | 29 |
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
python -B -m host.compile
python -B verify_package.py
python -B -m unittest discover -s tests -v
python -m examples.demo
python -m evaluation.smoke24
```

编译后必须检查六份 Compiled Prompt 和 Build Manifest：每个 Profile/Role 都应有十条固定 Core；R2R/RxR Dynamic IDs 只能来自本 Profile 的允许目录；Legacy 不得进入 RxR 运行时；Schema 必须处于约定的 Prompt 位置。所有编译产物必须提交并通过完整性校验。

真实模型调用、盲审语义评估、Tokenizer 捕获和导航 Rollout 属于独立实验。离线 Fixture、Smoke 和 CI 不能替代这些实验。

## 数据来源与评测

R2R 固定 Core 与 Dynamic 教学材料包含 val_seen 来源。评测前必须核对 Episode、Instruction 和 Scan 的重叠；不得把包含教学来源样本的评测结果称为无泄漏的独立验证。优先采用与教学来源隔离的评测 Split，并保留完整分母、Fallback 和技术失败记录。

## 当前工程状态

当前分支包含双 Profile 固定 Core、数据集专属规则、动态检索、完整双角色闭环、Snapshot Release、来源追踪和离线回归测试。任何后续改动必须保持 R2R/RxR 隔离，并以可复现的构建和行为测试证明未改变既有功能。
