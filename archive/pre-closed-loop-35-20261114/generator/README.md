# Generator｜唯一语义作者

维护 `prompt.md`、`repair.md` 和输出 Schema。G0 必须完整阅读原文、组装完整局部过程、判断切分合法性与收益；不因短指令而提前 KEEP，也不因动词多而逐动词切分。G1 只对 Reviewer 的每条意见独立作出 accept / partially_accept / reject / unresolved 决定。Reviewer 的修复建议是证据驱动的建议，不是可直接执行的 patch。

`compiled.txt` 与 `compiled_repair.txt` 由 `python -m host.compile` 生成，才是实际发给模型的文本。15个教学模板只作对照，不是唯一答案或在线路线事实。
