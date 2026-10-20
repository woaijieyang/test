# AwareVLN Case1 基线与 OracleAdapter 研究

**当前交付：2026-10-20 阶段研究快照。模型R2R/RxR测评已完成并封存；Landmark尚未全修复。** 用户授权先发布，后续继续Landmark修复。pRb候选已授权阶段采纳，保留2条已知退化，不将采纳等同全部验收通过。

先读[本次发布说明：结果、限制、成本和证据](docs/PUBLICATION_SNAPSHOT.md)，再读[总体conclusion](docs/zx/2026-10-14-2-conclusion-基线重建与全量测评.md)及[导航专项conclusion](docs/zx/2026-10-15-1-conclusion-导航连通性专项验收.md)。历史阶段与授权变化保留在原conclusion，不用历史“等待RxR”描述当前状态。

|部分|当前事实|
|---|---|
|AwareVLN R2R|1839/1839，SR65.633496%；后续5处原生离网，登记retracted、原成绩和限制均保留|
|AwareVLN RxR en-US|1223/1223，SR67.620605%；原协议指标/语义审计通过|
|Landmark全量研究|20911/33954严格通过，全分母/held114保留；非模型成绩|
|pRb660候选|98通过、562失败，恢复31/退化2；用户授权后续研究采纳，未全验收|

部署阅读顺序：[文档导航](docs/README.md) → [SETUP](docs/SETUP.md) → [架构](docs/ARCHITECTURE.md) → [数据](docs/DATA_INTEGRATION.md) → [测评](docs/EVALUATION.md) → [模型结果](docs/results/model_results.md)。研究入口：[OracleAdapter](oracleAdapter/README.md)。执行前核对当前plan、实际manifest和资源，原运行不可为查看状态重跑。

```text
src/              AwareVLN实际运行源码
configs/          公共部署配置与依赖/来源锁
scripts/          受保护启动、搭建、评测与审计入口
tests/            回归及历史诊断源码（保留原证据引用）
oracleAdapter/    独立研究模块；唯一活跃Oracle代码/配置在src/oracle
docs/             部署、数据、结果及同一阶段plan/conclusion
patches/          上游兼容补丁
```

runtime、data、models、outputs、upstream、backup和缓存留在机器上并被Git忽略。克隆仓库不包含受许可约束资产、权重或原始运行证据；按文档接入只读共享资产后使用`scripts/with_runtime.sh`。Oracle基本自检入口：

```bash
scripts/with_runtime.sh runtime/awarevln/bin/python -B oracleAdapter/run.py describe
scripts/with_runtime.sh runtime/awarevln/bin/python -B oracleAdapter/run.py self-test
```

上述自检不代表真实导航通过。后续新派生模型评测须先补齐信息流门槛，本次不重测、不训练。[当前计划](docs/zx/2026-10-14-1-plan-基线重建与全量测评.md)与[Git工作流水](README_WORKFLOW.md)记录范围和发布事务。
