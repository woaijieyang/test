# 002 图记忆注入

本目录是 GraphAdapter 注入侧唯一的实现位置。主模型输入由原来的 8 张 RGB、原指令和最近 reasoning 构成，诊断 profile 可附加有来源的历史文字和至多一张独立历史图。补充材料来自当前决策钉住的已发布快照，当前观察的身份另行校验。

## 调用一条完整链

1. 宿主每到原生推理边界，调用 `HostInjection.begin(...)`。它取得当前可见的快照、截止步、episode 和决策编号，通过同一建图消费者提交只读请求。
2. 私有建图进程调用 `WorkerRetrieval.read(...)`。它校验请求、已提交帧和位姿来源，管理编码器及每集特征缓存，由读取会话选择历史证据。回执与 request_id、episode_instance 和 snapshot_id 一一对应。
3. 宿主得到原采样槽和历史材料，通过 `HostInjection.compile(...)` 生成原问题的补充块。每个原推理边界可更新路径、估计距离、对象或历史图；同帧 REASON 保留各自的决策时钟。缺证据或超预算时恢复原采样和原问题。
4. `HostInjection.preprocess(...)` 使用宿主原 processor。调用者将真实的 prompt、token IDs、模型图像张量交给 `HostInjection.generation(...)`，在同一个上下文管理器内调用原 generate。审计核查原图、token、视觉预算和返回回执。原 parser 和动作队列继续接收原模型输出。
5. `WorkerRetrieval.end_episode()` 释放每集特征，`close()` 结束 worker 级编码器生命周期。不可变地图、封存记录和实验证据由 storage 与 evaluation 管理。

**入口示例**（模块导入按进程职责延迟加载）

```python
# 宿主 trainer
from graphAdapter.map_memory.retrieval import HostInjection, retrieval_settings

# 已隔离的私有建图进程
from graphAdapter.map_memory.retrieval import WorkerRetrieval

# 通信层
from graphAdapter.map_memory.retrieval import FrozenMemoryRead
```

## 修改时从哪里开始

| 问题 | 归属 |
|---|---|
| 谁可读、请求与回复的约束、原生槽编号 | `protocol.py`；进程间只读接口。原 `graphAdapter.interfaces` 下两个绑定仅转发公开名称 |
| 查询、候选、对象来源、结构化数据类型 | `contracts.py`、`query_adapter.py`、`candidates.py`。EvoMemNav 的候选与图文标签适配也在 candidates |
| 已存一跳关系与图像预算选择 | `bundles.py`、`selector.py` |
| 哪些历史事实可读，哪一个关系有来源 | `evidence.py`。基本事实与组合关系从同一处核验 |
| 何时读、跨步更新什么、何时撤销 | `dynamic_context.py`。事件门控、时间窗口、实际轨迹关系按同一时序处理 |
| 原图及附图材料化、对象区域、文本编译、预算 | `host_input_compiler.py`。包括原图身份、附图角色、地标卡与视觉槽 DTO |
| 最终张量、token 和原图核对；附图独立编码 | `input_audit.py` |
| 完整事务/生命周期 | `host_decision.py` 的 HostInjection、`session.py` 的 WorkerRetrieval。两者统一由包入口导出 |

规格中指定的六个文件（query_adapter、candidates、bundles、selector、host_input_compiler、input_audit）均保留。模式与参数归属相邻的 `map_memory/profiles/`。同一实现由多个 profile 复用。组件测试在本目录的 `tests/`，真实运行对照工具在 `graphAdapter/tools/002_retrieval_validation/`，独立报告归 `graphAdapter/evaluation/`。

**修改边界。** SimulatorAdapter 负责位姿来源，通用存储读取唯一地图；native PoseAdapter 和模拟器 API 均不属于本目录。宿主适配文件承担 AwareVLN 入口接线，worker 文件承担 IPC 服务接线。实际框架调用位置可从 runtime/host_integration/vlnce_baselines/awarevln_trainer.py 的 HostInjection.begin 和 map_memory/worker.py 的 read_memory 分支进入。

服务器候选根目录为 `/data/zy/vln/case2/outputs/graph_memory/graph002-organized-candidate-01`。当前导航效果验收仍在 002 小样本开发阶段。


## 历史地标的相对坐标

可选诊断 profile `001_dynamic_object_center.json` 在已核验历史附图上添加 `object_center_estimate_current_camera`。其 `right_m` 和 `forward_m` 分别是融合物体框中心在当前光学相机 X 和 Z 轴的投影。相邻字段 `distance_to_historical_camera_m_estimate` 表示两次拍摄位置之间的距离。坐标需要同一已发布地图、同一 episode、唯一活动实体、同类别检测来源及有效的同版本相机变换。超预算时先撤下物体坐标。来源与独立重算报告分别见 DynamicContextCompiled.source.object_position 和配对报告的 verified_object_centers。

构建拓扑菜单时，`anchor_detection_labels` 把每一原始检测引用绑定至该帧归档的类别；每个锚点只需解码一次 class_id 数组。菜单的 `objects` 在 `label_scope=anchor_detections` 时表示这些源检测类别，`topology.objects[].label` 则保留实体的跨帧聚合类别。旧式内存摘要缺少源类别映射时标为 `aggregate_only`。以上类别均来自感知模型。


仅需生成可读历史选项时，通过 TopologyMenu.from_reader(reader, ...) 读取固定快照。地图覆盖率和 BEV 继续使用 read_semantic_topology。获得实际回复后，由同一个菜单的 materialize(reply, reader, ...) 校验 episode、快照、当前采集序号和决策编号，返回原始 RGB、来源引用及原图网格上的检测框；NONE 返回空。应使用宿主的原 processor 处理这张 RGB。类别与框复用同一个 episode 字节额度，选图前不解压框，读取完整特征时复用已读类别。重复读取不同修订时应传入同一 episode 的 EpisodeFeatureCache，结束时由其持有方 close。


## Reusing text-to-camera scores across decisions

MemoryRetrievalSession owns separate CameraTextScores for the full instruction and native reasoning. Scores are reused only for the same immutable encoding, text/model/tokenizer identity and verified camera feature blob. Availability, current-view similarity, coverage, channel ranks, graph relations and the final image slots are evaluated on the current pinned read. Each text channel retains at most 512 scalar entries, scaled down for small feature budgets. A zero feature-cache budget disables scalar retention. Closing the session releases entries and text-matrix references. MemoryCandidates includes cumulative hit and computation counts under semantic_score_cache when the Q/V/C path runs.


## Native plan photo admission

The opt-in profile `001_native_plan_photo.json` uses `context_admission=native_plan_photo` with `landmark_query=current_plan`. The host binds the last completed native REASON output to this episode and decision. Until its next plan positively names a vocabulary item in the instruction, the host polls publication without issuing a broker read. A qualified read keeps the native image slots and can append one source photograph with its detector and spatial evidence. No primitive path window is requested in this mode. If the source is already represented, missing, ambiguous under the selected ambiguity policy, or exceeds the material budget, the host uses its original question and slots. Admission alone does not establish that the photograph corresponds to the intended physical target. The profile retains the original parser, action queue and STOP.
