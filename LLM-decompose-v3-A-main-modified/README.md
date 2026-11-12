# A完整处理修改版核心包（非上传原包）

此包对应服务器目录 LLM-decompose-v3-A-main-modified。七个模块、角色提示词、实际编译提示词、schema、15个generator模板和15个reviewer模板保留。测试代码、离线测试样本、运行日志、结果和已退役宿主已按交付要求剔除。

|接口|输入|输出或调用点|
|---|---|---|
|adapter.ingest|task_key、dataset、language、original_instruction|SourceRecord及原文身份|
|orchestrator.engine.run_record|record、call回调、RuntimeConfig|result、events、prepared_candidates、review_receipts|
|host.full_workflow.run|同上，逐条隔离进程|固定恢复profile及完整profile_history|
|generator|完整原文；修订时有原候选和反馈|候选子任务或source limitation|
|renderer.prepare|SourceRecord和候选|FrozenCandidate、实际instruction、映射账本及哈希|
|reviewer|原文、冻结候选、frozen_render|判定、引用证据、阶段与边界检查|
|renderer.commit|同一冻结对象和绑定的审核回执|最终instruction与身份|
|evaluation|逐任务真实记录|配对指标和身份见证|

恢复顺序为main → format_diagnostic → specific_diagnostic → verified_source_suffix。只有技术失败进入下一profile；正常语义回退结束。每次原包内部技术重试和语义修订按其配置执行。最后profile载入recovery-history/renderer_A_final.py，根renderer仍是原版。所有路径明确记录为A修改组。

模型配置见config/runtime.json。并发及资源见config/execution.json。执行宿主在host/complete-B和host/complete-Remaining，包含CLI派发、服务器单记录桥接、导航准备和汇总。它们保留实验时的case1目录、历史对照路径和运行目录依赖，运行前需提供相应case1环境与数据。核心包本身没有附带模型权重、模拟器、数据集或完整导航运行环境。

Windows与Linux的original compile.py会形成不同分隔符的组件路径，实际实验在Linux执行原包编译核验。修改提示词或模板后，应明确建立新版本并使用包内编译器生成compiled文件，再冻结身份。

柜子等地标的语义表述应在generator/reviewer规则与模板中审阅。adapter/renderer负责来源与拼接，任何对路线词语的调整都应记录为候选变化并再次审核。

PACKAGE_MANIFEST.json记录纳入、排除范围和每个交付文件的SHA-256。源码文件与服务器核对一致，README和交付清单为本次新增说明。测试结果来自原运行环境，包内按要求不附测试代码。
