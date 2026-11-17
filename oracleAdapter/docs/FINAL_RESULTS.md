# OracleAdapter 本轮研究最终结果

> **2026-10-20授权更新**：用户要求先发布当前阶段快照，并明确“可以先采纳”pRb候选。该候选已被阶段采纳用于后续Landmark研究，2条已知退化与全部失败保留，零退化及全科学验收仍未通过。下文此前“未采纳/无发布资格/未push”是相应历史时点的结论；当前范围、原模型封存及实际发布核验边界见[阶段发布说明](../../docs/PUBLICATION_SNAPSHOT.md)。

生成时间（UTC）：2026-10-19T07:14:11.804536+00:00。状态：**有限研究运行与独立证据核对已完成；全部导航门槛未通过，无发布资格，未自动commit/push。**

本报告使用原37016任务的完整分区：v1封存5144条、v2续跑31872条。每个任务只有一条最终执行结果，普通失败未重跑；两段仅有明确的历史几何回执格式兼容差异，实际源码身份分别保留。不得将本报告理解为一个源码SHA、原模型SR、搜索完备性证明或已成立的算法创新。

## 全量执行与验收

原目标和特权信息不同，以下是各自任务覆盖账目，不计算一个混合的Oracle成功率。完整信息、语言、split、profile及源码版本分组见后文。

| 任务范围 | 完整分母 | 严格通过 | 未通过 | 解释 |
|---|---:|---:|---:|---|
| R2R endpoint115有序参考 |1839|1280|559|541预算失败、18前沿耗尽 |
| RxR endpoint115有序参考 |1223|654|569|563预算失败、6前沿耗尽；官方动作可用性分层报告 |
| Landmark完整参考出现序列 |33954|20507|13447|9086预算、719初始源接触、231路线证据但端点接触、2670拓扑映射、741缺适配 |

全部33954 Landmark记录及train/val_seen/val_unseen均保留。held114从原constraint-blockers.json按task_key核对，114/114仍在本轮，均为identity_or_adaptation_missing静态失败；它们属于741，未另加分母、未删除。总计2544634实际动作和相同数量的逐任务独立进程原生回放；两段全量审计检查原始动作流、任务、源码归档、导入绑定和回放回执，没有将失败前缀当完整成功路线。静态失败没有被强行执行。

| Landmark split | 总数 | 严格通过 | 执行失败 | 有路线但端点门槛失败 | 静态失败 |
|---|---:|---:|---:|---:|---:|
|train|26464|15805|7620|204|2835|
|val_seen|2939|1740|870|14|315|
|val_unseen|4551|2962|1315|13|261|

## 方法类别、对照与结果解释

R2R/RxR教师的目标是按序经过派生参考点；Landmark教师的目标是按序经过完整原参考出现序列并保留landmark边界，这比只到终点或只过标记landmark更强。教师可读真值位姿、网格、目标、参考路径和源几何，Landmark另有标注；只有初态和身份兼容的分支提供official_actions。真实AwareVLN模型未得到这些特权，也未使用本轮Oracle替代策略。

| 全量固定信息分支 | 任务数 | 严格通过 | 普通执行失败 | 路线证据但端点失败 | 静态失败 |
|---|---:|---:|---:|---:|---:|
|r2r::no_compatible_action_prior|1839|1280|559|0|0|
|rxr::matched_official_actions|1185|642|543|0|0|
|rxr::no_compatible_action_prior|38|12|26|0|0|
|landmark_rxr::no_compatible_action_prior|31168|18226|9315|216|3411|
|landmark_rxr::matched_official_actions|2786|2281|490|15|0|

这些分支不是随机分配的同质算法对照。官方动作可用性由预先冻结的身份/初态条件决定，不能用表中两分支比值声称算法收益。组合按固定规则先执行合法官方建议，首次不合法建议在实际执行前拒绝或建议结束后切入既有原生贪心/有限动作搜索；从真实末状态继续，不重置姿态、不逐任务挑方法。

| 开发对照 | 实际结果 | 成本与归因 |
|---|---|---|
| 有损键+前进标记 vs 无损状态标签，12任务两臂 | 两臂各5/12；端点4/8、Landmark1/4，恢复0/退化0 | 无损键CPU增加；25对原生同键不同后继反例成立，但未显示全路线收益 |
| 同官方动作信息，受保护建议 vs 固定建议后搜索，133任务两臂 |51→90；39恢复/0退化 | 执行CPU445.828→2530.914秒，不能称同计算量收益 |
| 去掉官方动作信息的纯搜索，133任务 |54通过，组合90通过 | 纯搜索CPU4645.626秒；信息条件不同，单列；组合实际保留两个单方法成功并另有8例互补，不登记事后并集 |
| 当前端点3062 vs 历史endpoint115-v3 |1934 vs2225；295仅旧版通过、4仅本轮通过 | 输入/目标/初态/profile/几何已核对；历史完整计算条件不等价，不能作同预算因果解释或复制旧PASS |

成熟方法、实际源文件、冻结提交、许可证、动作空间差异与选型见[RELATED_WORK](RELATED_WORK.md)及[SOURCE_IMPORT](SOURCE_IMPORT.md)。本轮只采用有限方案；未移植OMPL连续控制、ETP随机恢复或瞬移，不增传感器、动作、体型或预算。已观察过开发/历史验证任务，不能宣称盲测泛化。无损状态、固定组合和证据工程均有成熟先例，目前不支持已形成算法创新的结论。

## Landmark适配独立结论与逐项台账

所有证据路径以下相对于case1，原始资产只读。

| 问题 | 逐项结果与仍未知 | 台账 |
|---|---|---|
|461缺发布图视点|全部在冻结原MatterSim图中同名且included；365有官方CE按稳定任务/顺序对应的位置，96无直接CE位置。未证明改名/合并/替代关系，不能用最近点冒充身份。CE位置没有viewpoint ID，逐节点转换日志缺失限制保留|outputs/oracleAdapter/original-graph-lineage-bound-v2/viewpoints461.json；continuous-reference-lineage-v1/viewpoints461-reference-sources.json |
|8034未匹配CE记录|全部与原始RxR Guide的ID、场景、split、语言、path_id、有序路径匹配；在已核查CE角色/split中仍缺匹配。不能归为格式错误、已证明的官方过滤或不可修复；历史转换排除原因未知|outputs/oracleAdapter/original-guide-match-v1/unmatched8034.json；identity-review-v1/unmatched8034.json |
|原/发布连通图|原始33954路径邻接全部成立；发布图11689缺ID、14491缺原直接边、7774原直接边齐全。缺直接边不等于无替代图路，更不等于物理无路|outputs/oracleAdapter/raw-source-graph-paths-bound-v2/all33954.json |
|pRb已知edge51|不是原图直接边；660源任务中直接用此边0、含两端21；原图存在3跳路。未擅自替换landmark路线，旧弱回放不能登记当前严格通过|outputs/oracleAdapter/raw-source-graph-paths-bound-v2/known-edge.json、known-scene-tasks.json |
|train:43144子段间连接|源路径cc03→7389连接边显式保留，10子指令不丢。统一全量中该任务524真实动作、524独立回放严格通过；无原适配同预算运动对照，不能把成功全归于映射或Oracle|outputs/oracleAdapter/source-connectors-v1/changes.json；logical-full-review-v1/all-task-lineage.json |
|重复访问/边界|出现次数和顺序由整条路径约束；真实全集当前无重复视点ID、匹配CE无零长相邻点。CPU回归覆盖回环/零段，不能据此宣称实际全集包含这些情形|outputs/oracleAdapter/continuous-reference-lineage-v1/all33954-reference-lineage.json |

原适配+原Oracle、原适配+新Oracle、修复适配+原Oracle、修复适配+新Oracle没有形成完整四臂全量因果实验。本轮身份/原图/连接边审查和Oracle开发分开归因，唯一连接边的静态修正和真实路线证据明确列出，不把混合变化包装为算法收益。

## 失败分类、物理解释与最小后续条件

全量失败逐任务记录在outputs/oracleAdapter/logical-full-review-v1/failures.json：包含生产者manifest、执行/原任务hash、实际receipt、缺失目标、离网点、断边、源接触参考点/端点、最后执行位置、下一必需参考点、最后搜索/拒绝计数以及回放告警。

| 类别 | 本轮数量 | 证据含义与边界 | 若后续再研究所需条件（本轮不实施） |
|---|---:|---|---|
|缺身份/适配|741 Landmark|目标坐标不全，不执行；含held114。已确认原身份不等于具有连续合法位置|作者转换来源或可验证的语义位置对应；held114需新增有效支持证据，否则改变位移/几何约束属于新协议 |
|拓扑映射|2670 Landmark|当前profile的点或相邻参考查询失败|按证据核查映射/通道，图可达不能直接替代动作可执行；不以盲扫/造桥处理 |
|初始源几何接触|719 Landmark|实际执行前initial_source_contact，未伪造绕过初态|区分支撑面、身体交叠、加载几何及验证器近似；要有独立接触证书。改变初态需另授权 |
|路线成功但端点源接触|231 Landmark|完整受保护动作路线不解除必需锚点端点检查，单列而不计严格PASS|核实锚点含义和体积；不得仅因路线到达邻域而删除门槛 |
|有限预算搜索失败|10190（R2R541/RxR563/Landmark9086）|记录bounded_search_did_not_find_plan；唯一触发预算未单独捕获，不能全部叫5000节点耗尽|有限搜索无完备性；未来改算法需固定对照，额外预算另列。不能直接认定数据不可达 |
|前沿耗尽|24（R2R18/RxR6）|当前状态表示/动作/剪枝下未找到路，不是物理不可达定理|可复核状态与后继及高度投影；保持现验收，不能删线性扫掠 |
|基础设施历史错误|1次旧v1阶段|历史几何回执格式KeyError，受控停止；兼容修复后只续未完成任务，旧错误/CPU记录保留|已完成元数据修复，不归为导航修复或删失败；最终37016均有终态回执 |

Habitat原生回放可复现性与物理独立性不同。当前规划/审计共用原生引擎及几何模型；部分关键接触已有有理数不同实现证书，但未对所有失败逐一给出完全独立的物理证明。台阶线性扫掠可能比原论文运动语义更严格，原生内部连续身体曲线未观测，因此本轮保持原线性标准，不采用假设台阶曲线、不改容差。未解决项有可追溯类别和证据，仍有上述未知。

## 原论文A与当前连续B

A的论文规则含失败中间landmark后重初始化、3m和10离散步；官方仓库没有可复用evaluator，reset朝向/隐藏状态、STOP预算边界和精确聚合尚缺实现依据。发布166663子段比论文166740少77（train71/seen5/unseen1）。本轮完成来源/就绪审查，**没有复现A或报告SA/SSA/LN**。B按当前固定原生动作整条无重置执行，强制完整参考顺序；B不能替代A，也不是完整语言语义证明。

## 资源与性能

完整执行与逐任务审计进程CPU合计239.845899小时；仅teacher记录CPU185.407871小时。控制器累计保守CPU计费274.021687小时，小于720小时上限。进程CPU包含加载/静态核查等，teacher CPU只是子集；保守计费不等于实际CPU。全过程无GPU、最多16CPU工作槽，未挤占外部任务。原生贪心C++内部探测未插桩，调用计数是adapter可见范围，不伪称完整模拟调用总量。RSS只报峰值/分位数，不求和成实际总内存。

下表按源码版本、数据集、split、语言、实际官方动作信息分别列出teacher墙钟P50/P95、CPU总量、搜索展开和RSS峰值，失败均计入；不同组不能直接作算法公平比较。完整成本、预演调用、碰撞查询、规划次数/切换次数在validation.json和all-task-lineage.json。

| 执行版本/数据/split/语言/动作先验 | N/实际运动 | 通过 | wall P50/P95 秒 | CPU秒 | 展开数 | RSS峰值MiB |
|---|---:|---:|---:|---:|---:|---:|
|full-continuous-reference-v1/landmark_rxr/train/en-IN/guard_then_search|265/265|222|2.769/61.913|3050.514|99159|628.48|
|full-continuous-reference-v1/landmark_rxr/train/en-IN/none|1119/1068|702|5.559/65.173|24364.367|993707|635.94|
|full-continuous-reference-v2/landmark_rxr/train/en-IN/guard_then_search|1256/1256|1022|1.218/62.334|15596.740|836761|628.93|
|full-continuous-reference-v2/landmark_rxr/train/en-IN/none|15008/13169|8580|3.160/63.716|272557.538|15775605|632.06|
|full-continuous-reference-v1/landmark_rxr/train/en-US/guard_then_search|168/168|141|2.824/61.824|1820.330|65215|628.48|
|full-continuous-reference-v1/landmark_rxr/train/en-US/none|530/507|357|4.993/64.521|10368.481|450458|629.74|
|full-continuous-reference-v2/landmark_rxr/train/en-US/guard_then_search|643/643|530|1.274/62.095|7723.641|418361|628.23|
|full-continuous-reference-v2/landmark_rxr/train/en-US/none|7475/6553|4251|3.238/63.712|136617.933|7877328|632.01|
|full-continuous-reference-v2/landmark_rxr/val_seen/en-IN/guard_then_search|155/155|129|1.605/61.059|1528.163|101879|625.80|
|full-continuous-reference-v2/landmark_rxr/val_seen/en-IN/none|1805/1595|1032|3.493/64.157|34673.919|1902073|630.56|
|full-continuous-reference-v2/landmark_rxr/val_seen/en-US/guard_then_search|81/81|70|1.277/61.060|641.584|32251|628.77|
|full-continuous-reference-v2/landmark_rxr/val_seen/en-US/none|898/793|509|3.819/65.698|17847.639|998024|631.13|
|full-continuous-reference-v2/landmark_rxr/val_unseen/en-IN/guard_then_search|153/153|115|1.275/62.666|2168.046|117688|648.05|
|full-continuous-reference-v2/landmark_rxr/val_unseen/en-IN/none|2881/2707|1860|2.179/65.695|47825.045|2405142|654.79|
|full-continuous-reference-v2/landmark_rxr/val_unseen/en-US/guard_then_search|65/65|52|1.320/62.607|768.059|45368|650.24|
|full-continuous-reference-v2/landmark_rxr/val_unseen/en-US/none|1452/1365|935|2.259/65.010|23935.578|1212578|652.78|
|full-continuous-reference-v1/r2r/val_unseen/en/none|1839/1839|1280|1.702/62.357|32159.281|1664577|652.59|
|full-continuous-reference-v1/rxr/val_unseen/en-US/guard_then_search|1185/1185|642|17.085/65.257|32244.313|2078439|653.66|
|full-continuous-reference-v1/rxr/val_unseen/en-US/none|38/38|12|52.011/63.313|1577.165|69100|650.72|

## 与原模型及历史派生验证的关系

| 独立结果 | 完成与指标 | 已通过 / 限制 |
|---|---|---|
| 原R2R模型 endpoint9 |1839完整；SR65.633496%、SPL57.278175%、nDTW65.369522%、NE3.978647m、OracleSR75.095160% | 原复算/语义审计通过；632普通失败、0运行/非有限。后续5离网使正式登记retracted；不等于原指标计算错误 |
| 原RxR模型 endpoint9 |1223完整；SR67.620605%、SPL55.934696%、nDTW67.661981%、NE4.279348m、OracleSR75.143091% | 原复算/语义审计通过；396普通失败、0运行/非有限。不表示新源几何/tensor独立重算门槛全部满足 |
| 历史endpoint115-v3离线Oracle |3062完整；2225严格通过/837失败、187642动作回放 | 非新模型SR，保留其身份和预算限制 |
| 本轮OracleAdapter |37016完整执行和独立证据核对；分组结果见上文 | 不替换前三组；未全PASS，未完整复现A，未证明全量算法收益或创新 |

Oracle失败不能自动否定旧模型指标；Oracle成功不能冒充模型成绩。可影响旧基线解释的是已经记录的原生离网/源几何或信息流限制，需要同任务/协议直接证据；新的有限搜索失败及更强验收不能直接证明原SR错误。本轮未修改正式模型，也未补齐派生R2R实际模型入口及预处理tensor独立重算，因此新协议没有模型测评准入。

## 可复核入口、身份与交付状态

模块：case1/oracleAdapter；统一代码/公开配置：src/oracle；104项CPU回归本地与服务器通过。既有打包干净导出验证针对较早89测试版本，不能冒充当前104版本的重新安装验收。历史代码、源归档、错误及负结果均保留。

```bash
scripts/with_runtime.sh runtime/awarevln/bin/python -B oracleAdapter/run.py self-test
scripts/with_runtime.sh runtime/awarevln/bin/python -B oracleAdapter/run.py review-full-validation --case-root /data/zy/vln/case1 --input /data/zy/vln/case1/outputs/oracleAdapter/full-continuous-reference-v2 --output /data/zy/vln/case1/outputs/oracleAdapter/NEW-child-review
scripts/with_runtime.sh runtime/awarevln/bin/python -B oracleAdapter/run.py review-full-lineage --case-root /data/zy/vln/case1 --input /data/zy/vln/case1/outputs/oracleAdapter/full-continuous-reference-v2 --manifest /data/zy/vln/case1/outputs/oracleAdapter/full-continuous-reference-v2-review-v1/validation.json --output /data/zy/vln/case1/outputs/oracleAdapter/NEW-lineage-review
```

NEW目录须为未存在的case1输出路径；以上是只读重建审计入口，不启动导航。报告主源：outputs/oracleAdapter/logical-full-review-v1/validation.json。

- 主源SHA256：`b2ab9ef8d9f10269aca2ee64483d344e96fad51179104181750d0ff132154d71`。
- full-continuous-reference-v1 manifest：`1e2d9c826aa71f04ad3d5bd9c123fbae2ce339dffd14047d9a187c9ae534f125`。
- full-continuous-reference-v2 manifest：`04db815594c8e89c095eba6ab7b6b4a1cfa28dbff7a2ccfec35e8523bcb7c31a`。
- all-task-lineage.json：`943b859c8cdc3822485e228ae70d7d30d0550f6e4b989a08219aa55f8e5120fb`。
- all-phase-costs.json：`032693a0fdde67a255b2abe75c6e34618de5b8042628a3927cdbd5751f250793`。
- failures.json：`8cda6180033c3c1a9ae3d4b4e90fb1325dcf44c32ca86fca8b1d04e863282e43`。

**已完成：** 独立可运行模块、成熟来源/代码审查、有限对照与消融、全量来源/适配台账、原37016完整执行/独立回放和跨版本审计、逐任务失败及成本记录。

**未验收：** 全部记录严格可执行、原论文A复现、全量因果四臂收益、所有失败的完全独立物理解释、新派生模型完整信息流、全部环境/发布门槛。有限研究按预设停止条件收敛，不为全绿追加数据/网格/算法版本。当前没有自动发布资格，未创建本轮提交、未push。原有Git工作和远端历史保持。


## 2026-10-20 完整Landmark验证与有限后续阶段

状态：全33954执行、独立回放与分组审查完成；全导航门槛仍未通过。原R2R/RxR封存文件9/9哈希一致，未重测、未修改原标注/场景/体型/动作/位移/回放门槛，未自动commit/push。

| 组别 | 完整任务数 | 严格通过 | 新增严格通过 | 旧严格通过退化 |
|---|---:|---:|---:|---:|
|unchanged|31300|20667|160|0|
|source_bounded_body|2561|213|213|0|
|official_dense_trace|93|31|31|0|

全范围覆盖账目为20911/33954，旧20507全部保留，恢复404、退化0。它不是跨信息条件混算的模型SR。真实动作/独立回放均为2326118；全部held114保留。失败分类：search_budget_exhausted=9563, topology_mapping_error=2670, identity_or_adaptation_missing=741, source_geometry_contact=42, search_frontier_exhausted=27。有限搜索失败不证明物理不可达。42源接触均为初始位置、0动作，失败证书保留。

查询缓存的未改目标/信息组共31300任务，其中两轮均执行运动的27889条，旧教师CPU491824.719153秒，新77084.067233秒，描述性比值6.3804，下降84.33%。160条恢复全部曾在60秒处、未到5000展开时失败。该结果支持计算成本问题的诊断，但历史资源/时间条件不同，不宣称随机对照因果速度界限。新全量9563预算失败中9560已达到5000展开、3达到墙钟上限，因此继续加速本身不能解决主体搜索覆盖问题。

### 固定优先级候选：保留负结果

| 方法 | 严格通过 | 执行与审计进程CPU秒 | 真实动作/回放 |
|---|---:|---:|---:|
|reference_priority1_control|8/16|161.018410|1169/1169|
|reference_priority2_candidate|8/16|149.356281|1288/1288|

两臂恢复0、退化0、8个原成功控制均保留。推广门槛未通过，不继续扫描权重、不启动该候选全量。两臂输入流、原生环境和其余方法参数匹配，重做全部32次执行及逐任务独立回放；不是拼接旧PASS。

调度改进已实际实现：Popen等待及时返回、启动检查0.05秒，身份/permit/超时条件保持。与历史同16任务相比，控制臂动作、位置、朝向、边界、profile/几何/原生环境逐项相同。退出到结算中位延迟由1.505725秒降至0.479822秒；但这16条的执行/审计进程CPU由124.133515增至161.018410秒。调度空等减少与总计算成本不同；历史4并发与本次16并发、运行时间及计数器条件不同，不能据此宣称完整吞吐线性翻倍。控制器上限32，实际受任务数/空闲CPU/内存限制；本开发每臂仅16任务、两臂顺序运行。GPU不用于这一无渲染CPU阶段。

### 四相机视点：查询拒绝原因已经明确

| 场景/节点 | 原查询数 | 最近候选三角面水平距离（米） | 新合法落点 |
|---|---:|---:|---:|
|82sE5b5pLXE/343f046631bb41b1a32a58400bb7df15|10|0.685815|0|
|D7N2EKCX4Sj/6ac9742aa5264ea8a194997121c966c9|5|0.756148|0|
|qoiz87JEwZ2/3d28c5c132ef42808a356be915ede15a|5|0.567396|0|
|cV4RVeZvu5T/acfc7a38863c412bbde815478879ed54|13|1.294316|0|

原33次查询均snapped_is_navigable且吸附残差不超过1.230014e-6米，全部仅因camera_horizontal超过原0.5米范围被拒。6个当前网格三角面的有理数最小距离及支撑平面下界均验证，不是漏掉一个近处的合法浮点投影。结论只覆盖这6个候选三角面；不能推成原始场景物理无路，也不授权扩大位移范围。0导航动作、0映射采用；相机域2米高/0.5米半径不是新机器人参数。

### 保留的失败、更正与资源结算

新优先级v1缺少launchers字段，首个worker在原生启动之前拒绝；全部失败/源码快照保留，v2准备阶段与worker复用同一必需launcher校验后才执行。两臂与父控制器实际为同一PID/start_ticks且共用一份进程CPU硬限制，因此只对重复的同进程控制器预留去重；不同PID或启动时间会被拒绝，旧失败进程4510秒仍单独扣账。
相机v1在原生查询之前因Python3.12/冻结3.10的AST结构不同而拒绝。使用同一3.10解析器确认三个历史函数与迁移函数AST完全相同；显式锁定解析器和指纹后在v2复核，原失败快照保留。没有靠改变几何或验收通过。
本有限阶段保守扣账8521.869204秒，另保留1800秒CPU检查额度，合计低于43200秒阶段上限。历史开发费用含预留和保守窗口，仍不声称全部历史CPU已精确恢复。最终源码CPU回归本地174项通过（Linux专用项skip1），服务器174项全部通过；这些不替代导航验收。

来源回执：
- `outputs/oracleAdapter/global-source-priority-closeout-v1/validation.json`
- `outputs/oracleAdapter/full-cache-unchanged-cohort-performance-v1/validation.json`
- `outputs/oracleAdapter/reference-priority-development-v2/paired-report/validation.json`
- `outputs/oracleAdapter/scheduler-paired-observation-v1/validation.json`
- `outputs/oracleAdapter/camera-surface-rejections-v2/validation.json`

本阶段不再追加权重试验或重复相机域采样。全局目标仍未达成；剩余静态/源几何/有限搜索问题保持在完整分母中。后续必须依据不同且可复核的根因和有限方案推进，不能把运行完成、CPU提速或本阶段收敛替代全局验收。


## 2026-10-20 oLB场景741条完成与资源利用收尾

本轮741条完整真实执行、逐任务独立回放、覆盖审查及与旧结果对照均已结束，控制器3354074/start54653029自然退出，source-freeze CLOSED。实际32个空闲CPU槽位，全部任务结束后CPU回落属于正常终态；没有GPU推理或渲染任务。完成时间2026-10-20 05:24:59+08。没有在后台空闲时自动重复运行。

| 分组 | 任务数 | 旧严格通过 | 新严格通过 | 整路恢复 | 退化 |
|---|---:|---:|---:|---:|---:|
|27个起点候选修改|27|0|0|0|0|
|输入未变控制|714|340|340|0|0|

33707实际动作均有独立回放。27条从原先0动作、首节点前沿耗尽，变为22–41实际动作、8–11次前进；18条停在下一reference index3，9条停在index4，均达到该次搜索5000展开上限。说明候选解除了原始起点的首动作阻塞，但没有解决整条路线，不能登记27条已修好或物理不可达。此结果属于Landmark派生起点适配诊断，不是Oracle算法收益，更不是模型SR。其他714条中的340个旧成功全部保留。全场景401失败包含383搜索预算与18身份/适配缺失。

资源利用问题的处理已经落地：先前16槽与短phase启动/退出等待造成空档，新的owned-Popen退出等待及时返回、启动绑定检查0.05秒，后续上限32空闲槽且不超过总64核。本轮已实际32槽运行，保留PID/start_ticks、permit、实际退出、预算和原生验收条件。旧同16任务对照的退出结算中位1.505725→0.479822秒只证明等待减少；执行/审计CPU124.133515→161.018410秒，因此不声称总体CPU成本减少或吞吐翻倍。本轮保守计费15256.653241秒（约4.238CPUh）不是实测总CPU；保留原20CPUh验证预留和原720CPUh总账约束，无预算重置。

来源：outputs/oracleAdapter/olb-start-repair-scene741-v1；manifest edbf9363f9c21c5382b920a7c0d0c2590541c957a56e42f52cf4fbf3c36f52dd，comparison 994a297018ccce16108128c9d2f4dd96f75472041d1282b3c1501110264568bb。只读收尾及27条进展分类：outputs/oracleAdapter/olb-scene741-closeout-v1/validation.json、changed27.json。后者记录实际动作、下一参考序号和末次搜索诊断，未执行新导航。

全33954此前严格通过20911的全量结果保持独立，不能拼接本轮场景结果冒充新全量；全局连通与90%目标仍未达到。R2R/RxR及原始场景/标注/物理门槛封存保持，未commit/push。当前候选不进入全量推广，不继续盲调起点；后续研究须重新绑定具体根因与有限预算。本轮控制器监控在收尾后删除，避免持续监控已终态任务。


## 2026-10-20 搜索空间诊断完成：大量近重复姿态占据有限展开

固定8个既有Landmark train失败均完成末次搜索诊断，全部复现原failure、5000展开与15000 transition调用；不是新路线评估或恢复。真实原生预演共120000次、搜索展开40000次，全部结束、source-freeze CLOSED且controller/worker身份检查无存活者。使用8空闲CPU并发，无GPU。worker报告区间CPU合计55.628943秒，不含启动和最终清理，仍保留完整900CPU秒预留扣账。192CPU测试通过（Windows专用Linux集成项skip1；服务器全通过）。

|任务|展开数|精确位置数|仅报告用1mm/0.001度分桶数|生成标签中相反转向后同位置但四元数不同的对数|
|---|---:|---:|---:|---:|
|train:22066|5000|42|358|2430|
|train:85886|5000|30|336|2164|
|train:113417|5000|132|329|2442|
|train:9047|5000|163|771|2138|
|train:74966|5000|16|126|2290|
|train:39833|5000|23|234|2210|
|train:7808|5000|54|387|2102|
|train:101607|5000|118|310|2688|

由独立脚本直接读取全部terminal-search节点、parent/action/depth、展开序号、heuristic，重算统计及哈希，不复用诊断summarize函数。8条均没有生成进入原目标区域的候选，因此本组不能归因“找到目标却没弹出”。每条5000展开只有16–163精确位置，仍有4974–5000精确位姿；生成节点中分别发现2102–2688个相反转向后位置完全相同而四元数位不同的标签。它说明无损浮点状态搜索确实被大量近重复旋转状态占据；仍不能证明这些状态未来后继完全等价，更不能直接删节点或恢复旧取整合并。毫米分桶仅作观察，不参与规划和验收。

原来的终态仅有总计数，本次新增terminal audit_sink在返回后保存内部状态，默认关闭；不改变队列排序、动作代价、精确key、Pareto支配或实际门槛。CPU成功/失败图对照保持结果与调用数；原生8条复现结果支持此诊断的相关性，但没有旧搜索树，所以不声称全树逐字节同一，也不将8例外推全部9563预算失败。

证据：outputs/oracleAdapter/search-space-probe-v1/validation.json SHA3ba1104851179f44a1eff3f66fb6780ca94069586e906389356181eadc937eac；manifest SHA2c9c3709ac18734ea050f219520af4cee2e07b6120bb0260282894af1e36a2cf；独立原始节点复算outputs/oracleAdapter/search-space-independent-review-v1/validation.json。完整节点和失败证据保留，无新完整导航PASS。

### 成熟方法核对及最小后续方向

AnySearch发现论文后，DOI正文抽取失败，随后通过作者主页核对arXiv全文与作者代码。论文[Improved Soft Duplicate Detection](https://arxiv.org/html/2109.12427)通过软重复性调整优先级而不硬删近似状态，并用后继子树重叠考虑动力学；它的保证依赖其搜索/启发式前提，不能搬到当前有界预算及非可采纳启发式上。作者[3D代码](https://github.com/Nader-Merai/cspace3d_subtree_overlap/tree/4a788ce7861f4137df114b829567b50e7c113ae1)已冻结commit4a788ce7861f4137df114b829567b50e7c113ae1，读取GetGoalHeuristic、NewRatioCalc和ARA调度；采用二维地图与mprim，不直接适配Habitat楼梯/投影/源扫掠。仓库无顶层license，araplanner.cpp有BSD声明，环境文件没有同样的明确声明；目前只封存阅读，不复制进活动实现或安装依赖。

下一步最小假设是保留精确状态与原合法性检查，仅降低已密集探索的近重复状态的排队优先级，并保留可探索分支。不能把未经证明的近似距离当等价关系；必须先固定一个候选和预算，与原方法及成功控制做同任务对照。本文的soft duplicate思想属于已有工作，不宣称创新。当前还未实现该算法候选，未启动新完整导航；不得根据本诊断宣称90%或全局贯通。

R2R/RxR封存、Landmark33954/held114完整分母及原始数据/场景/体型/动作/源接触/回放标准保持。当前全量20911/33954与本诊断分开；全局目标仍未完成，未commit/push。


## 2026-10-20 固定soft-priority完整对照终态：不推广

全部16任务×2臂已完成真实执行、独立回放、完整覆盖与配对审查。候选恢复0、退化0；8个旧成功控制均保留，8个原预算失败均仍失败。逐项核验32份实际结果：两臂任务字节流一致，动作/位置/朝向/参考边界/profile/原生几何/环境全部相同。候选所有搜索实际记录了固定soft配置与非零重复标签计数，排除“标签叫候选但没有调用实现”。源代码与实际worker绑定仍由原冻结manifest及逐任务回执校验。

|方法|严格通过|真实动作/独立回放|执行及审计进程CPU秒|成功控制的搜索展开|
|---|---:|---:|---:|---:|
|原精确键priority1|8/16|1169/1169|135.879102|2746|
|固定soft-priority|8/16|1169/1169|207.065351|1382|

7个成功控制实际调用搜索，1个未调用。成功控制展开下降49.67%，说明近重复优先级影响了搜索成本；总进程CPU反而增加约52.39%，未提高路线覆盖，不能称整体性能改善。CPU数值为实际观察，控制臂因预留错误分为首次16槽与续作3槽，候选全为3槽，且不是随机计时试验，因此不把CPU差异解释为纯算法因果效应。展开计数和完全相同实际轨迹提供更直接的可比证据。

### 调度错误、续作与最小基础设施修复

首轮控制器3379656/start54828981以3CPUh预算开放16槽，忽略每phase905秒预留及3605秒控制器预留，导致8个未启动任务停止。错误与STOPPED状态保留；8个已完成结果未重跑。续作控制器3382460/start54848243限制3核，保留原源码/manifest/物理预算，只执行未启动条目及候选；两控制器自然退出。结果看reviewed-continuation-validation.json，不能用原STOPPED标签遮盖后续完整回执，也不删除原错误。原Landlock拒绝运行进程写docs的事件保留，文档经正常维护入口更新，保护未放宽。

实验结束后才修复未来调度器：初始并发同时受剩余CPU预算可容纳的完整phase预留数约束，已收费的存活任务保留，不能通过停止健康任务回收额度。实际3h/905s/3605s反例应最多7新槽，续作已有收费后最多3；没有预算时不启动新worker。200CPU回归本地通过（Linux项skip1）、服务器全通过。本补丁未用于已经完成的实验，不为验收调度重跑导航。

完整阶段保守收费7576.517285秒，包含首个失败控制器费用，另保留3605秒准备/CPU检查额度，共11181.517285<21600秒。没有把控制器预留当实测CPU，未重置24/720CPUh上限。关闭的源码快照与失败证据保持。

依据固定停止条件，该候选不推广、不开展全33954、不扫描权重/分桶、不加搜索预算。此次否定的是这一具体候选的整体改进价值；不能因此否定所有soft duplicate方法，也不能把有限失败认定物理无路。已有公开工作不构成本项目创新证明。

来源：outputs/oracleAdapter/soft-priority-development-v1，manifest SHA9f30679fadd9545a4956efd91c6cf42e0aec42badaff2463048de46d11fdba12；paired-report SHAfa65fe4fc08c86f8b90c40eaa8f54865131faa66fa0d3abddf347683dd63fefc；独立额外核对outputs/oracleAdapter/soft-priority-closeout-v1/validation.json。全局33954既有20911通过结果保持独立，没有新全量成绩。R2R/RxR、原始数据与场景保持封存。研究目标尚未达到，无发布资格，未commit/push。


## 2026-10-20 Landmark209条源接触阻塞：完整归因与原生高度查询终态

本轮为有据诊断进展，不是新增恢复。209条任务的原生点/参考连接可用，但源端点门槛未过；其中42初态接触、167后续搜索预算失败。42初态均与输入完全一致且静态已记录接触，因此不是初始化浮点误差新引入。旧全源约束候选记录显示209条各有1个视点无合法候选，不是候选都存在但无共同分量。它们集中7原视点，实际包含61个不同派生坐标，全部209对应关系已核对，不能拿7样例替代61坐标或209任务。

|场景|影响任务|独特接触位置|接触三角面倾角(度)|中心投影在三角形内的位置数|
|---|---:|---:|---:|---:|
|HxpKQynjfin|15|1|25.753–25.753|0|
|X7HyMhZNoso|3|1|1.204–1.204|0|
|kEZ7cmS4wCh|59|15|0.467–2.881|11|
|pRbA3pwrgk9|68|18|0.503–1.099|2|
|rPc6DW4iMge|22|6|1.211–1.849|0|
|uNb9QFRL6hY|27|16|0.391–0.610|7|
|ur6pFq6Qu1A|15|4|0.624–1.518|2|

读取实际原生加载器几何导出的相应三角面，重新计算法向、准确有理数平面高度及重心坐标，并与每条原preflight接触证书绑定。kEZ内部投影位置的面高于基点约4.98–6.99cm，uNb约7.46–8.88cm，ur6约8.66–9.08cm，pRb约4.09–4.41mm。其余中心投影在三角形外的数值不能当中心正上方的实体面，只能结合已有半径内接触证书解释。多数近水平面仍只是几何描述，未取得语义标签或合法支撑证明，不将它们自动排除出碰撞检查。

固定61点原生高度查询已完成：183次try_step/snap/path查询，0执行动作、0目标修改。每个点第一次try_step(p,p)就精确返回原坐标，原snap固定/navigable/分量检查保持；61点float与rational源身体接触均仍存在，0合格新落点、0整路恢复。由此排除在本组靠重复零位移投影消除高度差的方案；不再增加迭代数或凭经验抬高坐标。单核进程CPU1.776383秒，保留600秒完整预留；此前几何7点/61点各120秒预留仍保留，未重置开发/全量预算。

诊断更正保留：初版把新增extra seed的0.350001m水平界也用于原样返回的rank0当前点，导致额外10项bound拒绝。已有规则对rank0只要求原sphere/camera界；只读复算更正为0项bound拒绝，但全部61源接触仍失败，0点通过结论不变。旧validation不覆盖，bound-interpretation.json记录原SHA、原因和更正；未重新运行原生查询、未放宽原规则。对同一视点默认同一派生坐标的早期失败检查及其错误原因说明，也已在coverage-comment-correction.json保留修正。当前207CPU回归服务器全部通过，本地Linux项skip1。

### 原始来源与下一步边界

本次AnySearch代码检索暂不可用，保留失败回执，直接核查官方仓库issue。维护者在[issue12](https://github.com/jacobkrantz/VLN-CE/issues/12#issuecomment-790086572)解释GT是逐参考节点运行Habitat follower所得轨迹；在[issue13](https://github.com/jacobkrantz/VLN-CE/issues/13#issuecomment-809599787)确认Guide instruction_id沿用原RxR、Follower用demonstration_id，并说明转换时调整过部分节点坐标。这支持稳定身份匹配与区分原pose/转换位置；仍不能解释8034条具体排除原因，未将它们标为已证明的官方过滤。issue22目前没有维护者回复，问题内容不能当GT身份映射答案。

当前profile中5场景原build_settings为null，不猜旧参数；只有pRb/Hxp保留部分明确构建参数。源PathFinder.cpp显示detailSampleMaxError按cellHeight缩放，但参考源码不替代当前二进制构建控制。下一步只允许先核对pRb/Hxp完整实际构建回执及未改参数的原生字节控制，再依据本次高度证据决定是否建立一个有限单因素detail候选。控制不匹配则停止该构建分支，不盲扫cell/region/climb，不修改原几何或验证器；任何候选须全受影响场景非退化、真实运动及独立回放才能算恢复。此候选尚未构建或运行。

证据：outputs/oracleAdapter/endpoint-mapping209-attribution-v1（209逐条、61坐标覆盖及更正），contact-surface209-v1（原生三角面与209来源绑定），native-height61-v1（原生查询与bound解释更正）。实现/配置在oracleAdapter/src/oracle/verification及configs/experiments。全Landmark33954及held114、封存R2R/RxR和原始资产保持；全局20911/33954未因此增加。没有自动commit/push，整体目标仍未验收。


## 2026-10-20 10:14 pRb完整660验收结果及退化根因

完整660任务及独立审计于新加坡时间2026-10-20 10:14:43结束；controller9504/start123476已退出、source-freeze CLOSED。以review-complete及其哈希绑定的完整审计为终态依据，state.json旧子阶段标签不覆盖终态。当前候选不通过推广：严格98通过，旧69保留67，新增31，退化2（train:23751/23752），失败562，未采纳profile，未push。全部任务保留，未拼接旧PASS。

|结果项|数量/证据|
|---|---|
|新严格通过|98/660（14.8485%）|
|旧严格通过|69/660；保留67、退化2|
|新增恢复|31；其中14目标未改，17属于源约束点修复组|
|剩余失败|556搜索展开上限、2首节点前沿耗尽、3初态源接触、1完成路线但源端点门槛失败|
|实际动作/独立回放|23290/23290；最大位置误差0、最大朝向误差0|
|执行与审计基础设施异常|0；全部1320阶段COMPLETE|
|完整分母|660；原33954/held114及其他场景未删改|

556搜索预算失败的末次搜索全部达到5000展开，没有墙钟超时作为本轮末次停止原因。其中11条还有独立的源端点门槛缺陷，不能全归给搜索器；其余有限失败仍不证明物理不可达。2条前沿失败train:77588/77589均首节点展开1、3动作探测无合法后继，0实际动作。3条初态源接触train:100582/101064/101065也为0动作；1条train:99259实际走完有序路线（100动作），但源参考端点仍有接触，因此严格结果保留失败。记录物理告警仅3个index0初态接触；通过路线及实际执行动作没有独立回放物理告警。

### 实际成本与预算分开

执行worker实测CPU6999.224806秒，独立审计worker实测1727.667851秒，合计8726.892657秒（约2.424CPUh）。控制器到完整审计回执墙钟325.923637秒（约5分26秒），32空闲CPU槽，无GPU。控制器自身实测CPU未记录，不能补成0；包含其3605秒预留及已观测清理上界的保守总计费12949.098602秒（约3.597CPUh），低于20CPUh运行预留。准备/构建/首次失败准备及后续诊断费用另保留，不冒充这8726秒覆盖所有研究历史。执行CPU P50/P95为10.401552/19.719167秒，审计为2.509687/3.506852秒；不同阶段分位数不相加为任务总分位数。

### 两条退化已查到实际运动高度响应

两任务的全部目标/初始朝向/信息条件未改；旧网格只需5/7次搜索展开得到2动作计划，新网格5000展开失败。进一步固定使用各自旧成功动作序列，在新profile真实执行并以另一个进程、rational source判定独立回放，保持原门槛/顺序/终止条件，不重置姿态。train:23751在第17个前进动作、23752在第15个前进动作发生源接触；两算术路线及实际回放位置/朝向误差0，均不能构成新profile成功路线证据。

与旧原始轨迹比对，水平前缀差为0；失败落点的新y分别比旧y低0.016739666m、0.015852690m。旧同一步源扫掠无接触，新落点本身有接触，并非只有直线插值告警；同一源三角面69465、同一几何SHA6cb538d0c7110267e6a6c7c3109ceb52d2fafc982dc86da8f09cbdc3774ba005，倾角约20.407度，接触位于身体底部附近。现已证明全场景收紧detail误差会在此局部降低原可通过路径的高度响应；仍不能证明没有其他合法绕行路线。不能通过加预算、手工回填旧PASS或忽略底部接触把当前profile推广。

诊断为2固定任务×2独立进程，32个尝试动作及32个独立回放尝试动作，包含各自最后的失败动作（不得当作全部合法动作）。四进程报告CPU合计9.925885秒，保留300秒预留；没有改660结果。Oracle输入明确增加了历史同任务动作序列，仅作反事实根因诊断，不当统一Oracle算法成绩。浮点/有理数交叉核查共享原生引擎和几何模型，未宣称数学完备独立性。

### 后续收敛方向及封存

当前全局detail0.1候选未通过零退化门槛，不采用，不继续全局参数扫描。下一步先核对coarse拓扑与detail数据对应关系，判断是否存在由源几何依据确定的局部高度修复，能改善已确认的错误区域而保留原安全通道；未经完整构造/静态/真实动作/回放验证，不做网格拼接、统一抬高或更换验收定义。也不能将反事实诊断结果加入当前31恢复列表。

原R2R/RxR及端点研究9个封存身份文件再次逐项SHA256核验一致，本轮Landmark发现不改变它们的原模型指标及已披露限制。全Landmark既有20911/33954结果仍独立，不能将pRb净增29直接写成新完整全量成绩。原660数据/失败/日志保持，候选资产未发布。

正式收尾证据：outputs/oracleAdapter/prb660-closeout-v1/validation.json、task-ledger660.json、recovered31.csv、regressed2.csv、failures562.csv、baseline-seal-check.json。完整run manifest SHA2eded760227035839f589bb36e10a0b92064b966fb57962affe552f5b6390024；scene comparison SHA2b9694e3b174d4cadba3a9c0938ecffc2c3c88cfa26e28efdb51bd09f97dd1db。反事实证据：outputs/oracleAdapter/prb-oldplan-counterfactual-v1/validation.json、contact-interpretation.json，manifest SHAeb766ed5d1a19d847191bc2a52703a301d6d7533097a71d85c0318c0098eb8fd。当前217CPU回归服务器全通过，本地Linux专用项skip1。
