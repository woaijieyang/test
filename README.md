# AwareVLN 位姿接口与图记忆候选

**001 建图已按 15 集范围验收；002 已验证图文能进入模型，导航收益尚未通过验收。** 本仓库存放两个模块的交接源码。服务器正式入口仍使用 001，模型权重、环境资产、原生 PoseAdapter 依赖及封存运行日志位于原工程。详细结果见[阶段结论](docs/conclusion.md)，待验事项见[当前计划](docs/plan.md)。

## 两个模块各自负责什么

| 模块 | 输入 | 输出与职责 |
|---|---|---|
| [SimulatorAdapter](SimulatorAdapter/pose.py) | Habitat 当前机体的位置和旋转，以及会话、帧号、时间戳 | 将机体姿态转换到本集初始 FLU 坐标系，按帧提供位姿。世界原点留在模拟器侧。目标位置、参考路径、房间真值、navmesh 和未来观测均不在输出合同内。 |
| [graphAdapter](graphAdapter/README.md) | 宿主实际采集的 RGB-D、静态标定、执行反馈，以及统一接口返回的位姿 | 对齐同帧数据，融合几何、对象和视图，发布可重载快照。在 002 中按决策检索证据，将拓扑说明、地图和历史图文编译成模型附加输入。 |

## 接口怎样接到导航循环

1. **每集 reset。** 宿主通过 `make_vector_factory` 绑定对应的 VectorEnv 环境。提供方建立新会话，即使再次运行同一 episode，也用新的 `episode_instance` 区分。模拟器进程通过位姿 RPC 返回本集相对机体位姿。[宿主与模拟器桥接](SimulatorAdapter/host_bridge.py)
2. **每个实际观测端点。** 宿主的 `PoseBridge` 通过 `PoseReader.capture` 绑定会话、帧号和时间戳。模拟器分支只向提供方传递帧标识与时钟。返回的 `PoseFrame` 带来源、有效性、地图版本和机体变换，GraphAdapter 再用静态外参得到相机位姿，将其与同帧 RGB-D 绑定。无有效位姿时不填造坐标。[统一 DTO 与读取接口](graphAdapter/interfaces/pose/contracts.py) · [观测桥](graphAdapter/observation_pose/pose_bridge.py)
3. **建图与发布。** 几何和对象分支使用同一帧的观测身份。建图服务提交更新后发布快照；检索固定读取当时可见的快照和观测截止点。001 只做影子建图与保存。[建图服务](graphAdapter/map_memory/service.py)
4. **每次实际模型生成前。** 002 的宿主调用 `HostInjection.begin`，私有进程通过 `WorkerRetrieval.read` 选择证据，宿主再执行 `compile`、`preprocess`，在 `generation` 的审计范围内调用原模型。上次 REASON 可用作线索。附加材料走独立通道，原指令和八个 RGB 槽保留；原 parser、动作队列、执行器和 STOP 继续处理生成结果。执行队列里的 primitive 不额外触发模型调用。关闭 hook 时走宿主原生路径。[宿主决策接口](graphAdapter/map_memory/retrieval/host_decision.py) · [读取会话](graphAdapter/map_memory/retrieval/session.py)

## 验证到了哪一步

| 范围 | 已有证据 | 尚待确认 |
|---|---|---|
| 001 建图与存储 | R2R 7 集、RxR-US 8 集；检查最终图保留、冷加载及逐集计算缓存回收。 | 结论适用于该批 15 集。 |
| 位姿边界 | 候选的提供方测试 77 项、宿主观测与位姿测试 74 项通过；6 集 469 个封存端点逐帧对应。 | 469 个端点是原档案兼容核查。 |
| 002 输入与导航 | 固定状态核对了真实 prompt、原生八图及额外视觉材料进入语言模型的路径。1953 的真实闭环两侧都成功，但候选 SPL 从原生的 1.000 降至 0.291。 | 1561 的正确 STOP 会被整图干扰；282 的 A33 原图及排名已核实，新增生成因共享 GPU 显存不足未完成。双域导航效果门槛仍未过。 |

上述数字来自服务器相应版本的运行与归档。建议先沿接口代码检查数据边界，再按 [plan.md](docs/plan.md) 的顺序检查 1561 的 STOP 和 282 的来源绑定。服务器审阅目录为 `/data/zy/vln/case2/docs/stages/graphAdapter/002/`。
