# Adapter：不可变原文与来源对应

这是离线源数据适配器，不是GoalAdapter，不切分语义、不改路线。

`ingest(record)`创建SourceRecord：task_key、数据集/语言、完整原文、UTF-8哈希、字符区间与格式profile。支持规范original_instruction，以及显式instruction_text或嵌套instruction.instruction_text；同时提供时必须一致。R2R/en和RxR/en-US之外拒绝。成绩、地图和GT字段不进入model_input。

`provenance.py`验证完整有序分区、唯一精确片段或宿主提供的offset/quote。不得在单词、缩写、连字符、数字小数或CRLF中间切边界。字符offset与UTF-8 byte offset不能混用。

`alignment.py`用于必要编辑的保守表面对应：唯一精确、区分大小写/标点的词元串可以恢复其源内部空白。不会修改候选词元、做同义词匹配或断言模型真实复制意图。重复且来源不清的普通新文字可以记录为EDIT；涉及有歧义特殊空白时不得随意选第一次出现，应由宿主给明确映射或技术回退。

COPY/MOVE复制实际源字符；EDIT是明确新文字；SEAM表示新连接。映射无法证明语义含义，语义仍由generator/reviewer处理。自动准备前后的候选与来源ledger均保存。模型不用生成offset。

公共类型与函数见source.py、provenance.py、alignment.py。完整接入用renderer.prepare，避免调用端在多个位置自行拼装。显式混合映射示例在examples/mixed_provenance_demo.py。
