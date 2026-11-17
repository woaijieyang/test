# Case2 概览

目的：在独立部署的 AwareVLN baseline 上集成经原始 SHA 定位的 HAMLET-Z V2 / CBEM aw4 seed10，并完成数据流测试与重新测评。

组织：src 为活动实现，configs/scripts/tests 为配置、入口和回归；runtime/data/models/outputs 为本 case 环境、只读资产视图及原始证据。采用用户指定的 case1 发布快照布局，不恢复旧 stage0/stageN 目录。

当前阶段与已验证事实见 README.md 和 docs/zx/2026-10-31-2-conclusion-HAMLET基线迁移与复测.md。EXPERIMENTS.md/RESULTS.md 由 case_tracker 维护；正式模型成绩与诊断分开。
