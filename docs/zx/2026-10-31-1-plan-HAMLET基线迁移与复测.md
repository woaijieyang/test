# HAMLET 基线迁移与复测计划

## 事实与边界
用户于 2026-10-31 明确选择 case1 已发布 baseline 快照 d230f31dbf38c8097594108665f6d0805530b44a。写根仅 /data/zy/vln/case2；源 case1、历史 case0、共享数据与权重只读。采用 src/configs/scripts/tests/docs/runtime/data/models/outputs 组织规则。保留随快照发布的 Oracle 模块及历史文档，但不将其历史验收当作 case2 新结果；排除未提交 subtaskAdapter/goalAdapter。

## 目标与验收
1. 源码导入、SHA 清单、路径本地化；独立 Git。
2. 按 conda/pip/native source 锁重建 case2 runtime；共享数据和官方模型只读链接；真实导入位置、pip check、内核写保护检查。
3. CPU 回归、真实渲染、网格重建与数据一致性、模型输入图像/张量/输出/动作/反馈/终止全链路，保留失败证据。
4. 正式 baseline 测评与独立复算，结果表沿用统一组织。诊断与正式结果区分，普通导航失败不重跑。
5. 全树检查与 GitHub HAMLET-baseline 发布；commit HAMLET-construct；核对远端 SHA/tree。查询时该分支不存在，故从 baseline 历史创建，不修改其他分支。
6. 根据截图 run 的 288 文件 SHA 及权重身份迁入最小必要 HAMLET 核心代码；核查重复实现和接口，完成测试和重新测评。

## 源码溯源
截图 run：r2r_full1839_candidate_cbem_prefilter52_aw4_seed10_20260801_v1。当前 V2 有 287/288 文件一致；原 trainer 在 eval_official_fallback_v1/awarevln_trainer.py.pre_official_fallback 找到，全部 288 文件可按历史 SHA 重建。D3-v3 memory adapter 与 abstention4_seed10 router 配置/权重匹配原 manifest。历史成绩复算不当作 case2 新推理。完整来源清单暂存 .planning/2026-10-31-hamlet-construct/。

## 资源与停止条件
启动前刷新 GPU 空闲状态和进程身份；不停止外部作业。CPU/构建使用原保护入口和原线程上限。路径逃逸、资产漂移、活动写入冲突、非有限正式指标、源代码变化时停止受影响步骤。保留失败与中断，不降低保护、预算或验收。

## 用户补充与适配验收
用户进一步明确：必须在我们的 baseline 上装配 HAMLET，重点核对之前逻辑与迁移后的数据流。不得以单独复制历史仓库代替集成。必须记录观测/历史帧、真实模型输入、记忆写入、CBEM 筛选与路由、选中记忆被生成消费、解析/实际动作、新观测反馈、episode 清理与独立指标。静态相同和 import PASS 均不是动态使用证据；迁移前后适配项逐项解释并回归。
