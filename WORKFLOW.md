# Case2 工作流

先检查 AGENTS.md、本阶段 plan/conclusion、资产身份和活动进程。多轮任务使用 tools/case_autolog.py begin/finish。运行前使用 tools/case_tracker.py start-run，完成或失败后用 finish-run 写入真实证据。既有 evaluator 将不可变原始记录写入 outputs/<run-id>，runs 中的 tracker 清单引用该路径。

构建使用独立 runtime；模型和模拟器使用 scripts/with_runtime.sh。阶段顺序：发布快照导入 → 环境/数据/保护 → CPU/原生检查 → 完整 episode 数据流审计 → baseline 发布 → HAMLET 核心集成与回归 → 正式测评与独立审计。

每个阶段保留失败；检查 actual model inputs、解析、primitive action、反馈和终止。诊断不登记为完整 benchmark。发布检查 staged tree、忽略、秘密、文件大小和许可；推送后核对远端 SHA/tree。最终执行 autolog audit --strict 与 tracker validate。
