# GraphAdapter 002 当前计划

**当前状态：已交接，等待人工复查；没有排队或运行中的新增评测。** 当前任务是判断图记忆能否向原生八图提供对决策有帮助的新增证据。基于已有结果，先复核检索线索与证据内容，再决定是否恢复小批量闭环。[阶段结论](conclusion.md)

| 顺序 | 状态 | 工作与验收条件 |
|---|---|---|
| 1. 检查来源和接口 | 可立即人工复查 | 对照 1561 与 282 的原生八图（服务器 `docs/stages/graphAdapter/002/inspection/validation/stop-controls/two-stops-native.jpg`）、A36 检测原图（服务器 `docs/stages/graphAdapter/002/inspection/validation/stop-controls/local-282-s36.png`）、A33 检测原图（服务器 `docs/stages/graphAdapter/002/inspection/validation/reason-roles/local-282-s33.png`） 及 粗排与原始 REASON（服务器 `docs/stages/graphAdapter/002/inspection/validation/stop-controls/two-stops-coarse.json`）。按 episode、decision、源步、snapshot、图像槽和检测成员核对。记录材料支持的具体事实，包括未知的位置或关系。|
| 2. 补齐简单决策对照 | A33 生成尚缺 | 恢复时先查看 未完成清单（服务器 `docs/stages/graphAdapter/002/inspection/validation/reason-roles/instruction-generation-status.json`）。在可用的 GPU 4–7 上复用冻结输入，完成既定的“只用指令检索”条件。原 prompt 中保留原生 REASON，比较相同状态与预算下的真实图、替代图、无记忆输出。已有完全相同的条件从封存结果复用。 |
| 3. 确定候选是否值得上线测试 | 待第 2 步 | 用 1561 检查正确 STOP 能否保持，用 282 检查正确来源与错误绑定能否被区分；计入相邻决策，排查提前 STOP 或一致的步长偏移。若异图、对调文字也能复现效果，保留反例，暂停在线晋级。 |
| 4. 双域小批量闭环 | 尚未启动 | 仅在前述内容对照成立后，预先登记 R2R、RxR-US 成员与预算。复用可配对的真正 hook-off control；对照输入、实际动作、STOP、计时及导航指标，保留失败和未启动成员。按 正式效果门槛（服务器 `docs/stages/graphAdapter/002/release_gate.md`） 判断能否继续，随后再考虑扩大样本。 |

**贯穿各步的接口约束。** 每次实际模型生成前固定当时可读的快照，保留原指令、八个原生 RGB 槽、原 parser、executor 和 STOP。SimulatorAdapter 只供位姿；记忆检索集中在 GraphAdapter。所有评估使用因果前缀，终图作事后检查。004 主动读取、005 细粒度描述与 003 后续工作均未列入当前执行项。

**本轮的执行边界。** 这份计划供人工检查和后续恢复使用。本次整理只调整资料摆放和索引，未启动新的模型生成、重新建图或正式测评。
