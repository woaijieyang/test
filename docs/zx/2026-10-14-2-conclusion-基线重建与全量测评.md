# AwareVLN基线重建与全量测评结论

## 2026-10-20 阶段发布与 pRb 候选采纳决定

记录时间：2026-10-20T11:22:40.210785+08:00。用户明确要求“先push到FirstPaper-VLN，后续Landmark继续修复”，随后对98/660、31新增、2退化的候选明确授权“可以先采纳”。因此本次发布范围更新为**阶段源码、配置、既有结果及完整限制的可追溯快照**；不再以全部导航PASS作为本次人工授权发布的前提。这不修改或伪造原有科学验收回执。

pRb detail0.1候选现为后续Landmark研究当前采纳方案，带已知退化；旧“未采纳”段落是该授权前的历史判断。全660仍为98严格通过/562未通过，旧69保留67、新增31、退化train:23751/23752两条；零退化门槛仍失败。全部33954及held114保留，不拼接旧PASS，不将局部净增29冒充新全量成绩。选择依据是已完成的完整场景对照及用户接受已披露退化，不是全部验收通过。

公开采纳描述为`oracleAdapter/src/oracle/configs/experiments/prb_detail_adoption_20261020.json`，绑定profile SHA `b482e820b915fef455cf8ae450cbab3f55d0e8d9c7b1f7f3da046df8c41e3942` 与原660 manifest。该文件是决策与后续启动绑定依据，不自动覆写任何运行配置；后续新运行需显式绑定同一profile及对应任务映射、冻结新manifest并真实执行/回放。R2R/RxR、旧模型和全局既有结果继续封存；未改原数据、场景几何、体型、动作或碰撞/回放门槛。

详细三组结果、成本、失败解释、证据路径与复现边界见[阶段发布说明](../PUBLICATION_SNAPSHOT.md)。本段记录的是发布授权和阶段采纳，不代表原模型新成绩、Oracle达到90%、Landmark完全连通、环境整体无缺陷或已成立算法创新。提交信息为`awareVLN-baseline-construct`，目标main保留既有历史、不强推。提交本身无法包含自己的SHA；实际发布commit/tree及远端核验回执保存在`outputs/publication/`，以远端核验成功才报告push完成。


## 2026-10-19 295条退化的只读根因分析与R2R/RxR封存

本次按用户要求只读分析，未执行任何新导航、搜索、模拟器实验或算法/数据修改。完整报告：[295条退化分析](../../oracleAdapter/docs/REGRESSION295_ANALYSIS.md)；逐条CSV/JSON及AnySearch原始检索证据：outputs/oracleAdapter/regression295-readonly-20261019-v1。

本轮1934/3062低于历史2225/3062，来自295旧通过/新失败与4新通过/旧失败。295输入、有序目标、初态、profile/原生几何和原审计口径核对一致，全部本轮失败为有限搜索预算。148条未达5000展开即在60.000199–60.053109秒结束（展开902–4985，中位1607.5）；147条达到5000展开和15000调用。历史实际搜索/launcher未设相同墙钟截断，不能称预算等价。整任务180秒、64搜索、动作上限不是这些记录观测到的触发。

明确控制缺陷：官方前缀仅检查动作合法，缺当前reference进度契约。221条RxR有前缀，其中219条与旧动作分叉，171条耗尽全前缀才回退；切换时194条距当前参考点>3m，最大26.329279m，201条在同一参考段搜索失败。例2442/21574在第1/12段执行214动作后离目标26.33m，曾接近0.288m但未满足.25m；不能通过放宽半径解决。76条当前动作则完整等于旧成功前缀，共同前缀位置误差0，不能归咎目标/场景变更。

明确性能差异：旧geometry空间块和精确起终点扫掠缓存，本轮SourceScene.contact每次重筛全场景三角面。它是新增60秒上限下的合理性能根因，未profile不能给贡献比例。旧厘米/角度+前进bit键与新float.hex/Pareto标签改变搜索图；已知旧键会错误合并，不能直接回退。缺旧/新完整展开树日志，不能逐条断言状态膨胀是全部147节点失败的唯一原因。

AnySearch核查Habitat官方文档及issue1689、ARA*/SBPL固定提交4d654845、MHA*、LazySP、E-Graphs，重读既有冻结Sim2Sim/ETPNav代码。成熟工作支持有界目标局部控制、先可行解搜索、昂贵边缓存/延迟检查及身份绑定路线先验，但没有可直接套用的90%保证。PDF抽取失败和无关检索已保留，不作为有效证据。

建议顺序（未实施）：①官方前缀按当前参考段对齐/有界进度回退，保持所有目标与顺序；②恢复保守空间索引与精确查询缓存，先证明判定等价；③保留无损安全分支，调查近等价标签和成熟anytime/走廊引导，不恢复错误硬合并；④明确唯一预算停止原因、碰撞CPU和同预算对照。不能以增加预算、复制旧PASS、改数据或放宽门槛称算法收益。

90%：3062需2756通过；即使假设295全恢复且不退化，也只2229，还差527。Landmark33954中3411静态失败，固定映射下最高30543（89.9541%）；合并source endpoint gate后6274条被阻挡，固定条件下最高27680（81.5221%）。达到90%至少需另解除2879条阻挡且其他路线也通过。因此Landmark适配与Oracle优化必须分开推进。此为当前程序门槛上界，不是永久物理无解；held114和完整分母继续保留。本轮没有开始Landmark修改/实验。

用户要求封存R2R/RxR：现有原模型/派生验证代码、输入与结果保持，不再自动更改或重测；baseline hash索引已核实，逻辑封存不移动目录/改权限。原模型完成不代表派生Oracle全修好，R2R5离网/retracted、旧2225/837和新1934/1128限制均保留。后续Landmark优化不得热改或覆盖这些结果。未commit/push。


## 2026-10-19T15:16:10.105230+08:00 OracleAdapter有限研究最终交付

**本轮研究执行与独立审计已结束；全部导航门槛未通过，未获得发布资格，不自动继续实验或push。**

完整研究报告：[OracleAdapter最终结果](../../oracleAdapter/docs/FINAL_RESULTS.md)。原始完整账目：outputs/oracleAdapter/logical-full-review-v1/validation.json（SHA256 b2ab9ef8d9f10269aca2ee64483d344e96fad51179104181750d0ff132154d71）。

原37016任务由v1封存5144和v2续跑31872恰好组成，原R2R1839/RxR1223/Landmark33954全部保留，无遗漏/重复，普通失败不择优重跑；明确保留两个manifest和实际源码身份。v2于2026-10-19T06:57:15Z完成，控制器自然退出、source-freeze CLOSED。收尾104CPU测试通过，子31872独立review和原37016lineage审计均通过证据一致性；2544634实际动作均有独立原生回放。审计一致不等于全部导航通过或物理判定数学独立。

| 结果组 | 完整结果 | 失败、影响与边界 |
|---|---|---|
| 原R2R模型 |1839完整；SR65.633496%、SPL57.278175%、nDTW65.369522%、NE3.978647m、OracleSR75.095160% |632普通失败、0运行/非有限；原复算/语义审计通过；后续5离网使登记retracted。新Oracle失败不证明原指标算错 |
| 原RxR模型 |1223完整；SR67.620605%、SPL55.934696%、nDTW67.661981%、NE4.279348m、OracleSR75.143091% |396普通失败、0运行/非有限；原复算/语义审计通过。新源几何及tensor等门槛不能据此写成全PASS |
| 历史endpoint115-v3 |3062完整，2225严格通过/837有限搜索失败 |187642动作回放；历史Oracle，非模型SR，不混算 |
| 本轮endpoint115 Oracle |R2R1280/1839、RxR654/1223严格通过 |1104预算+24前沿失败；244516动作；295仅旧版通过、4仅本轮通过，历史计算条件不完整，不当同预算因果收益 |
| 本轮Landmark连续B |20507/33954严格通过 |9086预算、719初始源几何接触、231完整路线但必需端点源接触、2670拓扑映射、741缺连续适配。held114全部在741中保留 |

全量Landmark各split：train15805通过/26464，val_seen1740/2939，val_unseen2962/4551；完整源记录未删。官方动作兼容分支2281/2786、无兼容建议分支18226/31168，任务/信息条件不同，不能直接比较算法收益。源几何initial_source_contact是执行前失败；有限预算失败不等于物理无路，也不能把每条都叫5000节点耗尽，因为唯一预算触发未单独捕获。

适配独立结论：461缺发布图ID全部在原图同名included，365有CE序列来源/96无；8034全部匹配原Guide身份/路径但仍缺CE，转换排除原因未知。pRb发布edge51不是原图直接边，原图有三跳路径但未偷换任务。train43144源子段间连接已显式保留，本次524动作真实执行/524回放严格通过；缺原适配同预算运动对照，不能将其当独立算法增益。逐项台账见最终报告对应路径。原论文A只完成来源与就绪审查，evaluator细节及77子段差异仍未解决，未复现A成绩；不得用B代替A。

开发效果：无损状态键复核25个原生混叠反例，但12任务成对0恢复/0退化且CPU增加；133任务固定组合90对受保护建议51，39恢复/0退化同时CPU445.828→2530.914秒。纯搜索54因无官方动作特权单列。无已成立算法创新；未完成全量四臂因果研究，不声称泛化。

完整执行/逐条审计进程CPU239.845899h，teacher CPU185.407871h，保守计费274.021687h<720h；后两者不是同一成本。分组P50/P95、展开、碰撞查询、RSS、回退和失败成本详见报告/JSON。未使用GPU，最多16启动时空闲CPU槽；未停止外部任务。原始标注、场景、模型和共享环境未改。

尚未验收：全记录严格可执行、所有关键失败的完全独立物理解释、原论文A、新派生模型实际入口与tensor独立重算、全部环境/发布门槛。有限研究按停止条件收敛，不为全PASS追加数据/网格/算法版本。Git HEAD仍5cdfed986a8b692263ac679e060555d9e26febaa，已有暂存工作保持；本轮未commit、未push。后台已终态，最终文档和本地副本核对后删除30分钟监控。


## 收尾前过程记录（保留原文）

状态：原R2R1839和原RxR1223完整模型测评及原复算/语义审计均已完成。R2R后续5处离网与retracted保持；历史派生v3为2225通过/837有限搜索失败。Oracle/Landmark研究进行中，全部验收未过、未发布。详见同一专项conclusion当前快照；历史记录保留。

## 2026-10-14 归档与来源准备
本地7903文件、3408850931字节移动前后SHA-256一致。归档backup/pre-rebuild-20261014-baseline，回执.rebuild/archive-20261014-baseline-verified.json。
Windows首次清点因长路径失败，使用扩展路径修复，相关文件没有遗漏。停止了核实为当前case1专属的CodeGraph服务以避免归档期间写索引；外部研究进程未停止。
服务器归档仍在清点/核验，唯一权威状态为.rebuild/archive-execution.log及最终verified回执，不能提前写PASS。重复规模扫描已停止，归档单一扫描保留。
官方源码暂存.rebuild/official-source，HEAD 8f14eb8450cdd14ff4e3ba1ea04824255121e6be；该参考树CodeGraph 209文件、4316节点、8845边。目录组织和文档材料暂存在.rebuild，尚未切换为活动部署。

## 归档启动时的验收状态（历史记录）
本地归档PASS。服务器归档进行中。独立环境、保护、网格修复、真实模型链路、正式全量、结果审计、发布均未通过。后续按实际证据更新，不用文件存在代替完成。

## 2026-10-15 暂存实现与分层验证

服务器清点完成：8,453,376个普通文件、2,388,743,483,479字节；此处是清点规模，不是归档完成声明。当前仍执行移动前全量哈希，最终以根控制目录中的正式verified回执为准。

新代码、规则和指南暂存在.rebuild/payload，未切换活动部署。已实现保护启动器、链接构建、源码导入与补丁、网格/运动诊断入口、任务冻结与调度、输入/输出/动作记录、原子结果及恢复、独立审计和统一结果登记。实际安装与GPU集成尚待后续门槛。

### 已执行检查与证据

| 检查 | 实际结果 | 范围和证据 |
|---|---|---|
| 原生episode reset片段 | 原代码因队列残留失败，补丁后通过 | CPU真实源码片段；.rebuild/reset-validation/before.log与after.log |
| 归档到源码导入的完整测试流程 | 3个合成文件及1个链接实际归档核验，再导入219文件、应用3项补丁、24项CPU测试零跳过通过 | .rebuild/archive-install-roundtrip/case1/.rebuild/；不是2.39TB正式归档或模型结果 |
| 运行启动器权限 | runtime/results/config三种模式通过，Landlock ABI4 | .rebuild/payload/outputs/verification/protection-modes-01.json；只在自有夹具试写 |
| 构建保护 | 允许自有构建输出，拒绝修改夹具backup；GPU不可见 | .rebuild/build-protection-receipt.json；未安装环境、未运行GPU |
| Git忽略边界 | 14类应忽略、10类应跟踪用例通过 | 隔离临时Git仓库；源码/结果索引不被误忽略 |
| 来源一致性 | 219个导入文件及3个补丁的实际哈希与清单一致 | roundtrip测试目录outputs/verification/provenance-01.json |
| EGL设备映射 | CUDA_VISIBLE_DEVICES=7时，逻辑CUDA设备0仅对应物理EGL设备7 | 只查询设备属性，没有创建渲染上下文；新环境仍需真实渲染测试 |

这些检查存在重叠，不累加为独立模型任务数量，也不等于导航通过。

### 已明确的输入与记录约定

现有官方权重配置为八帧、Llama语言模型、视觉塔和投影器。这里只核对了配置，尚未完成新环境中的权重加载或生成。

RxR原生NDTW读取guide与follower两份GT。只读检查得到11,006与10,847个键，交集为0；两份均纳入冻结输入，正式任务范围仍为guide/en-US的1,223条。

R2R顺序测试必须让正常任务A先于问题场景任务B，并处于同一逻辑分片；当前原始清单按预定规则得到A=4、B=28，分片0。B随后单独在同一物理GPU执行，审计实际序号从大于1变为1。RxR诊断是原33条加两条其他场景任务。任务选择先于模型结果，不按成功率挑选。

启动配置与trainer最终配置分开保存；生成前保存实际输入，输出token重新解码核验；原子result提交绑定轨迹和实际配置。恢复完整闭合轨迹时保留原失败结果，不重复模型推理。正式Full仍需要独立指标复算和所有准入条件。

### 实施纠正

Windows暂存文本统一为LF，并增加.gitattributes，防止跨平台传输及Git换行规范化造成源码字节身份变化。格式校验改为对实际落盘字节取SHA，AST等价性单独验证；此修正仅涉及新暂存文件的格式记录，不影响两端历史归档内容，也没有已有正式运行需要更正。

当前没有本次模型导航成绩、没有正式结果登记、没有提交或推送。下一步仍是完成正式远端归档，再按实际错误逐项完成独立环境与真实链路。


## 2026-10-15T07:31:08.961532+08:00 归档移动完成，进入实际部署

本节更新前文阶段状态。48项历史根内容已移动至backup/pre-rebuild-20261014-baseline；全部8,453,376普通文件的移动前SHA、前置元数据及移动后路径/大小/链接核验完成。按用户最新指示停止剩余移动后复算：已核验6,356,992文件、1,995,491,121,093字节；posthash_complete=false。回执.rebuild/archive-20261014-baseline-accepted.json，清单SHA256为9b1f8ec808c727c03b5e05933af6c91d4ec0aaed2c026ed883d56b2022e1b290。两个本任务持有的扫描/等待进程已按PID及starttime核实后停止，未停止外部任务。

219文件导入到活动源码/配置，3个上游文件补丁已应用，独立case1 Git main初始化（尚未提交）。实际活动树24项CPU回归零失败/零跳过通过：outputs/verification/cpu-import.json。来源、14项忽略/10项跟踪及18项本地文档链接检查通过。独立环境构建日志outputs/setup/environment-build-01.log；环境尚未完成。micromamba默认尝试写入用户主目录被Landlock拦截，初始conda事务仍完成；将显式固定缓存/注册行为，不能将该日志理解为全局写入成功。

## 2026-10-15T07:35:10.487640+08:00 活动数据接入与Git父提交

setup_data_links.py在活动目录连续执行两次通过，六个入口幂等。outputs/preflight/data.json记录R2R1839、RxR en-US1223、11场景及完整身份。outputs/verification/protection-installed-01.json记录三种实际启动器权限模式通过；这是数据/保护证据，不是导航结果。

首次HTTPS Git中转拉取遇到early EOF。将中转响应在发送HTTP头之前完整接收并标明长度，拉取只省略暂不需要的旧blob、不截断提交历史，复试成功。原main为5cdfed986a8b692263ac679e060555d9e26febaa，保存refs/archive/pre-awarevln-baseline，当前分支父身份保持该提交。未覆盖活动文件，没有提交/推送。证据outputs/publication/prior-main.json；认证仅通过本机内存通路。

## 2026-10-15 独立环境的实际兼容性修正

- 构建01：完成Python3.10独立环境、Torch2.3、Transformers4.37.2、FlashAttention2.5.8及导航依赖安装；原生配置因缺OpenGL开发文件失败。仅在runtime内补齐libgl/libglx/libopengl/libegl开发包，CMake随后通过。日志outputs/setup/environment-build-01.log及02.log。
- Gym0.17.3需要cloudpickle<1.7，最新joblib1.6要求>=3。核对两者发行元数据后固定joblib1.5.2（没有cloudpickle依赖），pip check通过。模型和动作协议未改变。
- Decord官方0.6.0发行wheel文件名宣称py3-none，内部却为cp36-cp36m，另有top_level.txt的过期RECORD哈希。官方整体wheel SHA51997f20be8958e23b7c4061ba45d0efcd86bffd5fe81c695d0befee0d442976被冻结。repair_decord_wheel.py只重建WHEEL/RECORD，校验其他全部成员字节一致；没有删除或绕过pip check。outputs/setup/decord-wheel-repair.json记录身份。CPython3.10实际生成/读取16帧视频通过，最大压缩像素均值差1，证据decord-decode-test.json。
- 构建02：旧pybind11 attr.h缺少cstdint导致std::uint16_t未声明。独立头文件探针修改前失败、补include后通过；patches/native-pybind11-cstdint.patch及configs/locks/native-patches.json记录唯一变化，outputs/setup/pybind-header-before.log和after.log保存复验。构建03正在继续。没有放宽编译错误检查。

上述为依赖与构建证据，尚不证明模拟器渲染、模型生成或导航成绩。失败构建日志均保留，未重写为成功。

## 2026-10-15 08:03 SGT 原生环境、数据和原网格验收

独立Habitat-Sim/绑定/Habitat-Lab构建完成。实际导入20个模块、4,981个关键文件，环境摘要7870af776af8f448d66e206c46e1ff717dfc2972b8b94ceafc827de8cdb10797；输出configs/locks/environment-summary.json与outputs/setup/runtime-files.json。第一次导入因Habitat核心安装未含baselines所需lmdb而失败，补齐原生IL/DDP依赖后通过；没有切换至旧环境。215项Python发行依赖锁已生成，pip check通过。

全部16个官方模型文件与公开冻结源一致，模型摘要f467265fc17f68cbc256ef4a65b8d196e8317a316cb858102d72095f2cdf8df5；outputs/preflight/model.json。这仅是权重身份，尚未实际加载GPU模型。

原网格全量原生PathFinder检查完成：3,062条中恰有33条起终点及参考轨迹连通问题，均为oLBMNvg9in8的RxR。该场景覆盖115条RxR和177条R2R。outputs/navmesh/original.json同时保存原端点、参考轨迹异常索引、原生岛半径及按实际可达性分类的端点连通分量；该场景观测到9组端点连通分量，不等同于整个网格的全部岛数。首次检查遇到旧Magnum Vector3不支持tolist，改用其迭代协议后完成；失败日志original-navmesh-01.log保留。

另外29条RxR存在原生is_navigable不接受的端点：13个起点、16个终点，分布oLBMNvg9in8、zsNo4HB9uLZ、EU6Fwq7SyZv。最大水平偏移约0.69m、垂直偏移约0.036m。对13个起点的52次0.25m原生try_step诊断中，31次位移超出名义步长，最大0.735824m。证据original-offmesh-endpoints.json和original-offmesh-try-step.json；这是待解决的额外物理运动问题，不删除标注、不把该现象当作合法修补。当前全量工程gate仍保持关闭。

原生数据加载器完整读取1839/1223，逐条保留原指令、起终点、场景和RxR instruction身份。体型1.5/0.1m、前进0.25m、转角15度、500步、种子100已确认。证据outputs/setup/native-dataset-config-probe.json。探针先漏传trainer设置的NUM_CHUNKS，后记录代码漏导入Path，两次失败日志保留；修复后的持久入口为scripts/check_native_dataset.py，并同步修复Oracle诊断入口的一分片配置，正式trainer本就设置这些字段。

GPU7曾因低显存被误判为空闲；启动器查到外部计算进程后在模拟器初始化前拒绝。已纠正判断，当前八卡均有外部任务，未停止或挤占。候选网格控制器只等待真正空闲GPU，状态outputs/setup/mesh-candidates-state.json；尚无已验收派生profile。

干净导出baseline-01暴露micromamba list --explicit并非纯机器可读锁的问题，改用env export --explicit并检查@EXPLICIT与全部固定URL。baseline-02正按已暂存tree和锁从零复建，两个尝试均保留；尚未给干净复建PASS。没有正式模型成绩、结果登记、提交或push。

## 2026-10-15 08:13 SGT 输入组件和历史候选复验

实际官方tokenizer、SiglipImageProcessor、process_images与图像token插入链在CPU检查通过：8×3×384×384 FP16、8个图像token、reason/action IDs128261/128262，tokenizer与embedding vocab均128263。outputs/setup/model-input-components.json仅证明预处理组件；无权重加载、生成或导航。第一次探针只import llava未触发builder注册，改为与trainer相同的builder导入后通过，两个日志均保留。

只读全局rxr-connectivity-fixed候选在当前新模拟器中复验，3062条起终点和参考点距离全部有限；仍有10个起点/16个终点离网（26条）。outputs/navmesh/legacy-candidate-profile.json与legacy-candidate-audit.json记录文件身份和历史参数声明，没有将它标为本次构建通过。

预先冻结的Oracle清单扩大为44条，原33条模型pilot选择不变；新增四项运动边界CPU回归，28项总回归零失败零跳过通过：outputs/verification/cpu-motion-bounds.json。正式gate继续关闭，等待空闲GPU上的新构建与44条真实运动验收。

## 2026-10-15T08:23:21.928117+08:00 干净导出验证通过，等待GPU

干净副本最初的CPU回归发现独立Python3.10没有os.O_PATH，而运行启动器使用的系统Python具有该常量。依据主机Linux asm-generic/fcntl.h的O_PATH=010000000增加兼容定义，保留真实内核拒写及子进程继承测试；主环境28项回归通过。没有降低保护能力或跳过失败测试。

完成独立安装的副本随后刷新为暂存源码tree 97dbef9c0203c00eb40df6de18a9ff752d14d20e（仅源码刷新，原独立依赖与原生编译产物保留），重新安装editable项目，再验证215项可移植锁完全一致、实际模块来源、新副本原生数据与输入组件、三种保护模式、28项CPU回归和pip check，全部通过。首次失败回执保留；最终回执outputs/verification/clean-refreshed-final.json，源码刷新记录clean-refresh-01.json。该证据不包含GPU模型生成、运动或正式测评。

离网诊断现有可复现入口scripts/audit_endpoint_motion.py，输出outputs/navmesh/original-endpoint-motion.json。更正统计口径：先前“31次超过0.25m”指三维位移；分离水平/垂直轴后，水平超过0.2501m的是30次，最大三维位移仍为0.735824m。正常上台阶可有超过水平步长的三维位移，不能全部称作水平违规；运动门槛已分别检查水平、垂直及reset误差。

当前验收：两端移动完成（远端剩余后验哈希按用户指令停止）、源码/独立环境/数据/保护/CPU/干净导出通过；原始33条已复现，历史候选仅静态距离通过；新派生网格、44条真实运动、真实模型pilot/顺序复验、完整1839+1223、独立结果审计及发布未完成。GPU资源全部有外部计算任务，候选控制器等待空闲，工程与正式结果gate均未开放。未提交、未push，没有本次正式成绩。

## 2026-10-15T10:23:14.350912+08:00 按最新资源授权启动GPU链路

用户明确要求直接使用现有资源。停止本任务原空闲等待控制器，改为GPU7共享剩余容量、单worker、启动至少28GiB空闲；不停止外部任务。策略configs/local/resource-policy.json，evaluate manifest冻结该策略。

四组新构建（body1.5m/radius0.1m不变）全量3062条静态结果：默认重建33条不连通；仅cell_height=.05为0；仅climb=.30仍33；两者组合为0。因此优先选择唯一必要变化cell_height=.05，默认climb=.20保持不变。各组profile与完整设置在data/derived/navmeshes/body150-*-v2/profile.json，审计outputs/navmesh/body150-*-v2.json。这不等于物理运动通过。

真实模拟器初始化暴露np.float已移除，install_compatibility.py在独立Habitat-Sim/Lab中替换为语义相同的float；原生渲染初始化随后通过，失败日志保留。RxR Oracle进度观测访问缺失的geodesic_distance字段而报错；移除未被模型读取的Oracle观测传感器，仅保留instruction观测和模拟器RGB/depth，评测measure全部保留。模型的prompt、帧采样、输入张量和动作不变。真实motion第二次尝试已启动，44条清单不变。

## 2026-10-15T10:31:24.366851+08:00 全部端点门槛保留与环境真实链路

用户明确选择继续研究网格、所有端点通过后才正式测评，并要求完整环境检查修复。因此motion-cell005-02的FAIL保留，不能用原生回放替代该门槛。44条Oracle任务全部success且reset位置误差0；CPU原生回放44条全部位置逐步误差0（outputs/navmesh/motion-native-replay.json）。这证明观测到的位移是原生行为，不是本项目添加的瞬移，但不足以满足用户选择的端点条件。

两条R2R模型诊断diagnostic-r2r-nativefix-01完成。模型输入/输出/解析/实际动作语义审计通过，所有逐任务指标与独立复算一致。1条成功、1条普通导航失败均保留；诊断不登记正式表，validate_results明确拒绝非full scope。真实RxR环境专项预先指定6892与3888，独立run diagnostic-rxr-environment-01正在执行，不替代35条正式前pilot。

三个场景重建：cell_height=.05、cell_size=.05时18条离网；edge_max_error由1.3改.1仍18；cell_size=.025时9条且0断连；cell_size=.01时56条离网/136条断连，作为负结果排除。输出outputs/navmesh/endpoint-study.json。剩余9条均为oLBMNvg9in8共用点[5.300414085388184,0.04583600163459778,2.102294683456421]。原始GLB三角面解析在其上方约0.14575m发现实体表面，证据endpoint-geometry.json；独立临时trimesh仅装在.cache/geometry-tools，未写入主环境。继续垂直分辨率/台阶单因素对照，体型/标注/坡度不变。

### 几何分析更正与RxR batch修复

原endpoint-geometry.json没有应用Habitat对MP3D GLB的Z-up→Y-up转换，故“上方0.14575m实体层”判断撤回，不用作参数选择依据。endpoint-geometry-world.json应用(x,z,-y)后，该点地板约-0.0266m、上方顶面约2.7849m；障碍应进一步检查横向体型范围。此前按错误解释启动的三项数值对照保留为探索负结果，不当作物理证明。

RxR环境诊断在首次生成之前因instruction sensor的tokens=None被batch_obs转张量失败。AwareVLN从current_episodes().instruction.instruction_text读取文本，完全不使用数字instruction sensor。evaluate_worker只关闭这个未使用的辅助观测，保留episode原文本、RGB/depth及全部measure；不伪造tokens、不改prompt。旧失败run保留，新身份重新开始诊断。

## 2026-10-15T10:39:57.171577+08:00 环境诊断与最小端点修正提案（未执行）

修复空数字token后，RxR两条真实模型诊断完成，模型输入/输出/解析/动作审计通过，逐任务指标与独立复算一致，1成功/1普通导航失败保留。环境真实链路已有R2R和RxR各2条证据，但最终身份的全部复建/顺序回归仍待完成。

endpoint-constraint-conflict.json记录9条共用点与固定圆柱体型相交的原始GLB三角面证据。未修改原始或派生标注。仅在内存假设修正坐标，结果endpoint-correction-proposal.json：在三个场景cell_size=.025、cell_height=.05、其余默认且体型不变的profile下，候选为[5.370209217071533,0.009996652603149414,2.14882493019104]，相对原点水平8.388cm、向下3.584cm、三维9.122cm；全量3062条端点均is_navigable且距离有限。此结果仅为静态提案检查，不是正式验收。

原始几何复核endpoint-candidate-geometry.json：候选点附近脚底以上0.3–1.5m内最近所检三角面水平距离约10.879cm，大于10cm半径，尚需完整圆柱面与实际reset/动作/渲染回放验收。受影响为5个起点（3888、7963、8829、10116、10287）和4个终点（6171、6243、10646、10757）。五条起点任务GT首点与原点完全相同，若授权派生协议需同步修正对应首点；四条终点任务GT末点并不等于原目标，不应强行改成新goal。完整reference_path和GT修正规则必须单独冻结并复验，不可批量盲改。

用户询问具体修改方案；本节仅提案，未获得派生标注实施授权。原始数据保持只读，正式gate关闭，无commit/push。

## 2026-10-15T11:06:53.570750+08:00 最终几何方案与全量回归通过

按照用户要求继续检索官方Recast/Habitat及冻结AwareVLN指标实现，依据与链接见DATA_INTEGRATION“官方依据与最终候选选择”。探索表包含所有失败候选，没有按模型分数调网格。恢复原物理区域面积阈值（cell_size .025，cell_height .05，region min/merge40）后，3062条端点全部可导航、全部参考点至目标距离有限，非有限任务0。机器人1.5m/.1m、默认max_climb .2、slope45及原GLB不变。新持久构建入口再次实际生成3个网格，逐文件SHA与已验证候选完全相同。

派生标注仅9条变化，5条GT首点同步，原始全部源文件哈希未变，其余guide及GT值一致。最终profile上48条真实Oracle导航全部成功，reset误差0，独立CPU原生动作回放48条逐步位置误差0，通过跨楼层/有限值检查。完整证据final-static.json、motion-final-01及配置recipe/protocol/diff。32项CPU回归已通过，但随后持久脚本/环境身份的最终复验仍在推进；正式模型全量还未启动，不能写最终完成。

## 2026-10-15T11:11:26.138284+08:00 最终环境复验与连续全量流程

最终独立副本全部13项入口检查通过（安装、兼容、链接、派生标注、全量预检、原生数据、动态库、输入组件、环境身份、32项CPU回归、保护、源码边界、pip check）。版本比对首次直接比较pip list的editable绝对路径，错误地将独立根路径差异当作版本差异；保留clean-final-protocol-failed01.json。按每份环境实际根严格验证可编辑包未越界，再比较相对路径及全部版本，完全一致。最终回执outputs/verification/clean-final-protocol.json。原生身份另显式包含实际加载的_corrade、_magnum、flash_attn_2_cuda，不只记录Python包装包。

当前冻结源码摘要049478d3a1f39b9697a619a1d538d2de90b8586d4ddc380eace36ac8b58a7ed5。连续控制器.rebuild/run_final_pipeline.py先执行最终R2R双任务与B单独运行顺序回归、RxR原33+2专项、独立指标/语义审计，再验证engineering gate，之后自动执行R2R1839和RxR1223正式新推理、全量独立审计与登记。任何失败中止后续步骤并保留尝试。原始状态outputs/final-pipeline-state.json，日志outputs/setup/final-pipeline-controller-02.log。当前仅进入最终模型验证，正式全量和发布尚未完成。

## 2026-10-15T11:18:17.189838+08:00 最终模型顺序回归通过

pilot-r2r-final-v1已完成2条，独立轨迹指标复算与模型输入/输出/解析/primitive动作审计通过。order-r2r-final-v1将B单独在同一GPU7执行，outputs/verification/order-final.json确认paired序号>1、single序号1，实际prompt、图像像素/张量、输入/输出token及动作位置序列完全相同。未通过更改解析、随机预算或选择性重跑得到一致。

连续流程进入pilot-rxr-final-v1的35条专项，仍未将诊断登记为正式结果。后续全量仅在全部engineering证据与当前冻结身份一致时启动。最终阶段结论尚未完成，待正式全量、审计与发布回执后更新。

### 参考轨迹口径补充 2026-10-15T11:38:43.449230+08:00

全量参考轨迹验收检查的是实际profile上的目标距离有限，不等于要求所有原密集GT点落在新网格中心可走面。原标注除授权5个GT首点外保持原值。原始与最终GT投影统计见outputs/navmesh/reference-quality-comparison.json；这些现象保留，不通过批量投影GT来抬高nDTW或隐藏异常。正式报告需注明该限制。

## 2026-10-15T13:06:30.299598+08:00 补充最小场景对照并冻结v2

补充场景级对照确认EU6Fwq7SyZv只需cell_height=.05即可通过端点和参考距离，水平cell_size保留默认.05、region min/merge20。其余两个修复场景保持.025/.05/40。组合方案全量3062端点均可导航、全部参考点至目标距离有限；原密集GT离网样本314→228、涉及任务158→101，最大水平投影.3709→.3784m（并非每个统计量都改善），最大垂直投影仍.5954m。选择依据是更少参数改动和更少参考投影差异，不使用模型成绩择优，不扩大GT修正范围。

在正式全量前保留v1诊断并终止仅本任务v1进程组，记录pipeline-v1-interruption.json，不覆盖已完成episode。v2协议为awarevln-scene-minimal-endpoint9-v2；9条派生数据的实际字节不变，仅协议/网格身份更新。持久构建再次重建三个网格，SHA与选定候选一致。v2对应的物理、干净环境和模型验收重新执行，旧身份不混入正式结果。

### 2026-10-15T13:07:33.461904+08:00 v2物理验证通过，持续流程存活

outputs/navmesh/final-static-v2.json确认3062条端点全部可导航、非有限参考距离任务0。outputs/motion-final-02的48条真实Oracle执行和独立原生逐步回放通过。已核实outputs/setup/final-pipeline-v2-process.json记录的PID/starttime及命令与活动进程一致；控制器等待v2干净环境复验后自动接续最终模型验证、全量及审计。发布通路保持等待全部验收，尚无正式登记和push。阶段仍进行中。

### 2026-10-15T13:14:28.248611+08:00 v2模型顺序回归通过

v2的R2R双任务及B单独运行均完成并通过独立指标/语义审计。order-final-v2.json确认episode28在同一GPU7的执行序号由2变1，模型输入、输出和动作精确一致。连续流程已进入pilot-rxr-final-v2的35条专项。正式全量与发布仍未完成；本机发布控制器已核实命令与PID匹配，仅等待全部验收。

## 2026-10-15T13:34:29.793673+08:00 新增独立导航连通性conclusion与强制发布门槛

按用户明确要求建立[导航连通性专项验收结论](2026-10-15-1-conclusion-导航连通性专项验收.md)，覆盖完整静态端点、稀疏/密集参考相邻段及正式实际逐步轨迹。初次严格静态3062条、179303次点目标查询、170117次相邻段查询全部通过；两条R2R诊断实际148位置/146段通过，独立不可达负向夹具被拒绝。审计器开发失败及修复记录在专项conclusion，未改动模型运行源码。

正式两套全量结束后，新增审计器必须复核完整1839/1223条实际轨迹、实际场景网格与体型，更新专项最终结论后才允许提交/push。原有完整评测流程继续运行，源身份不变。本机发布控制器更新时首次未取得Windows文件锁而退出；已确认旧进程终止、锁可用，改用已有锁文件的r+b访问和有限重试，重新启动并实际验证第二个实例被排斥。没有删除锁或绕过互斥，没有发生提交/push。

## 2026-10-15T14:01:06.525476+08:00 正式全量启动

v2的35条RxR专项全部完成，独立指标复算与模型输入/输出/动作语义审计通过，engineering.json状态PASS。此前R2R双任务/单独任务顺序回归及clean/static/motion/replay/CPU/保护门槛均已通过。连续流程已开始awarevln-r2r-valunseen-endpoint9-20261015-v2正式1839条全量，后续自动接续RxR1223及全部独立审计。严格连通性专项还会复核完整实际轨迹，未通过不得发布。当前仅启动全量，不代表全量完成或push成功。


## 2026-10-16T23:36:31.411118+08:00 R2R正式全量验收、统一结果登记与RxR继续

正式run awarevln-r2r-valunseen-endpoint9-20261015-v2完成1839/1839，缺失0、未解决运行异常0，各指标有限分母均1839。原生指标与独立复算一致；模型输入/输出解析到实际primitive动作的全量语义审计PASS，覆盖1839任务/轨迹及115138图像文件，错误0。记录到1次官方解析fallback，已按原实现如实包含，不是偷偷替换模型输出；模型普通导航失败保留为有效结果。validation.json于23:02:54 SGT通过，23:04:44登记。

唯一指标来源为[本次正式报告](../../results-show/awarevln-r2r-valunseen-endpoint9-20261015-v2.md)和[自动生成的统一总表](../../results-show/model_results.md)，本结论不另维护一组SR等数值。已执行render_results.py及--check，生成/一致性检查均通过。R2R本身仍读取原始R2R标注；该批使用修复网格。协议中9条派生标注只用于RxR，不把R2R说成修改了9条数据，也不与旧网格分数直接计算收益。

原控制器808206/start14259388自然接续full-rxr；23:34核验RxR15/1223、active1/pending7/failed0，eval控制器1411184/start26491356，worker1411386/start26494222正常。没有重启任务、改变模型/源码/预算/profile或资源策略。evaluate的run目录和非阻塞.controller.lock要求单一所有者，不手动抢先启动当前controller已安排的后续run。R2R通过不等于项目发布完成；Landmark/source_geometry_acceptance及RxR完整结果仍是后续门槛。

R2R补充运行统计：8个逻辑分片均只有process-1.json实际启动回执，未发生分片重试或普通导航失败择优重跑；完整检查回执outputs/verification/r2r-formal-reporting-audit.json。各指标有效/非有限数量和普通失败/运行异常均以已登记summary与生成总表为准。

## 2026-10-17T07:21:37.369140+08:00 完整轨迹审查更正与继续验证

R2R全1839/195541实际位置审查发现5个离网点，已精确原生复现并撤回登记状态，原始指标、身份、分母、原报告均保留。独立Detour探针定位getPolyHeight返回失败被忽略；隔离候选仅解决原生点位判定，仍有1源身体接触/5段精确扫掠接触，不能采用或报告环境完全通过。结果重生成检查通过。当前RxR304/1223继续。D7新混合v35静态全786恢复90且零退化，已接续全场景真实运动及独立审计；不把静态恢复计最终成功。完整证据和失败、更正见同一专项conclusion。原运行源码/环境/预算保持冻结；发布仍阻止。

## 2026-10-17T07:53:04.698090+08:00 完整端点源审查与未应用修正预案

全3062任务6124端点源审查发现新增106条，原/float32一致；原生is_navigable全部通过，说明两门槛不同。v2预案在明确的新X7配方下解决全部21共享位置，45R2R/61RxR标注及63GT首点的完整字段差异已准备，其他字段/语言保持；在内存代入完整方案后，独立6124源检查与3062参考连通全通过。新增范围确认待用户答复，未修改/激活新数据，不能视为正式修复完成。EU6全132四条件动作对照存在退化，候选拒绝。RxR319/1223与D7全786继续；完整原始证据、失败和授权边界见专项conclusion，未push。

## 2026-10-17T08:50:27.553991+08:00 D7完整审查与未采用环境候选

D7 v35全786及独立70973动作审查已终态491通过/271搜索失败/24静态。补充同目标/朝向的新实际执行恢复唯一旧证明，当前同profile路线存在性492，原470全保留；新90静态恢复仍无动作通过。529精确接触见证与细节高度原生API对照完成；v36新全量已接续，严格门槛保持。实验性源碰撞响应在132×2条件中每组120执行/12初始源失败保留，独立实际动作及事件审查通过诊断契约，未修改正式环境或宣称模型导航成功。106条派生标注范围仍待确认、原数据不动，R2Rretracted与原RxR冻结运行保持，未push。完整失败、更正和证据见专项conclusion。


### 2026-10-17T11:16:41.178393+08:00 新增106授权及endpoint115实际生成

用户已批准新增106条派生修正，累计115，原始数据不变。实际文件全3062/6124静态源身体与连通验证通过；全3062严格原生运动/独立回放正在进行，初始水平越界失败及最小离线规划修复均保留，新身份全量接续已安排。逐条更正表见DATA_INTEGRATION，证据/运行身份/失败详见同一导航专项conclusion。旧RxR冻结继续，旧R2Rretracted。全量新正式测评与发布均尚未通过启动/完成门槛；未commit/push。


### 2026-10-17T14:40:52.407439+08:00 endpoint115第一轮全量验证完成但未验收

v1全3062完成，1553严格通过/1509失败；149586动作独立回放误差0。失败已逐条归类：861水平越界、622搜索上限、24首节点耗尽及2其他前沿耗尽。24初始动作源失败的原生高度投影已复现；不能将其视为已修复或物理无路。新v2完整3062及独立对照按既有接续推进，详见同一专项conclusion。原RxR继续，新正式测评及push保持验收前置条件。


### 2026-10-17T15:46:49.841596+08:00 实际worker绑定纠错

名义v2实际仍指向旧worker，我方替换未命中及启动断言遗漏导致算法身份表述错误。844已索引及中断证据封存，只停止错误诊断组；旧RxR继续。正确worker以新run endpoint115-full-motion-v3全3062重建，实际路径/哈希/manifest三项测试通过。完整影响和证据见专项conclusion；未删数据、放宽门槛或push。


### 2026-10-17T16:04:48.901938+08:00 停止扩展修正范围

用户明确要求“改完最后一轮就不要继续修改了”。本次按当前已经启动的endpoint115-full-motion-v3作为最后一轮，不另开v4/网格/标注/算法修正，也不为追求全部PASS重复导航试验。固定现有源码、数据、profile和验收条件，只完成当前全3062运行、逐条独立回放、既有v1/v3比较及只读失败分类和最终文档；旧RxR继续。失败如实保留，完成运行不等于通过验收。

当前v3 273/3062，{'PASS_STRICT_MOTION_REPLAY': 199, 'FAILURE_PRESERVED': 74}；旧RxR659/1223。冻结回执outputs/verification/final-round-freeze-20261017.json，绑定实际manifest/源码/profile/派生数据身份。后续若仍有失败或信息流门槛未通过，应报告限制并收尾，不自动继续修改。新身份正式测评仅在本轮冻结状态已满足全部既有前置门槛时启动；否则不启动、不push。不能以本次停止修改要求为由降低标准或把剩余失败改成通过。


### 2026-10-17T16:07:31.961206+08:00 用户最终交付口径：三组结果分开整理

最后一轮完成后只做现有审计和文档收尾，不追加修改或新实验。最终交付必须分别整理：①旧R2R原协议1839模型测评；②原RxR冻结1223模型测评；③endpoint115最终v3全3062离线派生验证。每组列执行完整性、通过项、失败/未解决项、证据身份及对原基线结论的实际影响。模型导航成功/失败、基础设施错误、严格附加几何门槛及派生Oracle结果不得混淆；不能因为附加几何门槛失败而无证据宣称旧指标错误，也不能因为旧指标已计算就声称严格门槛通过。

保留原基线和派生实验各自数据/profile/源码身份；误绑定v2单列历史纠错，不纳入有效新版结果。最终给出明确交付状态（结果/文档是否完成、哪些验收仍失败、是否具备发布条件、实际是否commit/push）。不再启动新身份正式测评作为本次收尾工作。当前最终v3 327/3062、原RxR659/1223；这些仅为过程观察，结束后用完整回执替代进度描述。


### 2026-10-17T19:51:36.080995+08:00 最后一轮派生验证完整终态及三组结果分列收尾

endpoint115-full-motion-v3于19:37:41完整终态，已有独立v1/v3对照于19:38:59完成；两个控制器均自然结束。再次只读复核全3062结果及独立回执哈希、任务集合、实际worker SHA、同profile及完整动作统计；没有启动任何新导航/修复。收尾回执outputs/verification/final-derived-v3-closeout-20261017.json。

|派生验证类别|R2R任务|RxR任务|合计|
|---|---:|---:|---:|
|严格运动/源连续扫掠/独立回放通过|1353|872|2225|
|5000节点搜索上限|468|343|811|
|首节点前沿耗尽|18|6|24|
|1776/721节点后前沿耗尽|0|2|2|
|完整分母|1839|1223|3062|

全部187642个实际动作（含失败任务已执行前缀）独立回放，最大误差0；已执行轨迹源接触/原生告警0。这里没有把“尚未找到完整路线”的837条移出分母或计作成功；它们全部为SEARCH_OR_BUDGET_FAILURE，没有本轮基础设施失败或实际水平超步失败。完整路径存在性只对2225条获得证明，837条有限搜索失败不是一般物理无路证明。

相对完整v1：原1553严格通过全部保留，新增672，退化0；v1的861水平超步中672取得完整合规路线、其余189转为5000节点搜索失败。此变化仅说明离线Oracle提前筛除违规动作后的路线证明结果，不是模型SR收益，也不影响原基线模型动作记录。新增106标注任务中37通过、69失败；原9修正任务8通过、1失败；未改2947任务2180通过、767失败。标注静态修正与整条运动验证分别表述。

**三组结果必须分开：**

|结果组|执行/结果|通过项|失败或未验收项|对原基线结论的影响|
|---|---|---|---|---|
|旧R2R endpoint9原运行|1839完整，普通导航失败632、运行错误0、各指标非有限0|原指标复算、当时模型输出→动作语义审计|严格实际轨迹5原生离网，登记retracted；后续识别的独立tensor重算审查范围不足另列限制|指标依其冻结协议仍可复核；不能仅因附加几何门槛失败宣称指标算错，但不满足既定全部发布验收|
|原RxR endpoint9冻结运行|当前790/1223，仍运行|尚不能提前给全量结论|完整指标/复算/语义及后续审计待结束|保留原协议和原失败，完成后单列，不能用派生Oracle代替|
|endpoint115派生v3|3062完整，2225严格通过/837失败|完整覆盖、actualworker身份、187642动作独立回放、v1/v3无退化对照|未全通过路线验收；新身份模型信息流及Landmark全验收亦未完成|离线验证、输入协议不同，不是新模型成绩，不替换旧R2R/RxR指标|

旧R2R历史原协议指标：SR65.633496%、SPL57.278175%、nDTW65.369522%、NE3.978647m、OracleSR75.095160%；来源原summary.json保持，不能称派生协议成绩。

当前明确交付状态：**最后一轮派生验证和本项文档已完成；整体三组最终报告仍等待原RxR完整结束及已有审计。全部验收未通过，不具备push条件，未commit/push。** 按用户要求停止修正，保持837失败和其他未验收限制，不再开新试验。仅继续健康原RxR及已安排审计、最终结果整理；所有后台任务结束后给出统一最终交付状态并停止监控。

证据身份：v3 validation `c47a911ebf12029c09bea3a195bd0e3d3f0ae1e794a3eac48f22c37230e9bfa0`；完整pair审查 `a3e0a7b6d691fdc5ecb5106acb6b3b1e1cc36093c040abf645a9d14374533199`；v3 manifest `923b4e22846af7f2d8733c248b612a3faed743f93c8bd6c25798c0a745338fb8`；实际worker `01b886658c158a56b70f5cbd742415f309624ae337eb293bb1e37db08aef9150`；profile `73a5f9b002d9c5e22c8632f8c41261633b25163248e98f1bbd110b74a92514a3`。这些是证据身份，不应从目录名推断通过。


## 2026-10-18T16:35:31.032803+08:00 原模型结果分组收尾与研究边界

原模型1223/1839完整结果及复算回执已逐项核验，见outputs/verification/original-model-runs-closeout-20261018.json和[统一总表](../../results-show/model_results.md)。两组普通导航失败632/396属于有效成绩分母，不是运行异常。旧派生v3和新Oracle开发对照均为离线可执行性研究，不能取代模型成绩。Oracle新对照24/24及资产33954审查完成，但新增路线恢复0，研究尚未全量验收。原模型原协议审计通过与新增严格门槛未过同时如实保留，未commit/push。进一步证据和限制详见[专项conclusion](2026-10-15-1-conclusion-导航连通性专项验收.md)末段。


### 2026-10-18T21:18:56.641354+08:00 原始图参考与461视点、pRb边来源核对

原始离散图参考已补齐71场景：复用6份本case旧缓存，其余65份按Matterport3DSimulator官方冻结提交589d091b111333f9e9f9d6cfd021b2eb68435925取得，总20066429字节，全部匹配官方Git tree blob SHA1及大小，另存SHA256。未重复下载场景/图像/权重。原始图来源回执及已哈希审查证据100文件已同步到远端outputs/oracleAdapter；未同步新的活动Python/config文件，未更改正在运行的full-continuous-reference-v1。

original-graph-lineage-bound-v2逐点确认原461缺失视点全部在原始图同名存在、included=true，且在发布适配图同名缺失。旧8011节点相机位置与官方pose的[x,z,-y]轴转换最大差1.6431300764452317e-14m，故没有发现该相机坐标轴转换错误；此结果不证明相机到脚底/源几何可行。没有改名/合并/替代节点的发布来源证据，台账明确保留UNKNOWN，不以空间最近点制造身份映射。validation SHA3f7307822445bed9fd5d784ccf6fdb2471d205a6a67d587dd5f385add0700a66。

raw-source-graph-paths-bound-v2从3份原始Landmark文件重新投影全部33954路径（来源文件SHA逐项保留），独立得到8011唯一视点和同一461缺失集合，与旧台账完全一致，未移除held114。原始图33954条路径的逐步邻接均成立。直接按原ID序列套发布图：11689缺ID；14491节点齐全但缺至少一条原直接邻接；7774全部直接邻接存在。这只是图级源路径核查，缺直接邻接不等于没有多跳替代，更不等于身体或原生动作不可达；未执行FOV/10离散步限制/重初始化，不冒充原论文A或连续B的成功率。validation SHAc149cf9512ab36aecec0f11767c1478b25b2cfcbb069d3bf51078bbe129765db。

pRbA3pwrgk9发布edge_51两端71dfeb…→77d87c…在原始图没有直接边。该场景660条原始任务中，直接使用此边0条，包含两个端点21条。原图最少跳数路线经c327988cdf454a77a0094af6e906f257及658505895e5a449ab39a76b1e1f337a5，共3跳。该源图证据说明不能把发布图新增边的已知运动失败直接说成原始标注路径断裂；也不能把这条3跳图路线自动当当前体型/动作协议可执行路线。未向任务插入节点、删边、改落点或重跑导航，既有弱门槛重放证据和当前全量证据继续分别保存。

本次新活动审查实现位于本地oracleAdapter/src/oracle/adapters/landmark_rxr，配置在同模块configs/experiments/graph_lineage.json，统一入口新增audit-graph-lineage及audit-raw-graph-paths。本地78项CPU回归通过；远端仍用全量冻结的73项回归时源码，新命令待运行终态后才同步。源码快照outputs/oracleAdapter/graph-audit-source-20261018.zip。最初v1审查没有完整启动导入回执，原结果保留；bound-v2仅补实际入口/导入路径/hash/任务契约/信息条件，重新只读核对，全部证据输出字节与v1相同，新增原生动作0。不得声称v1当时已拥有v2启动证据。

本阶段仍进行中：上述是Landmark来源归因，不是Oracle算法收益或全部连续修复。全37016原生/独立回放仍由既有冻结任务推进；完整结果/失败分类及A与B协议差异仍待最终验收。原R2R/RxR模型结果不改，不因本次图结论自动恢复或撤销其验收状态；未新建模型测评、commit或push。


### 2026-10-18T21:25:18.072383+08:00 连续参考逐次索引与旧候选来源复核

本轮从三份共享只读RxR-CE Guide源文件投影稳定身份和完整reference_path，并以原始Landmark33954条逐任务复核，回执outputs/oracleAdapter/continuous-reference-lineage-v1/validation.json（SHA40305cc269558d46590396fe59acf64319d361a3b498b6711ac8655149dbf72f）。25920条split/instruction/path/scene/language全部一致且reference数量对应；8034条无匹配CE身份保留，没有用文本或空间最近点补匹配。逐任务reference occurrence索引、子段区间和365个缺发布图视点的每次来源出现均有台账。

从实际CE来源重建7264个视点候选集合，与旧native-mapping.json全部逐值相同；多坐标候选节点0、新增节点0、旧节点未重建0。461缺发布图ID中365有稳定身份加序列索引的CE坐标来源，96没有。此前official-multiple-anchor-check只检查旧表；本轮从源数据重新构造，仍无隐藏额外候选，不应继续反复尝试“旧表遗漏多候选”假设。全部33954原路径没有重复ID；25920匹配参考也没有连续零长度段，但实现仍保留逐次索引，并以合成回环/零段反例测试防止未来数据被合并。

重要可信边界：CE reference_path未逐点携带原始viewpoint ID；对应依据是稳定任务身份、完整路径顺序和相同长度，并非作者提供了逐节点转换回执。冻结VLN-CE公开树未发现原RxR转换程序，不能编造该实现或把坐标相同当成物理可行证明。新台账使用IDENTITY_AND_ORDINAL_REFERENCE_ACCOUNTED分类，未生成新目标、未改变任何任务坐标、未将GT旋转/位置重置到Landmark任务中。8034缺CE的历史原因仍未知，原Guide身份已经匹配不等于连续资产存在。

新审查代码继续只在本地oracleAdapter/src/oracle，统一入口audit-reference-lineage；81项本地CPU回归通过，源码快照reference-lineage-source-20261018.zip SHA19cf2202a45181f8b7798e74dc25cd309995fb80a413e53bfd934ac24ff3b094。新增源码未同步远端活动目录，证据已同步到case1自有outputs。原生动作新增0，本轮不计任何导航恢复或算法收益。全量控制器2198741/start42998002本轮核实非僵尸存活，观察时830/37016、RUNNING；不重启，不将进度当成验收。原模型、原始数据、几何及全量冻结输入保持，未commit/push，专项仍进行中。


### 2026-10-18T21:31:26.690837+08:00 全量收尾效果与成本报告工程验证

完整性审计原full_review.py已有覆盖/身份/原始流/独立回放门槛，但未提供全量分组效果和成本统计。本轮本地oracleAdapter/src/oracle/research/full_report.py补齐只读收尾报告器，先要求完整独立review及manifest/tasks/index/逐任务回执绑定，再按dataset/split/language/目标/参考范围/profile/实际privileges/method分组。静态失败保留分母，但不补成零成本teacher运行；普通搜索失败纳入成本分布；执行与审计全部attempt分别统计。P50/P95使用(n-1)*q线性插值。峰值RSS仅统计分布，移除sum以免被误解成并发总峰值。

控制器旧代码没有记录实际CPU，本轮没有热改它；报告明确controller_measured_cpu_seconds=null，reserved值只是预算预留。原生贪心内部探测也未完整计数，不能以preview次数当全模拟器调用量。无exit成本保留unknown，不补零；有settled回执时核验exit哈希和PID/start_ticks。原生算法、预算和物理验收不变。

用既有full-controller-engineering-v1四任务不可变导出进行报告集成，而非重跑导航。首次遇到旧回执缺motion_attempted字段而拒绝完成，证据full-report-engineering-launch-failure.json保留；随后仅对manifest没有新worker字段的历史格式作显式兼容，依result_sha256判断是否有motion，标记legacy_receipt_fields_absent；当前全量格式缺字段仍拒绝。旧回执不改。第一份成本报告保留；最终v2移除RSS求和并复核冻结source.zip，导航结果和原始数据不变。

最终工程报告full-controller-engineering-cost-report-v2覆盖4条：R2R1通过、RxR1搜索失败、Landmark2静态失败。执行4进程实际CPU合计27.280249475s，审计4进程合计6.344017898s；2次控制器会话预留7210s不能混当实际CPU。历史8个phase没有settled-cost.json，逐phase预留上界明确unknown。这些是工程集成成本，不是37016全量性能或算法收益。validation SHAe4439ab6006d4c6acebb6949b877adb9ee9a4a33f3bd0229b8a59a66c6fc7ea7。

本地86CPU回归通过，覆盖失败分母/不同信息条件分组/未知成本/负值拒绝/导出越界/PID身份等反例。报告器、入口及测试只在本地oracleAdapter；远端活动源码继续冻结。源码快照随报告保存在outputs，证据同步未运行新导航。全量完整结果、独立full review和正式成本报告仍待终态；原论文A与连续B可比性限制继续保留，阶段仍进行中，未新模型评测/commit/push。


### 2026-10-18T21:35:42.199376+08:00 原A协议复现就绪及发布子段数量核对

重新核对NeurIPS最终论文Table1/4.1/4.2/6.1及作者公开仓库。论文A是全景离散动作、3m范围、每子轨迹10步；中间landmark失败才重初始化并保留后续子指令，最终目标需STOP。公开仓库仍只有README，没有可直接复用的重初始化评测代码。reset朝向/仰角与模型状态、STOP是否占最后预算步、子轨迹切片和跨任务聚合的精确实现仍缺发布依据。本轮不自行填这些设置，也未把当前B的0.25m原生动作、严格线性身体检查和无重置执行改成A。

新只读readiness回执outputs/oracleAdapter/landmark-paper-a-readiness-v1/validation.json，SHAf03e01da45e1ee743a8f48c16a4a197c2250247f4e410c71afeeded0901bba75。共享发布数据保留33954完整任务，子段实际166663：train133531/val_seen13586/val_unseen19546；相对论文表格分别少71/5/1，共77。未发现逐记录修订日志，不能据此补造子段或改分母。已保留split级差异台账，未把当前数据宣称论文逐字节原版本。

原始子段有89条超过10条图边（train72/seen10/unseen7，最大19），逐条索引保留。这不是89条A失败：A的成功范围及实际策略/STOP语义不同，原路径边数不能替代真实评测。没有修改预算，也没有运行图捷径或重置冒充连续路线。协议证据配置landmark_paper_a_evidence.json明确execution_adopted=false；本轮只完成原A复现就绪核查，不输出SA/SSA/LN或A通过数量。

本地88项CPU回归通过，新增实现/配置都在oracleAdapter/src/oracle。证据已同步远端outputs，活动代码仍未覆盖冻结全量。论文PDF源SHAeb206b9f8ab9b7a5234e564db5f163141ea80c5bcf1ed8a691e72d0cc89c8a0a，892330字节，来源https://proceedings.neurips.cc/paper/2021/file/0602940f23884f782058efac46f64b0f-Paper.pdf。原A未复现这一未验收项明确保留；全量B、最终效果/成本和剩余失败审查仍待终态，阶段未完成。原基线及原始资产不变，未commit/push。


### 2026-10-18T21:39:17.253024+08:00 方法分类注册与贡献强度核对

方法注册表复核发现描述遗漏：冻结运行时require_task_contract已经显式支持reference_execution+official_actions，但registry只列出Landmark用途的官方建议组合。现仅在本地补guarded_official_reference_portfolio条目，声明相同ordered教师、REFERENCE_ORDER目标、无Landmark annotation特权；新增回归核对运行时与注册契约一致，错误套用Landmark或无官方动作方法仍拒绝。没有新增规划器/实验臂或改变teacher算法，远端注册表亦未热改。

RELATED_WORK.md中初始阶段“组合尚未选定/注册”的过期表述已明确标为早期状态，并指向当前实际证据。固定133同官方动作信息的建议单臂51、组合90，恢复39/退化0，但teacher CPU445.828到2530.914s，并非等计算量提升；纯搜索54、CPU4645.626s没有官方动作特权，属于信息消融而非同信息优越性。两个单臂均失败而组合实际通过8条，不能与事后并集混淆。无损状态键的12任务对照0恢复/0退化且CPU增加，不能凭混叠反例宣称覆盖收益。没有已成立算法创新；Landmark显式源connector属于映射记账，不能计为Oracle算法增益。

本地89项CPU回归通过，新说明和快照见outputs/oracleAdapter/capability-accounting-closeout-20261018。文档首次按Windows默认编码读取失败，在写入前终止；显式UTF-8后更新成功，未污染旧文档。运行中的全量仍冻结；本轮新增导航动作0、无新模型测评/commit/push，阶段完整验收仍待全量和协议边界收尾。


### 2026-10-18T21:43:45.281304+08:00 Oracle独立导出与离线wheel验证

本轮先核实全量控制器2198741/start42998002及其16个实际worker的PID/start_ticks/非僵尸状态，2026-10-18T13:39:55Z观察为1571/37016、RUNNING，无stop回执，未重启或改动任务。随后只在本地进行独立模块打包验证，不追加导航实验。

pyproject.toml原先dependencies为空，而CPU源几何检查和部分测试使用NumPy，现显式声明numpy依赖；不安装或升级当前环境。原configs/**/*.json打包规则不能依赖.gitignore来保护机器设置，新增exclude-package-data及package discovery排除configs/local。以case1自有干净导出夹具放置nested/do-not-package.json假哨兵，wheel中按成员名和内容双重验证不存在；没有读取或打包真实私有设置。

导出118文件，使用python -I运行源码导出89项CPU回归通过；pip wheel --no-index --no-deps --no-build-isolation离线构建成功。解包wheel并仅从解包路径导入，再次89项CPU测试通过。111个源码/公开配置文件成员及哈希逐项一致。wheel170396字节，SHA3fcb3f49e88f1fe4cb6d1a2396f6cfcc0405b867f6ec42fe845aa1d2867598ab。回执outputs/oracleAdapter/clean-export-build-v1/validation.json SHA8c51fa951b49df81c10fac091a110cc74bff028b44742f9dc34fb954a655762a；现有本机Python3.13.5/NumPy2.1.3/setuptools72.1.0用于CPU验证，依赖安装0、包网络下载0、原生动作0。

这证明独立CPU导出与打包范围，不证明全新Habitat环境或导航验收。原生运行仍使用冻结服务器环境，精确环境身份由运行manifest保存；通用依赖声明不是版本锁。pyproject变化尚未覆盖远端活动模块。证据增量传输已核验6文件；传输器新增--only白名单，避免每次重传既有参考图。源码/数据/验收条件和原模型结果未改，未commit/push；全量与独立审查仍待完成。


### 2026-10-18T21:48:16.695641+08:00 逐任务失败解释与当前状态入口收敛

全量收尾报告新增逐任务failure_explanation与failures.json，保留原failure类别，同时列缺坐标/缺geometry来源、离网参考索引、断开参考边、源接触参考/端点索引、下一必需reference、最后实际位置、最后搜索记录和规划拒绝统计。每条链接实际receipt/preflight/result/audit哈希。有限搜索失败明确physical_unreachability_proven=false，原生路线witness与端点源几何门槛分列。

本地92CPU回归通过；既有4任务工程证据只读报告分为1输入映射失败(train100702缺索引8)、1当前参考边失败(train1001边索引2)、1有限搜索失败(RxR10071/instruction57597)。原R2R工程任务仍通过；未重跑任何实际动作，也未将这4条称作全量成绩。证据outputs/oracleAdapter/full-controller-engineering-failure-report-v1已同步，远端活动实现保持冻结。

本次还将已过期的顶部当前快照移为历史快照，原正文保留；新顶部明确现在完成项、未验收项和最近观察时间，避免后续接手者继续依据57测试/组合未完成的旧状态行动。全部研究结果与原模型成绩分开，未commit/push。


### 2026-10-18T21:50:22.223342+08:00 Oracle文件Git忽略边界核验

远端Case1 Git忽略边界19个正反例全部通过，证据outputs/oracleAdapter/ignore-boundary-audit-20261018.json。Oracle源码、公开JSON协议/实验配置、测试、README/AGENTS/pyproject与正式results文档均不被忽略；configs/local含嵌套文件、构建/wheel、pycache、原始outputs、cache、backup、派生navmesh和models链接入口被忽略。初次probe指向models链接下的虚构文件被Git拒绝，改为检测链接入口，不遍历全局目标。该检查只验证规则，含尚未同步文件名的合成probe；不是暂存树内容/凭据/大文件的发布验收。没有git add/commit/push，规则文件未修改。


### 2026-10-18T23:09:04.389460+08:00 完整3062端点子集回执审查完成

同一full-continuous-reference-v1父运行中，端点任务1839R2R+1223RxR已全部完成，Landmark仍继续。只读封存完整journal帧前缀及3062已完成回执，父manifest/task_count37016/source.zip均保持原身份，没有伪造新的小分母全量manifest。快照endpoint-cohort-snapshot-v1含24500证据文件，压缩66603229字节；只复制已完成记录，不重启或覆盖任何worker。

本地oracleAdapter新增明确范围的review-completed-endpoints入口和公开endpoint_cohort_review.json。审查核验journal链/完整任务集合、父输入hash和Merkle成员、实际worker/teacher/auditor导入路径与hash、两阶段startup/任务/方法/协议、两份preflight的一致性、原始trace与数组、producer SHA、显式初始化次数以及独立回放回执。现有原生回放来自各任务先前独立进程，本次只归集核对，没有再执行导航或回放。95CPU回归通过；活动远端源码仍未覆盖。

审查结果endpoint-cohort-review-v1：R2R无兼容官方先验1839=1280严格通过+541预算失败+18前沿耗尽；RxR有先验1185=642通过+537预算失败，无兼容先验38=12通过+26预算失败。RxR总654通过/569失败，R2R559失败。共1128失败=1104预算+24前沿；所有实际244516动作对应独立回放，位置与朝向最大误差0，回放物理告警0。失败前缀无告警不代表完整路线通过；全部端点门槛未全部通过。每条失败已保留具体最后搜索/拒绝统计/末位置与证据链接。

所有失败detail为bounded_search_did_not_find_plan；最后SearchResult分别记录budget或frontier。当前记录没有保存唯一预算触发分支，不能把1104都说成5000节点耗尽；例如有展开1605、调用4814、约60s结束的案例。严守现有预算，不热加预算或挑任务重跑。搜索失败不是物理不可达证明。

本轮严格通过1934未达到旧endpoint115-v3的2225。旧结果保留，本轮不声称已取得全量覆盖收益。两轮控制器和墙钟预算未形成完整匹配对照：本轮显式60s每搜索/180s每任务，旧manifest文字声明5000节点、1500每段/10000任务等但未声明相同墙钟/控制器，不依据通过数差直接给算法因果结论。原R2R/RxR模型的标注/profile/目标与Oracle强参考口径也不同，这些不是新模型SR，不覆盖原基线结论。

validation SHA c7a5fc7c32115a7ad96606dc3d2311abc7cf89b6f5ae90b44c9a34922e59e07a，报告和完整失败表已同步远端outputs；父37016完整审查仍待Landmark33954终态，原A复现等限制继续保留。最新完整运行观察2026-10-18T22:54:39+08:00为3547/37016、16实际phase全R且绑定与manifest一致、无stop。未新模型测评、commit或push。


### 2026-10-18T23:20:43.145474+08:00 完整3062历史路线证据对照

对完整3062端点任务作只读历史对照，代码为本地oracleAdapter/src/oracle/research/history_overlap.py，统一入口compare-endpoint-history。原endpoint115-v3全部结果及独立audit文件按旧validation声明hash重新核对，源input文件按当前冻结source_binding核验，导出精简元数据(endpoint-history-metadata-v1，SHA474df36616494b4098619a10e5488a5887f5b533bd28c480a01a53d597d183e7)；不执行旧轨迹，不更改任何结果。

全部3062所列源input字节/manifest、目标顺序、原始旋转、历史旋转等价、实际初始位置、profile及native几何字节检查不一致0。对照为：R2R两轮均通过1280、仅旧版通过73、仅本轮通过0、均失败486；RxR当前有官方先验分支分别638/221/4/322，无先验分支12/1/0/25。合计295条仅旧版通过，本轮全部为search_budget_exhausted；旧严格成功回执均有independent_replay、exact_continuous_linear、空source_alerts及允许范围内回放误差。这是已有旧路线证据，足以阻止未经论证将这些失败归为数据物理不可达；不是本轮重新执行证明，不复制为新PASS。

仅本轮通过4条均为RxR有兼容官方建议分支：episode1242/instruction73507、5503/23949、6906/31539、8658/120185，完整task_key见报告。它们已包含在本轮3062真实执行/独立回放中，本次对照没有新增动作，也没有修改数据，不称作4条数据修正。

当前与旧控制器的完整内部状态、历史特权信息和墙钟/CPU账目没有形成同预算控制。因此对照使用historical_only_pass/current_only_pass描述，不把结果差直接作为算法因果收益或退化；不登记两轮成功并集。输入/几何一致不等于完整模拟器/规划状态已证明相同。原模型SR和旧Oracle结果仍独立保留。

报告outputs/oracleAdapter/endpoint-history-overlap-v1/report.md，逐条all3062-overlap.json，validation SHA514d43213cbe908da03fd771557e8053679e2386ba3a179bbed5ac6b310b6cd6。本地95CPU回归通过，报告/源码快照已同步outputs，活动远端代码未改。Landmark父全量继续，未新模型评测、commit或push。


### 2026-10-19T00:16:11.004110+08:00 历史几何回执兼容修复与保留完成结果续跑

原full-continuous-reference-v1在2026-10-18T23:38:17+08:00受控停止，已完成5144/37016，stop任务train:101576，异常KeyError('native_geometry_path')。完整调用链定位SourceScene从receipt读取单一字段格式；XcA2TqTSSAj历史回执使用native_triangle_dump_sha256，冻结catalog已保存正确native_geometry_path/hash。文件未丢失、几何未变化，属于接口预检漏覆盖。一次检查71回执发现70标准/1历史格式；没有把基础设施错误归为导航不可达。

先写失败回归，原实现不支持catalog-bound历史格式而失败；随后仅增加明确格式解析，要求legacy状态、native byte control、scene/hash、顶点/三角形计数与catalog一致，拒绝缺来源或冲突，不猜文件名。各调用处只增加catalog传递。101项CPU测试本地/服务器通过；全部71几何实际读取、三角面/包围盒与规范元数据控制字节一致，native动作0，所有原回执与场景保持。源证据geometry-schema-catalog-v1（SHA925318110ba293b306f96df29693255b00e8d69948e46073a076093657c565cd）。

新旧兼容检查验证搜索、NativeAdapter、状态键、contracts、portfolio、两几何核心及物理协议等10文件SHA未变；6个调用模块AST除catalog参数外相同；SourceScene.contact AST相同。这里只证明元数据接口修复及不变项，不能宣称场景导航修复。old-owned-process closure核对10289个历史spawn/start身份，无存活者，source-freeze CLOSED后才同步；原source.zip和全部失败保留。

父prefix-review已完整审查5144条（R2R1839、RxR1223、Landmark2082），包含普通失败，不重跑。原目标37016不缩小；新full-continuous-reference-v2只执行31872未完成Landmark任务，逐条记录parent_task_sha/new_task_sha和去除module_source_sha后的不变任务含义hash。新manifest SHA04db815594c8e89c095eba6ab7b6b4a1cfa28dbff7a2ccfec35e8523bcb7c31a，不是冒充旧冻结身份；父prefix审查SHA7188f9d0017498fef7bb797f232669d51d19e2c7da4bf09a6e520269f7512497。最终必须将两段完整、不重复任务集合与原1839/1223/33954对齐，并公开各自实际源码身份。

总CPU上限仍720h，扣除父运行保守账目154993.24807027262s后，新段上限2437006s，未重置总预算。单任务180s、单搜索60s/5000展开、150000预演、1500每reference/10000任务等均保持。每剩余phase仅给一次新基础设施尝试，避免原已失败任务跨版本累计超限；额外基础设施错误停下审查，普通失败继续保留，不择优重跑。

新控制器2262168/start44143263已实核存活，00:11:33+08快照242/31872 RUNNING，选用16个启动时空闲CPU槽3/5/6/9/10/11/12/14/15/17/21/22/23/29/32/33，无GPU。原异常train101576现完成静态检查和独立审计，结果STATIC_FAILURE_PRESERVED/topology_mapping_error，仍未导航通过；首个有动作完成记录train40071真实143动作及独立143回放通过，用于确认新执行链路，不能当全量结果。启动回执geometry-schema-continuation-launch-20261019.json。

原始标注、场景、全局环境、权重、原模型及网格profile不改。此兼容修复没有新增规划算法或放宽碰撞标准；当前远端已同步修复与此前本地准备的审查报告模块，并再次冻结至新段终态。未启动新模型评测、commit或push。阶段仍进行中，不把剩余31872完成单独当整个37016验收。


### 2026-10-19T00:40:13.428712+08:00 多执行身份的完整集合合并审计准备

为新身份续跑准备只读最终合并审计review-full-lineage，代码/公开配置仅在本地oracleAdapter/src/oracle。显式锁定原父manifest1e2d9c…和续跑04db8155…以及原1839/1223/33954共37016任务，要求父5144与子31872集合无遗漏/重复/交叉；逐任务原始含义仅允许module_source_sha256这一执行身份字段改变，目标/姿态/特权/数据/profile等变化拒绝。每条结果保留真实producer run/manifest与原输入/执行输入hash，不伪称单一源码。

完整子运行及独立full review未就绪时，入口在读取全量/生成结果前明确拒绝，不能用小夹具或部分数据宣称原实验完成。最终将分别核对组件审查、原始回执/输入/源码、每任务动作/回放数及累计CPU上界；普通失败保留，分组效果和资源按实际信息条件及执行版本记录，不作跨版本随机化性能对比。记录的参考顺序也不等于完整自然语言语义或原论文A重初始化。

失败回归已保留，随后本地104项CPU测试通过。准备回执outputs/oracleAdapter/lineage-review-preparation-v1明确full_data_merge_executed=false；只有代码与CPU门槛准备，尚未对真实全量执行最终合并，未覆盖远端冻结的101测试版本。真实集成仍待full-continuous-reference-v2全部终态后完成。无新导航、模型评测、commit或push。


## 2026-10-20 Oracle专项阶段更新

全33954 Landmark执行/独立审计完成，严格20911通过、旧严格通过退化0；不同映射/信息组分别记录。固定优先级配对0恢复0退化，未推广；四相机视点原33查询全因超0.5米范围拒绝，无映射修复。原R2R/RxR封存哈希保持，研究结果不覆盖模型成绩。174CPU回归通过；全导航门槛未过、无自动push。详见同一导航专项conclusion及oracleAdapter/docs/FINAL_RESULTS.md的2026-10-20章节。


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


## 本次实际发布检查（2026-10-20）

远端工作区Oracle CPU217项、根CPU32项全部通过；从暂存树导出的干净副本同样217+32项全部通过，无跳过。干净副本使用既有case1 runtime，不是新安装环境或新导航实验。实际暂存文件逐项审查：无数据/权重/环境/outputs/backup/本机配置、无符号链接、无大于10MiB文件；常见私钥/GitHub/API/AWS令牌和带凭据URL模式扫描无命中（模式检查不构成绝对无秘密保证）。.gitignore正反例通过，公开JSON配置/结果索引可提交；许可文件及来源记录保留。阶段报告5项关键证据路径及SHA256逐一匹配。

Git按既有.gitattributes规范化文本行尾为LF，历史工作区/源码归档保留原字节。发布树的blob/hash和运行时原始source SHA分别记录，不能把Git导出源码摘要冒充旧运行源码摘要。全部历史诊断源码保留用于证据追溯，活跃Oracle仍仅oracleAdapter/src/oracle。以上检查只支持本次阶段快照发布，不提升任何导航失败或科学验收状态。


## 2026-10-24 固定划分复测与结果迁移（进行中）

新正式结果唯一入口为case1/results-show/MODEL_TEST_RESULTS.md，原docs/results已完整迁入；records.json及旧run状态保留，旧路径在历史结论中只作历史记录，不再写入。当前计划/结论为docs/zx/2026-10-24-1-{plan,conclusion}-固定划分基线测评与结果归档.md。

用户确认沿用已发布endpoint9，并授权建立/data/zy/vln/data/checkpoint-choice/VLN-awareVLN。该副本已物化R2R1839、RxR-US1223，14叶子不重选、不丢失。6124源记录/GT哈希核验通过，9标注和5GT修正逐字段记账；原VLN未变。副本内dataset.yaml与evaluation.json指向实际复制的修复数据/GT及冻结profile，场景/权重不复制。原VLN引用的audit目录缺失如实保留，新副本当前验收不冒充原历史验收。

历史模型成绩按新划分重算已进入results-show/checkpoint-choice-historical.md，明确不是本次新推理。单块A1/A2/A3/B1/B2/B3/Remaining与A1+A2/A/B1+B2/B/Full分开列，累计指标从逐任务结果计算。R2R旧retracted保持；新复测也不会自动证明5处严格离网问题已消失。

新入口scripts/checkpoint_choice.py按精确叶子ID运行；来源chunk固定1/0，实际worker/trainer/dataset路径及SHA与manifest匹配。受保护启动的results-write只开放results-show，模型worker不得携带行政写权限。40项CPU回归及3模式真实权限测试通过；前39项后增加挂载别名反例为40项。

首次预检失败为旧scene_view只按profile内容命名：当前只读bind mount恢复可用，同一profile在普通shell解析原始路径、保护namespace解析.shared-ro；旧视图链接指向前者，字节哈希相同但严格路径比较冲突。保留旧链接、旧日志和诊断；本次独立视图以实际目标路径加内容身份命名，不修改旧工具或profile。普通shell探测的打印文字误称Protected，实际当次未启用保护；真正保护环境复验由prepare-v2及后续gate提供，不能使用该文字代替执行证据。

GPU仅4–7完全空闲卡、最多4张，CPU总不超64。所有已完成旧run保持封存；新任务未完成前不登记新成绩、不提前push。完成后按受控清单归档本阶段可再生成中间副本，保留运行依赖/失败/源码快照/验证回执，再审查Git并发布。


## 2026-10-25固定划分endpoint9完整baseline复测

本轮固定评估分区完整执行R2R1839、RxR-US1223；动作语义审计、独立轨迹指标复算和validation均PASS。两数据集普通导航失败分别632和396，非有限/运行异常0。完整结果、A/B/Remaining各块及新旧逐任务差异见根results-show/MODEL_TEST_RESULTS.md。与旧endpoint9运行task_key、模型、配置、profile、benchmark及427个模型/评测策略冻结文件匹配；五项逐任务指标、终止、步数和模型调用数差异均0。全部trace SHA分别有变化，原因未逐字段确认。旧R2R因独立严格几何5离网发现保持retracted；新旧数值一致不取消该限制。Oracle/Landmark和原数据未改。

本次固定分区副本VLN-awareVLN保留原ID，仅RxR endpoint9修复9 annotation/5 GT；原VLN未变、原audit目录缺失已披露。成本采用每worker结束回执的批次墙钟时间与控制器端到端墙钟分列，批次有重叠，已退出进程CPU秒无法完整恢复，不估填。
