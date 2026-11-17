# Generator：Codex子对话

使用gpt-6.1-sol，reasoning effort=medium。模型实际配置由宿主验证，主对话不得代生成。

prompt.md定义一次完整英文导航指令的联合切割/装配；output.schema.json保留status/subtasks/issues；templates含10个教学输入输出；manifest固定顺序。scripts/workbench.py task --role generator 会读取正文、Schema、全部模板并注入唯一原文。子代理必须真实读编译后的task文件，不能根据路径猜模板内容。

输出仍为普通英文子指令。起点/过程/终点/条件是内在语义检查，不打印人工槽位；不添加动作、距离、停顿或任务终态。遇到文本本身不可消除的实质歧义保留needs_review。在线完成由导航模型判断，本角色没有观察到任何动作已发生。

子线程只读一个task、返回JSON，不编辑仓库，不读其他轨迹、历史review或未来100样本，不递归派生。父线程保存candidate与真实运行凭据，再本人review。repair.md只用于明确标识的回归/修复attempt；不能自动覆盖首轮失败，更不能替代prompt版本精修和新100轨迹测试。


## 单记录子会话复用与审核职责（2026-11-02 用户更新）

原 prompt.md、Schema、10个模板和 repair.md 原样保留。用户批准：generator 生成，独立 reviewer 审核；最多一次由 reviewer 意见触发、且由 generator 自行核实后进行的语义返修。主对话最后逐条复审、汇总和判断达标，不作为返修反馈来源。

需要复用同一 generator 时，每条外层启动使用 [single_record_reuse_wrapper.md](single_record_reuse_wrapper.md) 中的短指令，参数为本条完整 generator_task.txt 路径。不得沿用前条实体/路线/结论，不得将多条混入同一实际输入；接近上下文上限前换新会话。此约束不修改原语义提示词。

并行数量不超过用户上限6且服从宿主上限；完成的自有执行进程及时回收，原始候选、审核与模型凭据保留。桌面通道指定 gpt-6.1-sol/medium；用户另授权 CLI 备用 gpt-5.6-sol/high，实际身份逐调用记录、分组报告，不能混称同模型批次。
