# Case1 AwareVLN 工作规范

## 入口与事实
先阅读 README.md、docs/README.md、活动 plan/conclusion 和实际运行清单。用户当前明确指令优先；运行manifest说明实际执行身份，文档状态不能替代原始证据。固定工作流规则在本文件，样本、资源、预算和进度在阶段文档；不不断追加相互冲突的旧授权。

## 工作边界
服务器唯一写根 /data/zy/vln/case1；Windows工作根 C:\Users\20240\Desktop\workplace\vibe_coding_workplace\first-paper\case1，仅连接、必要暂存及本地归档。远端命令使用 cd /data/zy/vln && cd case1。不得访问其他case，不修改父AGENTS.md或父Git。
本阶段允许只读参考harness、指定results-show格式及部署必需全局数据/模型/模拟器来源。共享资产不得修改。backup历史只读，不作为新源码、环境或运行依赖。

## 文件与执行
src实际源码，configs配置/依赖锁，scripts入口，tests回归，patches兼容补丁，docs说明和经验证摘要。runtime环境、data数据视图/派生网格、models权重链接、outputs原始运行、upstream参考、backup归档均被Git忽略。不得复制原始资产进docs绕过忽略。
使用scripts/with_runtime.sh启动数据检查、模拟器、模型及子进程。保护失效即退出，缓存/编译/临时输出全部在case1。
结果登记和生成显式使用 --results-write，仅额外开放 results-show；冻结环境与诊断配置使用 --prepare-configs，仅额外开放 configs/locks 和 configs/diagnostics。真实模型/导航启动不得携带这两个管理参数。
launch-config.yaml记录启动配置，effective-config.yaml记录trainer完成覆写后的实际配置；正式记录绑定每个任务的实际配置及完整配置集合哈希，不得混称。
门槛：归档 → 独立环境 → 数据/保护 → CPU回归 → 网格及真实链路 → 全量 → 独立审计 → 发布。接口、mock、smoke、部分运行和正式成绩分别表述。模型不能读取目标、GT轨迹、测地距离、网格和评测真值位姿。
活动写入冲突、输入身份变化、网格未验收、覆盖异常、非有限正式指标或源码漂移时停止受影响阶段。保留失败与中断；普通导航失败不可择优重跑。只恢复未完成项且先核对冻结身份，不热改运行源码。
资源与PID/starttime启动前刷新，不停止外部进程。

## Git与文档
docs/zx和results-show遵守各自AGENTS.md。同阶段一对plan/conclusion，原始证据在outputs，正式数字由机器记录生成。
2026-10-20用户更新授权：当前阶段快照先发布woaijieyang/FirstPaper-VLN main，提交awareVLN-baseline-construct；随后明确采纳带2条已知退化的pRb研究候选。此次人工发布不代表科学验收通过，详见docs/PUBLICATION_SNAPSHOT.md及同一plan/conclusion。后续自动发布仍须适用门槛。仅服务器case1独立Git，保留远端历史，不强推。审查全树、忽略、大小、秘密与许可，记录README_WORKFLOW后发布，核对远端SHA/tree。
CodeGraph只索引case1活动源码，不遍历backup/runtime/data/models/outputs/upstream/.rebuild及父目录；不能代替动态测试。
