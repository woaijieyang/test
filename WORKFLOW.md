# Workflow and Data Contracts

## 1. Source Intake

Adapter 只负责解析记录 Envelope、识别 Dataset/Language/Split、生成稳定 task identity、保留原始 instruction 并计算 SHA-256。当前支持 R2R English 与 RxR en-US。原始指令只解码一次，不做 trim、Unicode normalization、大小写转换、`unicode_escape` 或 split/join。模型只收到原始指令文本，不收到 GT、轨迹、路径、分数或 Scene 元数据。

每条 Source Identity 包含 task_key、dataset、language、split、source_sha256 和 profile。正式评测必须提供明确且合法的 Split；开发数据可以使用 unspecified，但不得冒充正式评测记录。相同 task_key 对应不同 Source Hash 时必须报告冲突。

## 2. Profile Dispatch and Frozen Inputs

Adapter Profile 是数据集规则和模板派发的唯一依据。Host 在 G0 前确定并冻结：
- Profile 与 Dataset Rules 文件及 Hash；
- Generator Fixed Core IDs/Hash；
- Reviewer Fixed Core IDs/Hash；
- Generator Dynamic IDs/Hash；
- Reviewer Paired/Diagnostics IDs/Hash；
- Prompt Components、Schema 和 Runtime Bundle Hash。

R2R/RxR 不允许跨目录、跨规则或跨 Schema 回退。固定 Core 每个 Role 十条，顺序稳定且不参与检索。Dynamic 仅来自明确的 Profile allowlist。

## 3. G0 — Candidate Authoring

Generator 阅读完整 Source，识别事件顺序、目标、参照物、空间转换、条件、完成事件和潜在阶段边界。每个 Stage 都必须给出 Entry、Target、Process、Ending、Conditions，并保留 source_quotes、candidate_quotes 和 carryover。每个相邻阶段必须有 Handoff。

KEEP 与 SPLIT 都必须是主动决策。不得按动词、句子、房间名或长度机械切分。阶段边界不是物理 STOP；看到目标不等于到达；靠近不等于进入。无法安全解析路线关键 Source 歧义时使用既有 needs_review 路径，不猜测目标。

## 4. Renderer Freeze

Renderer 对 Candidate 进行来源可追溯装配，生成精确 rendered_instruction、来源 Ledger、Snapshot ID 和 Hash。它不修正语义，不因导航指标选择 Candidate，也不在 Reviewer 通过后清理文本。SOURCE_EXACT 和 fallback 必须返回精确原文；BOUNDARY_ONLY 只替换获批边界分隔符；ASSEMBLED 模式必须记录 COPY/MOVE/EDIT/EDIT_SEAM。

## 5. R0 — Independent Review

Reviewer 收到 Source、冻结 Candidate 和精确 rendered_instruction，不接收 Generator 的 Stage Audit/Handoff 自评。Reviewer 按 L0–L6 检查完整 Source Coverage、依赖、每个 Stage、相邻 Handoff、分组质量和全路线回读。Finding 必须有真实 Source/Candidate 证据、影响、最小局部修复建议和受保护要求。教学案例不是 Verdict 投票；无证据的风格偏好不得成为阻塞 Finding。

## 6. G1 — Bounded Repair

R0=REVISE 进入 G1。R0=UNRESOLVED 时要结合 G0 状态处理：如果 G0 返回的是 active Candidate（status=ok），Host 也允许进入 G1，让 Generator 基于完整 Source 独立判断该歧义是否确实无法消解，还是 Reviewer 对一个可执行 Candidate 的过度拒绝；如果 G0 已返回 inactive `needs_review`，且 R0 仍确认 Source-level ambiguity，则不生成猜测路线，直接精确原文回退。G1 接收完整 Source、旧 Candidate、R0 Findings 和受保护要求。每条 Finding 必须有一条明确响应；Generator 可以拒绝不受 Source 支持的建议。G1 必须返回完整 Candidate，不是 Patch。不得为了修一个局部问题破坏其他已满足的 Source Requirement。

## 7. R1 — Fresh Recheck

R1 使用新审查上下文，接收新 Candidate、新 rendered text、冻结 R0 Review、旧 Candidate 和旧 rendered text。它必须逐条核验所有旧 Finding 的 resolved/partially_resolved/unresolved 状态，并重新审查整个新 Candidate。只有所有旧阻塞问题解决、没有新增阻塞问题且三项质量维度全部通过，才能释放新 Snapshot。

## 8. Release and Failure

R0 PASS 释放 Reviewer 实际审查的同一个 Snapshot。R0 REVISE 进入 G1；R0 UNRESOLVED 在 G0 为 active Candidate 时也可进入 G1 重新判定，在 G0 为 inactive `needs_review` 时则精确原文回退。G1 后必须经过 R1；只有 R1 PASS 且旧阻塞 Finding 全部 resolved、当前 Candidate 无新增阻塞问题时，才释放 R1 实际审查的 Snapshot。R1 非 PASS、技术失败或 Snapshot/Hash 不一致均回退到精确 Source。技术失败不是语义失败诊断，Fallback 不是导航成功。所有失败保留在评测分母和运行记录中。

## 9. Actor Boundary

AwareVLN 现有 instruction slot 只接收最终 instruction 字符串。不得新增 Goal Switch、STOP Hook、Memory、Graph Memory、Completion Detector，也不得修改 Reason/Act、图像输入、Action Space、预算或 last_reasoning。Tokenization 必须在现有 Actor 构造完整请求之后采集完整 Prompt Token IDs，不得逐 Stage tokenize 后拼接。

## 10. Evaluation Hygiene

教学来源必须可追溯到 Split、Episode、Instruction 和 Scan。R2R Core/Dynamic 使用 val_seen 来源，正式评测前必须核对样本和 Scan 重叠。优先使用与教学来源隔离的评测数据。报告完整分母、Fallback、技术失败、SR/SPL/nDTW 和置信区间；离线测试不代表真实模型或导航实验。
