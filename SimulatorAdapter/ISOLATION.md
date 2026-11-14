# 真值读取隔离规则

本任务新增的模拟器真值读取实现只允许位于 src/SimulatorAdapter/。运行时只读 agent state 的 position 和 rotation；不得查询目标、语义、对象、导航网格、路径、距离、占据图或评测指标。模块不执行导航动作。

直接访问真实模拟器的探针在 tests/probes/；全部本次新增模拟器相关验证在 tests/。测试驱动可以设置已知位姿以验证坐标转换，但此能力不得进入 pose.py 或宿主工作流。

graphAdapter.interfaces.pose 只定义契约与数据校验。GraphAdapter 只消费 DTO、执行观察和建图，不导入模拟器实现、不访问模拟器 API。宿主将受限位姿提供方注入接口；未完成的私有 worker 和生命周期接线仍拒绝启用。

目录外兼容入口只负责转入此目录的实现，不含模拟器调用。已有评测器不在本次改动范围。静态隔离测试与运行时拒绝测试共同验证边界，不能仅凭静态扫描宣称不存在所有泄露风险。


### VectorEnv 的位姿坐标系

模拟器进程读取机体 position 和 rotation 后，用 reset 时的机体变换建立本集初始 FLU 坐标系。成功的 RPC 回执包含 episode_uid 和 T_episode_base（4×4 刚体变换，列向量，平移以米计）。建立会话时另含 pose_session，矩阵为单位阵。绝对世界位置和原始四元数只在模拟器进程内用于计算。每次绑定、过期会话和测量错误使用原会话规则。宿主的 PoseReader 继续以帧号和采集时间读取原 PoseFrame；相机外参由观察模块提供。
