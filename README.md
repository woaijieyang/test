# Case2：AwareVLN上的历史HAMLET-Z V2 + CBEM

R2R1839条、RxR-US1223条全量推理及独立审计已完成。R2R SR65.144100%（baseline65.633496%）；RxR-US SR67.457073%（baseline67.620605%）。保留全部普通导航失败与负向差异，未因结果重新调参或择优重跑。

本仓库复现截图指定的历史HAMLET-Z V2/CBEM aw4 seed10核心，并接到独立部署的AwareVLN baseline；这是受HAMLET启发的导航改造，**不是原论文HAMLET的等价实现**。方法区别、训练来源、初始版本定位和局限在结论中说明。

- [Remaining/Full最终对照与分析](result-show/Remaining-Full-final-analysis.md)
- [全部A/B/Remaining/Full机器生成总表](result-show/model_results.md)
- [搭建、模型、训练来源与最终conclusion](docs/stages/2026-10-31-HAMLET装配与部署-conclusion.md)
- [记忆链路与全1839轨迹分析](result-show/HAMLET记忆链路与收益分析-20261101.md)
- [原文对照及训练数据扩充](result-show/HAMLET原文对照与训练数据扩充分析-20261101.md)

## 组织与执行

src为活动源码，configs保存冻结配置与来源，scripts为受保护入口及审计，tests为回归，tools包含分阶段调度和报告。runtime/data/models/outputs/upstream/cache均仅在服务器保存并由Git忽略。数据/权重/原始图像/动作日志不随代码发布。

实际运行只使用GPU4–7、CPU24–95；A→B→Remaining。源代码、模型、标注、网格和实际配置均绑定。必须使用scripts/with_runtime.sh启动模型和模拟器。历史内部名称case1_runtime/CASE1_PROTECTION保留，实际路径来自case2。

服务器的data/landmark保存20847条通过严格筛选的索引；data/baseline-rollouts保存R2R/RxR/Landmark历史baseline轨迹清单。它们没有启动新训练，也不能把验证集或Oracle轨迹伪装成训练baseline。

旧results-show目录保留来源明确的case1历史结果；本次正式对照入口为单数result-show。源码来源为baseline d230f31及经288文件历史哈希定位的候选核心；初始部署提交107317c的消息为HAMLET-construct。

## HAMLET-v2 分阶段训练增量

新的短时记忆训练使用独立版本的 Moment → Reader → CBEM checkpoint，不覆盖上面的历史实验结果或权重。入口为 `scripts/hamlet/run.sh`，在线评估通过显式 `--method hamlet-trained` 启用；baseline 与旧 `hamlet` 默认路径保留。

详细的真实文件 tree、Mermaid workflow、S00–S11 操作和 GPU/数据验收边界见 [HAMLET-v2 实施与训练执行手册](docs/hamlet/HAMLET-v2_实施与训练执行手册.md)。`bash scripts/hamlet/test_cpu.sh` 执行旧接口及新训练的 CPU 回归；CPU 通过不代表完成真实 8B、A6000 或导航验证。缓存 read-set、rollout split 证据及 Moment dtype 现有独立审计回归（见手册第 6 节），未经过真实 8B 联调不可视作上线验收。训练仅使用 R2R train 与 RxR train en-US，B1/B2/B3 只作累计选模，历史 val-unseen rollout 不得回流训练。
