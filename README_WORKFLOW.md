# 工作流水

按实际时间追加正式Git交付事务：变更、验证、结果、限制及发布回执。阶段过程在docs/zx，数字在docs/results。历史流水如下，当前事务见最新条目。


## 2026-10-20 阶段快照发布事务

用户明确授权先push，再继续Landmark修复，并允许阶段采纳pRb候选。范围：AwareVLN源码布局、独立OracleAdapter、公共配置、补丁、文档与结果摘要；不包含运行环境/数据/权重/原始outputs/backup/凭据。目标`woaijieyang/FirstPaper-VLN:main`，提交`awareVLN-baseline-construct`，保留现有父提交历史、不强推。

科学状态：两套模型测评封存；R2R retracted限制保留；Landmark20911/33954，pRb98/660、31恢复/2退化，候选仅经人工授权阶段采纳，未全部验收。详细事实和成本见docs/PUBLICATION_SNAPSHOT.md。

验证：本次提交前审查实际暂存树、忽略正反例、文件大小/符号链接/凭据模式、许可和CPU回归；实际检查回执位于outputs/publication/intermediate-20261020。本文不预先宣称push成功；提交自身SHA、实际远端commit/tree核验与传输回执在提交生成后另存outputs/publication，并在交付回复提供。


## 本次实际发布检查（2026-10-20）

远端工作区Oracle CPU217项、根CPU32项全部通过；从暂存树导出的干净副本同样217+32项全部通过，无跳过。干净副本使用既有case1 runtime，不是新安装环境或新导航实验。实际暂存文件逐项审查：无数据/权重/环境/outputs/backup/本机配置、无符号链接、无大于10MiB文件；常见私钥/GitHub/API/AWS令牌和带凭据URL模式扫描无命中（模式检查不构成绝对无秘密保证）。.gitignore正反例通过，公开JSON配置/结果索引可提交；许可文件及来源记录保留。阶段报告5项关键证据路径及SHA256逐一匹配。

Git按既有.gitattributes规范化文本行尾为LF，历史工作区/源码归档保留原字节。发布树的blob/hash和运行时原始source SHA分别记录，不能把Git导出源码摘要冒充旧运行源码摘要。全部历史诊断源码保留用于证据追溯，活跃Oracle仍仅oracleAdapter/src/oracle。以上检查只支持本次阶段快照发布，不提升任何导航失败或科学验收状态。


## 2026-10-25 VLN-awareVLN endpoint9固定划分全量复测

用户明确授权：在/data/zy/vln/data/checkpoint-choice/VLN-awareVLN复制修复版，采用已发布endpoint9、沿14叶子固定ID完整测评；原VLN与原始全局数据不改。R2R 1839/1839、RxR-US 1223/1223执行完成，worker审计、独立指标复算和validation均PASS。新旧每数据集逐任务指标/终止/步数/模型调用差异为0；trace SHA不同项分别1839/1223，不声称字节轨迹相同。新R2R evaluator run complete，但旧R2R 5处严格离网/retracted边界仍单独保留。完整对比和成本见results-show/MODEL_TEST_RESULTS.md；阶段结论附run/profile/manifest/validation及限制哈希。

资源：4 GPU worker并发，设备仅4–7；每卡本任务额度24576MiB，采样峰值最高见outputs/checkpoint-choice-20261024-shared24-v1/final-review-receipt.json。CPU更新为<=72后部优先、nice10，最终稳定32个逻辑核；早期退出worker启动亲和性沿用worker-done回执，不粉饰。worker elapsed为并行批次墙钟时间，互相重叠；退出worker精确CPU时间未知，未估填。控制器source freeze和最终审计状态见outputs/checkpoint-choice-20261024-shared24-v1。

Results迁移和新表生成后，清理仅按本任务拥有清单归档；process-show及另有日期阶段文档因所有权不明保留不暂存。push前逐文件核对Git树、ignore、凭据模式、许可和文件大小。


## 2026-10-25 固定划分baseline全量复测

R2R1839/1839及RxR-US1223/1223完整推理结束；两run的动作语义审计、独立指标重算、validation全部PASS。新旧各数据集逐task_key配对，指标数值在1e-12绝对容差下差异均为0，终止原因/primitive动作数/model调用数也一致；轨迹原始SHA分别不同，不宣称逐字节相同。R2R旧记录5例严格离网导致retracted状态继续保留。模型指标、A/B/Remaining单块/累计/full、来源及协议限制见results-show/MODEL_TEST_RESULTS.md和checkpoint-choice-20261024.md。两个新记录登记为complete，身份及回执绑定在results-show/records.json和outputs内。Worker批次墙钟耗时可能并发重叠，CPU退出进程最终ticks未知，资源账本不估填。

用户要求的精确过程文件归档已生成manifest，原run/trace/log/失败证据保留；所有权未归属的process-show/及另阶段文档保留且不暂存。GitHub main已核验：commit `1f79a7cb6747d03b7b5b1f370e73dfab6c6e71fd`，tree `bc3d6a4d6af27361be7dea94b2094cc3381cdfae`，parent `c3b5010c8a5e4efdf1a7063bc0f2f95df6ff9376`；完整回执见阶段结论与忽略文件`outputs/publication/push-verified-20261025.json`。


工作区清理回执：本任务创建的本地37个与服务器2个终态辅助脚本已逐SHA归档，归档manifest列于results-show/intermediate-cleanup-20261025.json；原始运行/失败/轨迹/审计证据保留，未归属本任务的process-show及另阶段文档未修改。暂存树审核PASS；GitHub main现已验证包含commit `1f79a7cb6747d03b7b5b1f370e73dfab6c6e71fd` / tree `bc3d6a4d6af27361be7dea94b2094cc3381cdfae`。


## 2026-10-25 push前清理与审计最终状态

R2R/RxR新run全部执行和最终独立审计通过，records登记为complete；R2R旧retracted几何限制保留。逐task配对指标差值全为0，trace hash逐条不同且不声称byte-identical。results-show总表报告所有fixed leaf/cumulative/full的新旧差异。40个本地和2个远端本轮临时工具SHA校验归档；原始运行和失败证据保留。未归属的process-show和其他阶段文件不暂存。本次prepush tree审核与远端最终回执在commit生成后另附。


## 2026-10-25 固定划分复测交付审核

R2R/RxR各自完整run及最终semantic action audit、独立指标重算、validation均PASS，并写入results-show。新旧逐任务指标差异为0，R2R旧retracted几何限制保留。结果分区、成本、annotation/profile/source identities和trace SHA限制详见阶段conclusion。过程脚本已精确归档，原始失败及审核证据保留；用户所有权未确认文件未暂存。GitHub提交和远端main/tree核验回执将在push后追加。


## GitHub发布核验

`woaijieyang/FirstPaper-VLN:main`已收到commit `1f79a7cb6747d03b7b5b1f370e73dfab6c6e71fd`（tree `bc3d6a4d6af27361be7dea94b2094cc3381cdfae`，parent `c3b5010c8a5e4efdf1a7063bc0f2f95df6ff9376`，message `awareVLN-baseline-construct`）。GitHub API返回与本地commit一致；未强推，认证仅在本机relay使用。发布前的目录/秘密/许可/大文件审核PASS，具体数据见阶段结论。

## 2026-10-31 Case2 HAMLET-construct
从 case1 发布提交 d230f31 导入，case2 独立 runtime 与资产视图已完成部署和完整 episode 数据流验证。目标分支 HAMLET-baseline；首次提交仅封存已验证 baseline，随后继续 HAMLET 核心装配与正式测评。源 case1、case0 与共享资产未修改。详情见本次计划、结论及 results-show/deployment-tests.md。
