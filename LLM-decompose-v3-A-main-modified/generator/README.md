# Generator：唯一语义作者

输入是完整 `original_instruction`。输出仍为v1.3的 `status / subtasks / issues`；不得输出导航动作token、状态图、字符offset或源文以外的场景事实。

先全文识别事件和关系，再装配完整局部过程，最后选择合法且有用的切点。保持原文也必须经过分析；不能短句默认KEEP，也不能把每个到达点或动作词强制成行。入口、过程、目标、终态与条件是语义要素，不是五句模板。单段必要装配是有效输出，不能因为一段而回退源文。

`prompt.md`保留v1.3核心并落实本版任务；`../contracts/execution_standard.md`是两角色唯一共用标准。`templates/01–15.json`固定加载，前10例输入/输出保持底稿身份，新增例补足短单目标、多目标、终止绑定和关系主体等情形。`compiled.txt`已经展开文件内容；普通API不会自行跟随本地模板路径。

正常调用使用compiled.txt与独立JSON用户消息。修订调用使用compiled_repair.txt及repair.schema.json，输入source/candidate/reviewer_feedback，输出candidate/feedback_response。对每项建议独立接受、部分接受、拒绝或未解决；正确诊断可能伴随错误修复选项。不要为迎合reviewer改正确部分，不输出推理轨迹。

baseline/只用于可追溯，不运行。改prompt、模板或Schema后必须从包根目录重新编译，并建立新的实验目录。质量标准和模板说明在docs/QUALITY_AND_TEMPLATES.md。只有普通英文最终进入导航器，所有反馈与检查留在离线日志。
