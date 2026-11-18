# Host｜编译、校验、编排、快照和精确回退

`run_record(source, transport, pins, separator='\n')` 执行最多四次调用：G0 → R0 → (必要时 G1 → R1)。R0/R1 审查与 actor 最终使用的是同一个冻结 Preview。Host 只做 JSON Schema、原文引用、模型/effort/request receipt、候选快照、renderer ledger 和发布策略校验；它不是第三个审查角色。

真实 `transport(request)` 必须返回 `{'output': parsed_json, 'receipt': {'model': actual_model, 'effort': actual_effort, 'request_id': actual_request_id}}`。模型和 effort 必须由实验配置固定。没有实际 provider receipt 时不能宣称该请求由指定模型完成。

R0/R1 pass 才提交候选。unresolved、一次修复后仍有问题、或技术异常均精确回退到原始 source。`fallback_unresolved` 与 `fallback_technical` 必须分开统计。`receipt_for_navigation()` 应在原导航器完成完整prompt/tokenization后调用；它检查输入字符串身份，不会替调用方验证 tokenizer 或 image extraction。
