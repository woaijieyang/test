# LLM 子任务分解与审核

统一可修改配置在 [workflow.toml](workflow.toml)。generator 与 reviewer 共用顶层 `max_review_rounds`，各自配置段通过 `review_limit = "shared:max_review_rounds"` 引用，不维护两份独立上限。修改配置仅作用于下一批启动；每批先复制并冻结配置、提示词与模板哈希，运行中不得修改批次规则。

## 目录与提示词保护

- `generator/`：用户原始生成提示词、Schema、10 个教学模板；另附 `single_record_reuse_wrapper.md`，定义同一子智能体逐条处理时的短隔离指令。
- `reviewer/`：用户原始审核提示词、Schema、10 个教学模板。
- `workflow.toml`：两角色共用的轮数、技术重试、并发、模型与失败回退设置。

用户原始 prompt.md、Schema 与教学模板不修改。上层规则只约束调度、职责和结果保存；遇到旧文档中“主对话直接承担 reviewer”的要求，按用户后续明确安排执行下述职责。

## 审核流程及轮数

每次模型输入只含一条完整 original_instruction、该角色完整规则和模板。generator 输出候选；reviewer 对照整条原文检查遗漏、添加、顺序、作用域、衔接与粒度，接受符合要求的不同切法。reviewer 不以反驳 generator 为目标，不凭表达偏好要求返修。

`max_review_rounds = 2` 包含首次审核，故当前批最多返修一次。设为 1 则没有语义返修；设为 N 则最多 N-1 次。generator 必须先核对 reviewer 指出的证据和原文，仅修复确实存在的问题。技术失败使用独立的 `max_technical_retries` 记账，不冒充语义通过。所有原始输出与失败均保留。

主对话逐条最终复审、汇总和判断是否达标，不向 generator 发返修指令。达到审核上限仍不通过，或最终复审拒绝时，保留完整原指令作为未分解输入；不换轨迹、不补样、不将回退计作分解成功。失败报告保留原文、最终分解（无分解时明确为空）与主审判断。

## 子智能体复用及模型记录

启用 `allow_session_reuse` 只允许同一子智能体按顺序处理独立记录。每条开始必须使用 [逐条复用隔离指令](generator/single_record_reuse_wrapper.md)，重新实际读取本条完整任务包，不沿用上一条的实体、路线、候选或判断；接近配置的上下文比例时更换子智能体。不得把多条原指令混成一个输入。实际并发取配置上限与宿主可用额度的较小值；只回收本任务已结束资源。

本次 pilot40 的桌面调用为 gpt-6.1-sol / medium；桌面容量阻塞后使用用户明确授权的 CLI gpt-5.6-sol / high，CLI 每次调用为独立会话、两条流水线并行。复用开关的存在不代表本批实际采用了上下文复用。实际模型、effort、子线程 ID、任务与候选哈希均由宿主回执记录，混合模型结果分开说明。

## 本批产物与测评

执行记录位于 `/data/zy/vln/case1/outputs/subtaskAdapter/llm-split-20261102-r0`。每条保留 source、完整 task、candidate、reviewer 意见、主审结论和宿主元数据；`attempt0` 不覆盖。`task-read-evidence-audit-v2.json` 从真实子会话工具输出核验完整任务阅读，不能用自我声明替代。

用户阅读的失败汇总为该运行目录的 `reports/分解失败汇总.md`。pilot40 已完成 40 条主审，39 条最终可用，1 条保留原指令。首次语义审核与返修结果分别统计；技术失败另列，不等同于分解失败或导航失败。

同一原 train40 进行 baseline/A/B/C 导航对比：A 追加当前 Goal；B 再追加模型报告的已完成 Goal；C 再追加完整原指令。保留原生 reasoning、时钟和控制流，回退条目四组均使用完整原指令。导航进度以 `navigation/controller-v2-events.jsonl`、真实进程和封存审计为准，不从本文推断已完成。只有某方案在 R2R、RxR 的 SR 均不下降且至少一项上升，才解锁冻结 fresh100；文本审核通过率不等于导航 SR。

调度进度补充（2026-11-03）：baseline 完成后，调度器已按记录从 v2 迁移到 v3，保留正在运行的 worker/监督进程，复用空闲 GPU 处理未启动批次。当前入口以运行目录 navigation/current-controller.json 为准，事件见 controller-v3-events.jsonl；v2 退出是有凭据的主动调度交接，不是导航失败。

最终状态（2026-11-03）：原 train40 文本 39 条最终通过、1 条原文回退；四组 160 条完整导航结果审计完成。baseline SR 为75%/90%，A40%/50%，B20%/40%，C40%/55%，fresh100 因条件不满足保持 NOT_RUN。三个场景切换超时批次保留失败，21 条完整旧结果保留，6 条未开始导航任务首次执行完成，0 轨迹重跑。完整结论与口径见运行目录 README.md、TECHNICAL_PLAN.md 和 reports/ABC_COMPARISON.md。
