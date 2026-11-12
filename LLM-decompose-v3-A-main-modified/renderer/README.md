# Renderer：准备、冻结、提交

`prepare(source, proposed, explicit_maps=None)`在审核前创建FrozenCandidate。依据来源决定SOURCE_EXACT、BOUNDARY_ONLY、ASSEMBLED_SINGLE或ASSEMBLED_MULTI，并记录原候选、实际审核候选、instruction、stage_spans、来源ledger和哈希。

SOURCE_EXACT使用完整原字段；单段但确有语义装配必须保留编辑结果。有来源的复制片段保留内部双空格、TAB、LF/CRLF和Unicode；新建词缝用单空格、新阶段之间用一个LF。逻辑阶段来自数组/记录的区间，原生换行不自动增加阶段数。所有可验证空白恢复必须发生在冻结和review之前。

`bind_review(source, frozen, report, request_id=..., review_prompt_sha256=...)`绑定同一个记录、源文、候选、最终英文、冻结方案和reviewer版本。`commit(...)`重新核验这些身份并且只返回既有冻结字符串；禁止在commit之后strip、join、添加标点或换行。错误、过期或跨record回执不能复用。

`fallback(source, reason)`直接返回源字段，分别记录source_limited、unresolved_after_one_repair、technical_failure。fallback不等于通过审核的完整新计划。

`FrozenCandidate.verify()`检查哈希和内部区间/text/UTF-8/分隔符一致性，不只看单一摘要。哈希不是语义证明或抗恶意宿主的签名。用单元测试中的人为pass夹具演示commit也不是模型验证。

高级CLI仅准备请求/冻结文件，真实语义审批仍在orchestrator流程里。evaluation的格式对照不能借用另一字符串的审核回执直接发布。
