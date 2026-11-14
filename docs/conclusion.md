# GraphAdapter 002 阶段结论

**截至 2026-11-14，001 已在修订的 15 条样本范围内通过验收。002 已打通图记忆到 AwareVLN 的图文输入，仍处于候选阶段，导航效果尚未达到发布条件。当前交接给人工检查。** [当前计划](plan.md) · 001 验收结论（服务器 `docs/stages/graphAdapter/001/conclusion.md`） · 002 规格逐项验收（服务器 `docs/stages/graphAdapter/002/release_gate.md`）

## 哪些已经完成

| 内容 | 已核实的结果 | 查看证据 |
|---|---|---|
| 建图与持久化 | 001 使用 R2R 7 集、RxR-US 8 集。按实际观测建图、保留最终地图、检查冷加载并回收可重建缓存。 | 001 结论（服务器 `docs/stages/graphAdapter/001/conclusion.md`） |
| 位姿隔离 | 最新 002 候选的宿主向模拟器仅请求绑定会话的帧位姿。77 项提供方测试、74 项宿主测试通过。6 集 469 个封存端点与观测逐帧对应。 | 接口、失败记录和真实场景复查（服务器 `docs/stages/graphAdapter/002/inspection/reports/pose_input_boundary_review.md`） |
| 图文接入 | 单成员真实闭环已有按调用关联的材料、模型生成、解析和执行日志。后续固定状态验证进一步核对了原生八图、额外图像投影、文字和语言模型首轮输入。 | 发布验收与在线结果（服务器 `docs/stages/graphAdapter/002/release_gate.md`） · 固定状态图文对照（服务器 `docs/stages/graphAdapter/002/inspection/reports/stop_content_controls.md`） |
| 检索来源 | 15 集 804 次请求中，626 次带可追溯的历史 REASON，来自 31 次独立生成。330 次引用中至少有一个类别只出现在该段 REASON 的观察句；该数值表示线索出现频次。 | 来源分析与复查方法（服务器 `docs/stages/graphAdapter/002/inspection/README.md`） |

## 为什么 002 仍待验收

- **R2R 1561** 的当前原图可见木地板，原生正确 STOP。加真实地图后，三个提示位置都输出前进 25 cm。增加原生槽的检测文字可恢复 STOP，但把两槽类别对调也恢复 STOP，尚不能归因于正确图文绑定。原生八图（服务器 `docs/stages/graphAdapter/002/inspection/validation/stop-controls/two-stops-native.jpg`） · 固定状态实验（服务器 `docs/stages/graphAdapter/002/inspection/reports/stop_content_controls.md`）
- **RxR-US 282** 的目标是对面空房。加入上一轮 REASON 后，粗排第一名是看到床和椅子的第 36 步 A36；只用原指令时，第一名是看到暖气片的第 33 步 A33。A33 的原图、检测和排名已核实。新增生成因共享 GPU 显存不足未完成，没有 A33 的新动作或闭环得分。A33 原图（服务器 `docs/stages/graphAdapter/002/inspection/validation/reason-roles/local-282-s33.png`） · 未完成记录（服务器 `docs/stages/graphAdapter/002/inspection/validation/reason-roles/instruction-generation-status.json`）
- **RxR-US 1953** 的已封存在线对照两侧均成功，但候选用了 303 个 primitive，原生用了 7 个，SPL 从 1.000 降至 0.291。更新过的位姿候选、渲染修正和固定状态生成各有独立版本；上述分数属于该次在线运行。闭环复核（服务器 `docs/stages/graphAdapter/002/release_gate.md`）

## 代码、数据与运行位置

| 位置 | 用途 |
|---|---|
| [检索与注入源码](../graphAdapter/map_memory/retrieval/README.md) | 固定快照、构造本次查询、召回证据、编译图文及宿主审计。 |
| [统一位姿接口](../graphAdapter/interfaces/pose/README.md) · [SimulatorAdapter](../SimulatorAdapter/README.md) | 模拟器只供约定位姿；RGB-D、标定和执行反馈使用宿主观测链路。 |
| 复查目录（服务器 `docs/stages/graphAdapter/002/inspection/README.md`） · 离线核验脚本（服务器 `docs/stages/graphAdapter/002/inspection/verify_review.py`） | 已展开的源码、测试、原图和生成记录。在 inspection 目录运行 `python verify_review.py`。 |
| 既有技术文档（服务器 `docs/stages/graphAdapter/002/reference/memory_retriever_design.md`） · 历次阶段记录（服务器 `docs/stages/graphAdapter/002/reference/conclusion_history.md`） | 追溯历史设计和单项实验；当期发布判定以本页和当前计划为准。 |

服务器根目录为 `/data/zy/vln/case2`。正式入口 `scripts/with_graph_runtime.sh` 指向 `outputs/graph_memory/graph001-pose-boundary-20261114`。最新可审阅候选位于 `outputs/graph_memory/graph002-pose-input-boundary-01`。本目录的 inspection 是审阅副本；服务器 outputs 中的原始运行记录、地图、权重和默认启动配置均独立保存。
