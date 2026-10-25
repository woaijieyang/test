# Case1 测评结果

本目录是正式结果唯一入口，2026-10-24由docs/results完整迁入。历史原始outputs不移动，旧run/验证回执和retracted状态保留。

- [模型测试比较总表](MODEL_TEST_RESULTS.md)：R2R/RxR分别列单块、累积与完整范围，记录运行身份和来源。
- [原完整测评登记表](model_results.md)：由records.json生成。
- records.json：既有正式全量结果登记索引；逐run Markdown保留。
- checkpoint-choice-historical.md：历史完整run按当前VLN清单重分组，不冒充新的模型推理。

新正式测评在outputs产生原始证据，通过覆盖、模型动作审计与独立指标复算后登记；普通失败保留。部分进度不得填成完成成绩。源VLN与全局results-show只读。
