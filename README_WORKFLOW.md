# 工作流水

按实际时间追加正式Git交付事务：变更、验证、结果、限制及发布回执。阶段过程在docs/zx，数字在docs/results。历史流水如下，当前事务见最新条目。


## 2026-10-20 阶段快照发布事务

用户明确授权先push，再继续Landmark修复，并允许阶段采纳pRb候选。范围：AwareVLN源码布局、独立OracleAdapter、公共配置、补丁、文档与结果摘要；不包含运行环境/数据/权重/原始outputs/backup/凭据。目标`woaijieyang/FirstPaper-VLN:main`，提交`awareVLN-baseline-construct`，保留现有父提交历史、不强推。

科学状态：两套模型测评封存；R2R retracted限制保留；Landmark20911/33954，pRb98/660、31恢复/2退化，候选仅经人工授权阶段采纳，未全部验收。详细事实和成本见docs/PUBLICATION_SNAPSHOT.md。

验证：本次提交前审查实际暂存树、忽略正反例、文件大小/符号链接/凭据模式、许可和CPU回归；实际检查回执位于outputs/publication/intermediate-20261020。本文不预先宣称push成功；提交自身SHA、实际远端commit/tree核验与传输回执在提交生成后另存outputs/publication，并在交付回复提供。


## 本次实际发布检查（2026-10-20）

远端工作区Oracle CPU217项、根CPU32项全部通过；从暂存树导出的干净副本同样217+32项全部通过，无跳过。干净副本使用既有case1 runtime，不是新安装环境或新导航实验。实际暂存文件逐项审查：无数据/权重/环境/outputs/backup/本机配置、无符号链接、无大于10MiB文件；常见私钥/GitHub/API/AWS令牌和带凭据URL模式扫描无命中（模式检查不构成绝对无秘密保证）。.gitignore正反例通过，公开JSON配置/结果索引可提交；许可文件及来源记录保留。阶段报告5项关键证据路径及SHA256逐一匹配。

Git按既有.gitattributes规范化文本行尾为LF，历史工作区/源码归档保留原字节。发布树的blob/hash和运行时原始source SHA分别记录，不能把Git导出源码摘要冒充旧运行源码摘要。全部历史诊断源码保留用于证据追溯，活跃Oracle仍仅oracleAdapter/src/oracle。以上检查只支持本次阶段快照发布，不提升任何导航失败或科学验收状态。
