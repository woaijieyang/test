# Renderer｜来源可追溯的机械装配与冻结

`freeze(Source, parts, separator='\n')` 返回 `Preview`；`unchanged(Source)` 逐字符返回原文。Renderer 不作语义判断、不决定切点、不在 Reviewer 通过后润色文本。

- `SOURCE_EXACT`：原文原样透传，包括前缀/后缀/原生换行。
- `BOUNDARY_ONLY`：有序源片段覆盖正文，只把授权切点处原有空白换成 LF。
- `ASSEMBLED_SINGLE`：有来源支持的单段重组；不得因为只有一段就恢复原文。
- `ASSEMBLED_MULTI`：来源支持的多段重组；新阶段之间用 LF。

可靠的 COPY/MOVE 片段保留内部原生空白；编辑片段和拼接缝记入 ledger。重复文本导致来源对齐不唯一时，不擅自选择第一个位置；如原生空白也无法消歧，则技术失败并由 Host 精确回退。`unused_source` 是字面映射覆盖情况，不是语义遗漏证明。索引单位是解码后 Unicode code point，0-based half-open。

R2R/RxR profile 只描述原文特征，不选择不同的空白清洗规则。默认新阶段分隔符为 LF；SPACE 只可作为独立预注册格式实验。
