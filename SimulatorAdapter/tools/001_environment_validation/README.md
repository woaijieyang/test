# 真实环境验证

真实运行使用 graphAdapter 的统一 `eval --cohort-plan` 入口，通过宿主注入本模块的位姿提供方。不得在图消费者中新增模拟器查询。

已完成证据：原工作区的 simulator-quality15-reuse-v3 与 simulator-async2-v4。旧版一次性探针保留于原工作区 src/SimulatorAdapter/tests/probes 及冻结release，不作为当前执行入口。
