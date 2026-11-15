# Adapter｜R2R en / RxR en-US 原文接入

`from_record(row, dataset=None, split=None)` 支持：
- R2R VLN-CE：`instruction.instruction_text` 或 `instruction_text`；若未提供 language，按 R2R 数据约定使用 `en`。
- RxR en-US guide JSONL：字符串 `instruction` 或 `instruction_text`。
- 通用规范行：`original_instruction`。

必须显式提供 dataset。若没有 `task_key`，必须提供 split 与 R2R `episode_id` 或 RxR `instruction_id`。冲突字段、非目标语言、空文本和错误源哈希均拒绝。原文只做一次 UTF-8 解码；不 trim、不规范化、不重写。Adapter 不把 scene/path/GT/score 投给 LLM。

`profiles.json` 中的数字是本次上传 evaluation 文件的描述性统计，不是生产格式约束。
