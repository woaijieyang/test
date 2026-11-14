# GraphAdapter

负责普通RGB-D观察接入、同帧位姿DTO校验、几何/对象/视图图、内容寻址存储、只读查询和评测。不直接调用模拟器真值API。

- `interfaces/activation.py`：唯一总开关。off优先于残留profile/broker，默认off。
- `interfaces/pose/`：两种提供方共享的只读DTO、连续坐标系合同和当前Simulator执行政策。
- `observation_pose/`：RGB-D对齐、采集时序、宿主桥和有界异步发布。
- `map_memory/geometry/`、`perception/`、`storage/`：唯一地图及原图证据，不按阶段复制地图。
- `evaluation/`：Case1 A成员绑定、原评测器调用、证据核验。显式队列使用CLI `eval --cohort-plan`。
- `tests/`：跨功能合同；各功能原有tests仍随所属功能。
- `runtime/`：受保护的执行器。`host_integration/`仅保存宿主薄接线，运行时映射到原宿主路径。
- `tools/000_contract_checks/`：维护中的CPU检验入口。
- `docs/000_interfaces/`、`docs/001_validation/`：接口和本阶段证据说明。

地图、日志、快照和报告写入项目 `outputs/graph_memory`。当前实际执行仅允许SimulatorAdapter；PoseAdapter原模块独立保留，未经用户明确安排不启用。
