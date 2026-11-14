# SimulatorAdapter

只替代位姿来源，不是导航器或场景数据库。

- `pose.py`：仅读agent position/rotation，转换为episode初始FLU坐标，按帧保存准确位姿。
- `host_bridge.py`：宿主VectorEnv RPC，白名单只返回episode身份、T_episode_base。
- `tests/`：位姿、隔离、生命周期、统一接口和异步接入验证；新增模拟器验证代码只在本模块。
- `tools/000_contract_checks/`：CPU合同检查。
- `tools/001_environment_validation/`：真实环境验证入口与证据索引。
- `docs/000_interfaces/`、`docs/001_validation/`：范围和验证说明。

共享协议从 `graphAdapter.interfaces.pose` 导入；该包仅含纯合同，不启动建图或定位。模块不得获取目标、语义、对象身份、楼层真值、navmesh、路径距离或评测指标；不得执行导航动作。RGB-D仍来自宿主正常观察。源状态只在采集时读取，后台建图只能消费冻结DTO。


### VectorEnv 的位姿坐标系

模拟器进程读取机体 position 和 rotation 后，用 reset 时的机体变换建立本集初始 FLU 坐标系。成功的 RPC 回执包含 episode_uid 和 T_episode_base（4×4 刚体变换，列向量，平移以米计）。建立会话时另含 pose_session，矩阵为单位阵。绝对世界位置和原始四元数只在模拟器进程内用于计算。每次绑定、过期会话和测量错误使用原会话规则。宿主的 PoseReader 继续以帧号和采集时间读取原 PoseFrame；相机外参由观察模块提供。
