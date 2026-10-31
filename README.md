# Case2：AwareVLN 基线与 HAMLET 复现

当前状态：独立 baseline 部署验证已通过，包括 13 条完整 episode 数据流测试。HAMLET 集成与正式测评进行中；尚未发布本次结果。

基线源码来自 case1 已发布提交 `d230f31dbf38c8097594108665f6d0805530b44a`。仅调整 case2 部署路径并重建独立环境；未纳入源目录未提交的 subtaskAdapter/goalAdapter 工作。历史文档与结果随快照保留，其中标注 case1 的成绩属于源实验，不是本 case 的新结果。

| 目录 | 用途 |
|---|---|
| src / configs / scripts / tests | 运行源码、配置与依赖锁、保护入口、回归 |
| runtime / upstream / .cache | 独立环境、第三方源码、构建缓存；Git 忽略 |
| data / models | 只读共享资产链接与 case2 派生视图；Git 忽略 |
| outputs | 本次原始日志、输入/输出轨迹、审计回执；Git 忽略 |
| docs / results-show | 部署说明、阶段计划与结论、来源明确的结果登记 |
| oracleAdapter | 发布快照自带模块，保留来源；不计为 HAMLET 新实验 |

本次入口：[迁移计划](docs/zx/2026-10-31-1-plan-HAMLET基线迁移与复测.md)、[当前结论](docs/zx/2026-10-31-2-conclusion-HAMLET基线迁移与复测.md)。已有部署和数据流说明见 [SETUP](docs/SETUP.md) 与 [ARCHITECTURE](docs/ARCHITECTURE.md)，其中历史绝对路径须按 case2 本地环境核验。

所有模型与模拟器执行使用 `scripts/with_runtime.sh`。Python 包中的 `case1_runtime` 和保护变量 `CASE1_PROTECTION` 是继承的内部命名，实际路径由当前工作根决定；必须核验导入位置在 case2。

目标历史版本：HAMLET-Z V2 / CBEM aw4 seed10，run `r2r_full1839_candidate_cbem_prefilter52_aw4_seed10_20260801_v1`。已定位 288 个 SHA 一致的历史源码文件与原 adapter/router；恢复和新测评状态以本次结论为准。
