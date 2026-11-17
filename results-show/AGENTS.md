# 正式结果规范

records.json是验收索引，model_results.md和record报告由render_results.py生成，禁止手改数字。原始结果在outputs，阶段conclusion链接本目录。
record_id唯一，绑定run/dataset/split/language/清单/模型/源码/配置/网格身份和验收回执。register必须拒绝缺失/重复、运行错误、非有限、复算不一致、语义链路未通过及输入漂移。
smoke/mock/诊断/部分/失败不进正式表；正常导航失败保留，不择优重试。
R2R与RxR-US分开，SR/SPL/nDTW/OSR百分比、NE米；有效/非有限、导航失败、基础设施异常分列。跨协议不直接算收益。
新记录追加；更正保留旧记录、原因及superseded/retracted状态。全局results-show只参考，不授权写。原始大资产、秘密禁止进入docs。

2026-10-24用户指定：本目录是case1唯一正式模型结果入口，历史原始记录按字节迁入；新结果仍须逐任务复算和审计。总表MODEL_TEST_RESULTS.md展示各固定块/累积/全量，model_results.md保留原登记表的自动生成兼容入口。不同run/protocol分组，历史重分组不是新推理。Oracle研究另列，禁止混作模型成绩。
