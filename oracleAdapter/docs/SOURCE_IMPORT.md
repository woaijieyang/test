# 实际复用与源码导入说明

本文件记录已经使用的实现；调研候选不等于已移植。

| 活跃组件 | 实际来源 | 本轮变化与边界 |
|---|---|---|
| NativeAdapter | 既有case1独立环境中的Habitat-Sim0.1.7；sim提交856d4b08c1a2632626bf0d205bf46471a99502b7 | 调用原生动作/PathFinder；不修改安装库，不启用渲染，不替换模型观测 |
| 动作搜索核心 | 标准有预算A*的独立小型实现 | 接受适配器提供的隐式状态转移；返回候选计划，不声称算法创新或完备性 |
| `verification/projected_distance.py` | `tests/landmark_diagnostics/projected_distance_reference.py`，历史SHA `8c2cfa0e5a3222e2e686dc22a5fb6bf0ce2b4d8dd097a90e3e0f39bc88bae266` | 保留数学定义与阈值；仅改包内导入/文本编码，旧文件不动；活跃SHA见geometry-port.json |
| `verification/linear_sweep.py` | `tests/landmark_diagnostics/swept_cylinder_reference.py`，历史SHA `b73833d7dbdc92704c40fbf7fdd372e3791f68a64fbb0ccc6490a3d2b707f383` | 保留数学定义与阈值；仅改包内导入/文本编码，旧文件不动；活跃SHA见geometry-port.json |
| `verification/contact_certificate.py` | `tests/landmark_diagnostics/swept_cylinder_witness.py`，历史SHA `6e63da3922d27492fe7e8361fd10e0f3c984d2a3e5a9ab93cf5bcf35a2600484` | 保留数学定义与阈值；仅改包内导入/文本编码，旧文件不动；活跃SHA见geometry-port.json |

- 上述三份几何函数来自本case已有研究实现。新入口不exec/import历史脚本；旧文件继续供历史回执追溯。
- 有理数证书实现与线性距离实现代码不同，但共享几何模型和输入；不能因此宣称物理判定完全独立。
- 官方仓库只作冻结参考与依赖审查，尚未直接复制ETPNav、OMPL、Sim2Sim控制器进入活跃实现。相关许可证、提交、实际代码路径见configs/sources/upstream-lock.json及RELATED_WORK.md。
- 新研究源代码和配置在oracleAdapter内；原AwareVLN源码/配置、权重、原始数据、场景和旧结果不改。原始Guide缺失参考仅缓存在case1自有outputs目录，按内容SHA和provider generation锁定并复用。
- 每次运行的源码zip是历史证据，不是另一套活跃实现。修改代码后必须生成新运行身份，不能回写旧结果。

## 协议文档与实际生成身份的区别

冻结VLN-CE README的“Required Task Configurations”明确列出挑战动作：30°转向、0.25m前进、30°抬头/低头及480×640 RGBD。因此0.25m有README来源支持；它不是从未显式设置forward_step_size的RxR YAML单独推断出来的。

冻结RxR YAML中的0.88m/0.18m、slidingFalse是作者提供的任务配置。它本身不是当前全局GT文件的生成回执；本地GT没有逐文件记录生成时的源码、navmesh、身体和滑动设置，不能仅凭YAML断言这些就是GT生成时实际生效的参数，也不能单独把当前接触归因于体型差异。本轮保存文件内容身份，按当前固定协议重新执行验证，保持这项来源限制。

RxR冻结README定义源heading为z-up、面向+y时为0、向右转为正弧度。[Habitat官方坐标教程](https://aihabitat.org/docs/habitat-sim/coordinate-frame-tutorial.html)定义右手y-up、前向-z；[Habitat-Lab接口](https://aihabitat.org/docs/habitat-lab/habitat.core.simulator.Simulator.html)声明旋转系数xyzw。已只读检查安装的Habitat-Sim0.1.7常量UP=[0,1,0]、FRONT=[0,0,-1]。轴旋转不包含相机到脚底的高度偏移，也不证明外参矩阵方向；相应数据级核验须另行保存完整结果，不能靠经验改符号或高度。

## Landmark初朝向及发布资料的边界

全量字段核查显示Landmark拥有自己的heading和每个sub_path对应的headings；这些字段不等于原Guide heading。原论文3.1允许标注者调整朝向，并说明对部分RxR错误作了修订，但没有给出每个字段差异的生成日志。官方main分支仍为6c9c6f5…且只有README；完整issues查询只发现关闭的#1数据发布请求，不能据此编造heading生成器或原评测实现。

官方补充材料PDF已冻结（SHA256 `71ae45a27f71fa957e675cdf131a88bbb423bc63378c098f1dafec4342560cb5`，19923337字节，9页）。其中声明数据CC-BY许可，但未指定版本；这不等于README-only仓库提供了可复用代码许可证。首次pypdf提取出现不可编码surrogate，改用已安装PyMuPDF并保留原PDF。没有找到heading/headings数值语义的详细定义，不能自动统一这些字段。

原Matterport3DSimulator官方仓库补查提交为`589d091b111333f9e9f9d6cfd021b2eb68435925`。其README确认heading弧度与+y/z-up约定；NavGraph.cpp按row-major pose输入提取原相机位置，并使用included/unobstructed定义图邻接。该加载器不读取JSON中的height字段，不能仅凭字段名称将它当作已验证的相机离地高度。现有Case1 original-connectivity缓存只覆盖部分场景；pRb原图文件不在该缓存，场景.house元数据存在。后续优先核对已存在资产及源码来源，不重新下载已有场景或凭空造连通边。


## 原始图来源补齐与逐点核对（2026-10-18）

上述“部分场景缓存”已补齐为71场景：复用6份旧缓存，65份从Matterport3DSimulator冻结提交589d091b111333f9e9f9d6cfd021b2eb68435925获取，总20066429字节。每份按冻结Git tree的blob SHA1/文件大小验证，并保存SHA256；没有下载场景、图像或权重。来源回执在outputs/oracleAdapter/reference-cache/mattersim-original-589d091/fetch-receipt.json。原始图用于身份/离散邻接解释，不是新连续网格。

original-graph-lineage-bound-v2对全部461缺失视点确认：原始图均同名存在且included=true，发布适配图均无同名ID。既有8011视点的相机位置与官方pose经[x,z,-y]轴转换最大差约1.64e-14m；没有应用高度偏移。改名、合并、替代节点的来源证据仍未建立，不能因为位置近而赋予这些类别。

raw-source-graph-paths-bound-v2重新从3份原始Landmark文件提取全部33954路径，8011唯一视点及461缺失集合与旧台账完全一致。原图33954原路径邻接均成立；发布图11689条缺ID、14491条ID齐全但缺原直接邻接、7774条原直接邻接全部存在。缺直接邻接不代表没有其他图路径，更不代表物理不可达。此审查未模拟FOV、10离散步预算或重初始化，因此不是论文A测评。

pRb edge_51在发布图中存在，但原图没有直接边。660原任务中直接使用此边0条，包含两个端点21条；原始图最少跳数路线经c327988cdf454a77a0094af6e906f257及658505895e5a449ab39a76b1e1f337a5两个中间ID。没有将该路线代入任务，也没有宣称原生动作已通过。

新图审查代码仅在本地oracleAdapter/src/oracle完成，78项CPU回归通过；远端全量冻结期间未同步活动源码。证据及源码快照可同步到outputs，但不能据此声称远端活动入口已经具备新命令。初次v1审查未保存完整启动导入绑定，保留原回执；bound-v2补充实际入口/导入路径/哈希/信息契约并只读重审，全部证据输出字节与v1相同，0新增原生动作。


## 连续reference逐次来源复核（2026-10-18）

本轮从三份共享只读RxR-CE Guide源文件投影稳定身份和完整reference_path，并以原始Landmark33954条逐任务复核，回执outputs/oracleAdapter/continuous-reference-lineage-v1/validation.json（SHA40305cc269558d46590396fe59acf64319d361a3b498b6711ac8655149dbf72f）。25920条split/instruction/path/scene/language全部一致且reference数量对应；8034条无匹配CE身份保留，没有用文本或空间最近点补匹配。逐任务reference occurrence索引、子段区间和365个缺发布图视点的每次来源出现均有台账。

从实际CE来源重建7264个视点候选集合，与旧native-mapping.json全部逐值相同；多坐标候选节点0、新增节点0、旧节点未重建0。461缺发布图ID中365有稳定身份加序列索引的CE坐标来源，96没有。此前official-multiple-anchor-check只检查旧表；本轮从源数据重新构造，仍无隐藏额外候选，不应继续反复尝试“旧表遗漏多候选”假设。全部33954原路径没有重复ID；25920匹配参考也没有连续零长度段，但实现仍保留逐次索引，并以合成回环/零段反例测试防止未来数据被合并。

重要可信边界：CE reference_path未逐点携带原始viewpoint ID；对应依据是稳定任务身份、完整路径顺序和相同长度，并非作者提供了逐节点转换回执。冻结VLN-CE公开树未发现原RxR转换程序，不能编造该实现或把坐标相同当成物理可行证明。新台账使用IDENTITY_AND_ORDINAL_REFERENCE_ACCOUNTED分类，未生成新目标、未改变任何任务坐标、未将GT旋转/位置重置到Landmark任务中。8034缺CE的历史原因仍未知，原Guide身份已经匹配不等于连续资产存在。



## 2026-10-20 finite-stage implementation provenance

`planners/action_space.py` retains the existing native-transition search and Pareto labels. The fixed `priority_weight` parameter changes heap priority only; weight1 is the unchanged default, weight2 was a conventional weighted-search development candidate, with0recovery/0regression on the fixed16. It is not promoted or claimed novel. Search counters do not issue additional native queries. `research/priority_study.py` freezes identical task streams, verifies real launcher bindings, and reuses existing full-worker/preflight/replay machinery.

`research/full_run.py` now uses the actual owned Popen handle for prompt exit waiting while preserving PID/start_ticks and pidfd timeout checks. Legacy recovered phases without a handle retain identity polling. Scheduling/resource effects are reported separately from algorithm coverage. The maximum32worker setting remains bounded by task count, observed idle CPUs, available memory and the overall64logicalCPU limit.

`verification/camera_surface_diagnostic.py` contains copies of three small historical Case1 projection helpers, not imports from the historical tree. Original sources: tests/landmark_diagnostics/bounded_triangle_projection.py SHA360263e04160acdadaccae42cb2c73ebf1a261b809ad9b95652bf87eada82369 and cylinder_contact_height.py SHAbe6142466330f2b072d8aa6490bf88bc8bcb4c834efee0ee0c3ab7432f9c9fe2. All three function ASTs match under the frozen Python3.10 parser. The initial Python3.12-generated fingerprint mismatch was rejected before native queries and preserved. Public config binds the parser version and historical receipt/profile. No historical source file is imported at runtime.

The camera diagnostic reuses the canonical rational witness implementation for a separate cross-check of six current-navmesh triangles, plus an exact supporting-plane lower-bound check. Its2m slab and0.5m radius describe the historical camera search domain, not a new robot body or motion-acceptance protocol. All33original queries fail the horizontal camera bound;0targets adopted,0navigation actions. This does not prove original-scene physical impossibility. No external algorithm code, package upgrade, model, raw scene or original annotation change was introduced by this finite stage.
