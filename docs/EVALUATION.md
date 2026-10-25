# 完整测评、恢复与结果登记

## 范围与协议

正式范围为 R2R val_unseen 1,839 条、RxR guide/en-US val_unseen 1,223 条。使用官方 AwareVLN 权重，保留原 prompt、帧采样、解码、动作步长/转角、停止阈值与预算。正式配置、种子和网格在运行前冻结。

任务键包含 dataset、split、language、scene、episode、instruction。RxR 不仅使用 episode ID。两个数据集分开统计，不平均分片均值，也不把不同范围的平均值当作性能增减。

## 诊断与正式运行

诊断清单必须先于模型结果生成。R2R 选择同一逻辑分片内、先执行正常场景 A 再执行问题场景 B 的两条任务，并在相同物理 GPU 上让 B 单独运行。验收检查实际 episode 序号，不能把两个首任务当作顺序复验。RxR 包含原 33 条及两条其他场景任务。

`freeze_diagnostics.py` 使用 `--prepare-configs` 生成清单。真实模型诊断、Oracle 运动检查与正式 Full 使用不同 run ID。Oracle 使用 `configs/diagnostics/rxr-motion.json` 的48条预先冻结任务，包含原33条、全部13个原始离网起点与9条已授权修正任务的并集；检查reset严格等于派生标注，保留名义位移偏差诊断；以同一profile原生独立回放核对全部动作轨迹并拒绝跨楼层跳跃。诊断和历史结果不得充当正式结果。

`evaluate.py` 接受 dataset、run-id、scope、profile；诊断还需要 episode-ids。可用 `--gpu-ids` 固定诊断卡。默认只调度空闲设备，最多八卡、64 个逻辑 CPU；无空闲资源时等待。正式 Full 必须先持有与当前源码、网格及全部证据匹配的 engineering gate。

## 配置与模型边界记录

每个 worker 保存启动配置 `launch-config.yaml`。trainer 完成 split、语言、分片及输出目录覆写后，保存 `effective-config.yaml`。每条结果绑定实际配置的 SHA；`effective-configs.json` 汇总整个 run 的实际配置。报告中的 config_sha256 指该集合，base_config_sha256 仅指入口 YAML。

模型生成前记录 `model_input`，生成后以 call ID 绑定 `model_call`。审计重新解码实际输出 token IDs，核对原始文本、输入配对、图片像素、原解析与每个 primitive 动作。轨迹另外记录评测侧位姿、碰撞、终止原因及 STOP 来源，评测信息不进入模型。

## 中断与恢复

每个结束的 episode 原子提交 `result.json`，控制器从提交文件合并总记录。任务已经结束但提交被中断时，从完整闭合轨迹恢复结果，保留恢复标记，不重新调用模型。

恢复前检查控制器锁、PID/starttime、仍存活的 worker、冻结源码、模型、数据和网格身份。只补未完成项；普通导航失败或步数耗尽计入有效结果，不择优重跑。所有 attempts 与失败日志保留。影响执行语义的改动需建立新身份并重跑受影响批次。

## 审计到登记的顺序

以下命令要求 RUN 指向已有 run_manifest.json 的实际运行目录；具体运行目录及已执行命令记录在 conclusion。

```bash
test -n "${RUN:-}"
scripts/with_runtime.sh runtime/awarevln/bin/python -B scripts/aggregate_results.py --run "$RUN"
scripts/with_runtime.sh runtime/awarevln/bin/python -B scripts/recompute_metrics.py --run "$RUN"
scripts/with_runtime.sh runtime/awarevln/bin/python -B scripts/audit_model_trace.py --run "$RUN"
scripts/with_runtime.sh runtime/awarevln/bin/python -B scripts/validate_results.py --run "$RUN"
scripts/with_runtime.sh --results-write runtime/awarevln/bin/python -B scripts/register_results.py --run "$RUN"
scripts/with_runtime.sh --results-write runtime/awarevln/bin/python -B scripts/render_results.py
scripts/with_runtime.sh runtime/awarevln/bin/python -B scripts/render_results.py --check
```

登记必须同时满足：恢复原始完整任务集合、没有重复或未解决运行错误、指标有限、源码/环境/输入身份未漂移、模型到动作链路通过、原生指标与独立轨迹复算一致。完整覆盖本身不等于语义适配正确。

SR、SPL、nDTW、Oracle SR 展示为百分比，NE 为米；计算保持原精度。任何非有限值都不能通过静默删行消失。普通导航失败正常进入分母。

## 统一结果与修订

原始证据在 outputs。records.json 是正式结果的轻量索引，model_results.md 和每个 record_id 报告由脚本生成，不能手工修改数字。新记录追加；更正要保留原记录、原因及被替代/撤回状态，不能覆盖原始 run。

新网格协议与旧网格成绩分开，不直接计算收益。阶段 conclusion 解释过程并链接结果，不维护另一套数值。results-show为case1正式模型结果入口；全局/data/zy/vln/results-show只作格式参考、只读。


## Landmark发布门槛：原生回放与源几何分别验收

`tests/landmark_diagnostics/publication_gate.py`不仅检查完整33954条原生执行/回放，还要求显式解除`geometry_review_required`并提供`source_geometry_acceptance`（case1内报告路径及SHA-256，且进入acceptance的receipts）。只写status=PASS不能越过缺失的源几何验收。

源几何汇总必须绑定同一完整任务清单、同一profile及同一native validation摘要，并绑定实际验证器路径/源码摘要。当前准入模式仅为`exact_continuous_linear`；5cm采样、普通GLB解析或待审查的台阶替代曲线不能自动作为该模式通过。用户尚未决定台阶协议，未来若另行明确采用，必须版本化协议、验证器和准入测试，不得仅修改状态标签。

汇总字段包括status、coverage_complete、verification_mode、manifest_sha256、profile_sha256、native_validation_sha256、body（height=1.5/radius=0.1）、foot_epsilon_m=1e-5、radial_epsilon_m=1e-6、validator_path、validator_sha256、audit_issues、unresolved及records。每条记录必须对应冻结task_key/scene/source_record_sha256，标为PASS，geometry_kind为NATIVE_LOADER_EXPORTED_TRIANGLES，提供native_trace_sha256和geometry_sha256；actual_position_contacts、continuous_linear_contacts、hypothetical_step_segments均为0。逐条actual_actions之和必须与原生全量验证一致。重复、缺失、外来任务、源几何/网格身份漂移、未原生确认几何和更改身体/容差均拒绝。

这个契约不是现有数据已通过的声明。目前没有生成实际PASS的全量源几何报告，整体仍NOT_ACCEPTED。真实验收仍须完成相应执行、独立复算和证据检查；单元测试中的合成记录仅用于验证拒绝规则。


## 冻结描述与实际验收状态

正式报告的实验身份会逐字保留冻结协议描述；其中AUTHORIZED_PENDING_VALIDATION是创建协议时的状态，不是一个持续更新的实时字段。正式准入以运行目录validation.json、独立指标/语义回执及results-show/records.json的登记状态为准。不得为把描述改成PASS而修改正在运行的冻结配置。当前endpoint9协议的dataset_roots只覆盖RxR派生标注；R2R继续使用原R2R标注，但两者使用明确记录的修复网格版本。

同一正式run只能有一个控制器。evaluate.py使用非阻塞.controller.lock，且--resume拒绝仍存活的owned worker、扩大冻结GPU白名单或改变输入身份。不要在现控制器运行时另起同run，也不要抢先启动它已经安排的后续数据集，否则会破坏唯一所有者和恢复流程。


## 新身份测评前的信息流硬门槛（2026-10-17T15:49:57.265547+08:00）

用户明确要求信息流完全正确后再正式测评。已有文件、目录名、配置声明、模型可加载、静态连通或旧协议语义PASS都不能代替新身份的实际链路验收。当前endpoint115信息流状态为BLOCKED_NEW_FORMAL_EVALUATION_INFORMATION_FLOW_NOT_ACCEPTED；报告outputs/verification/information-flow-readiness-endpoint115-v1/validation.json。

本次只读审查确认两个待补环节：现configure_dataset只改RxR，不能证明新R2R派生标注和GT被正式入口读取；现audit_model_trace对processed_image_sha256仅检查存在，尚未从冻结图像处理器、原输入图片及实际dtype/shape/order独立重算模型张量。现有记录应保留，不把检查范围不足包装成已通过。旧endpoint9适配器对其冻结范围的行为不被追改，新协议接入需在新源码身份中实施并重验。

新身份正式启动前必须具备以下实际证据：

|信息流边界|必须核验的内容|
|---|---|
|入口→实际执行|启动worker、导入模块、解释器/依赖、模型、源码哈希；必须核对真实绑定，不能靠版本标签|
|协议→加载数据|R2R与RxR实际annotation/GT路径和哈希；task_key包含instruction；reset坐标等于派生记录；未选语言/字段保持|
|配置→场景|effective配置与实际加载profile/网格SHA一致，体型、传感器、动作和预算匹配|
|观测→模型|指令、当前及历史RGB顺序/像素、prompt、token IDs、图像处理器、最终张量内容/shape/dtype逐项对应；独立重算张量，不能只检查字段非空|
|真值边界|GT轨迹、目标、测地距离、Oracle、网格和评测位姿仅评测侧可见；检查实际送入模型的完整参数/对象边界，不只检查字段命名|
|模型→动作|真实output IDs重新解码、normalize、官方parser/动作队列、每个primitive和call_id完全一致；异常输出/STOP/步数耗尽/碰撞均保留|
|任务间状态|队列、历史帧、推理文本、计数器和随机状态reset；单任务/交换顺序/分片变化独立复验，不能复用同一首任务冒充顺序检查|
|动作→结果|实际轨迹独立原生回放、源几何审查及指标复算；全量身份/分母/异常/attempt不混淆|

先在独立诊断run完成新身份真实模型链路核验，诊断不计正式成绩；全部前置门槛通过后才允许新身份完整1839/1223测评。后续正式全量仍须逐条审计，诊断PASS不能替代全量审计。GPU允许4–7最多4张，只选空闲资源。当前冻结RxR继续，不热改src/scripts/config/runtime。任何缺失、错配、未重算、泄漏或未完成证据都保持阻断。
