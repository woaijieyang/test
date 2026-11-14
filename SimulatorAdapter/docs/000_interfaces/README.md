接口说明见本模块README；共享位姿合同位于 graphAdapter/interfaces/pose，读取合同位于 graphAdapter/map_memory/storage/READER_CONTRACT.md。总开关由 graphAdapter/interfaces/activation.py 统一解析。

## 位姿 RPC 的失败返回

回传无效测量只包含 episode_uid 与 pose_error=invalid_measurement，宿主保留本帧 RGB-D 并记录几何不可用。session_changed 与 profile_rejected 分别在宿主按会话错误和权限错误处理，中止受影响的采集尝试。未知协议字段不能用作位姿。命令派发和真实场景故障探针在 tests/probes/ 下的 pose_dispatch_probe.py、real_rotation_fault.py。


### VectorEnv 的位姿坐标系

模拟器进程读取机体 position 和 rotation 后，用 reset 时的机体变换建立本集初始 FLU 坐标系。成功的 RPC 回执包含 episode_uid 和 T_episode_base（4×4 刚体变换，列向量，平移以米计）。建立会话时另含 pose_session，矩阵为单位阵。绝对世界位置和原始四元数只在模拟器进程内用于计算。每次绑定、过期会话和测量错误使用原会话规则。宿主的 PoseReader 继续以帧号和采集时间读取原 PoseFrame；相机外参由观察模块提供。
