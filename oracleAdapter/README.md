# OracleAdapter

> **2026-10-20授权更新**：用户要求先发布当前阶段快照，并明确“可以先采纳”pRb候选。该候选已被阶段采纳用于后续Landmark研究，2条已知退化与全部失败保留，零退化及全科学验收仍未通过。下文此前“未采纳/无发布资格/未push”是相应历史时点的结论；当前范围、原模型封存及实际发布核验边界见[阶段发布说明](../docs/PUBLICATION_SNAPSHOT.md)。

本模块独立放在 `case1/oracleAdapter`。活跃实现、任务契约及全部公开配置统一在 `src/oracle`；历史 `tests/landmark_diagnostics` 只作为不可变来源与数据证据，不被新入口导入执行。

当前状态（2026-10-20）：完整Landmark33954验证与独立审计结束，严格20911通过；旧20507全保留，新增404按映射/信息组分开归因。查询缓存显著降低已记录教师CPU成本；全局连通/90%尚未验收。后续固定权重两臂均8/16、0恢复0退化，未推广；四相机视点33查询全部超原0.5m范围，无新映射。调度等待优化已实现，所有已启动任务均终态。原R2R/RxR封存、不重测。完整记录见[研究结果](docs/FINAL_RESULTS.md)最新2026-10-20章节、[295条分析](docs/REGRESSION295_ANALYSIS.md)及父目录同一专项conclusion；不自动commit/push。

最新受影响场景验证（2026-10-20 05:24+08）已完成741/741：714控制保留340旧成功，27起点候选仍0整路成功，33707动作完成独立回放。实际使用32空闲CPU槽，当前已终态。起点首动作改善不等于全路恢复；详见FINAL_RESULTS最新收尾段及outputs/oracleAdapter/olb-scene741-closeout-v1。

最新算法对照（2026-10-20 05:52+08）已完成：固定soft-priority与控制均8/16，恢复0/退化0，总CPU成本未改善，按停止条件不推广。全部32次实际执行及独立回放审查完成；原资源预留错误和有据续作分开保留。未来调度已增加预算并发上限，200CPU回归通过。详情见FINAL_RESULTS最新条目。

最新pRb660完整审计（2026-10-20 10:14+08）：98严格通过，新增31/旧成功退化2，推广门槛未通过。全部23290动作独立回放误差0；两退化的旧计划在新profile实际落点也发生源接触。完整成本与失败分类见[PRB660_RESULTS](docs/PRB660_RESULTS.md)。该轮及诊断均终态，未采用候选或push。

## 实际目录

```text
oracleAdapter/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── run.py                       # 仅负责导入统一入口
├── docs/                        # RELATED_WORK与SOURCE_IMPORT：来源、实际代码和适配边界
└── src/oracle/
    ├── contracts.py             # 目的、任务、特权信息、动作、预算、失败与证明类型
    ├── registry.py              # 能力注册及契约拒绝检查
    ├── entrypoints.py           # 统一入口、启动绑定、源码快照、成本与失败记录
    ├── adapters/habitat/        # 原生状态和动作接口
    ├── adapters/landmark_rxr/   # 身份、出现次数、显式子段连接边
    ├── adapters/rxr/            # 官方原始 Guide 来源与逐条身份核对
    ├── common/                 # 无损状态键、完整上下文与冻结证据
    ├── teachers/ordered.py      # 按序参考/landmark真实动作教师，禁止中途重置
    ├── research/route_study.py  # 冻结开发清单、成对调度、逐任务独立回放
    ├── planners/action_space.py # 有限预算的标准动作搜索核心，输出候选计划
    ├── verification/           # 导入绑定、固定线性扫掠、有理数接触证书
    ├── configs/                # 公开来源/任务/协议/实验设置；local子目录忽略提交
    └── tests/                  # 契约、混叠、顺序、证书、缓存与来源完整性回归
```

原始数据、权重、场景、构建缓存及运行轨迹不进入源码。研究输出在父目录 `outputs/oracleAdapter/<run_id>`；官方缺失参考资产缓存位于其中的 `reference-cache`，通过来源回执复用，不重复下载。

## 可复现入口

以下命令在服务器 `case1` 根目录运行，使用既有受保护运行环境；不安装或升级正在运行模型的环境。

```bash
scripts/with_runtime.sh runtime/awarevln/bin/python -B oracleAdapter/run.py describe
scripts/with_runtime.sh runtime/awarevln/bin/python -B oracleAdapter/run.py self-test
```

数据/原生诊断入口必须显式指定 `--case-root /data/zy/vln/case1` 和新的 `--output /data/zy/vln/case1/outputs/oracleAdapter/<run_id>`。已有运行应直接读取回执，不为查看结果而重跑。

| 命令 | 作用 | 不代表什么 |
|---|---|---|
| `audit-landmark-identities` | 完整33954身份、8034缺失记录、461视点和子段出现次数台账 | 不代表连续路线已修复 |
| `audit-source-connectors` | 对原完整路径中的子段间边作显式记录，保留全部子指令 | 不代表连接边可执行 |
| `fetch-rxr-guides` | 缓存此前未在指定共享注释目录找到的官方原始Guide文件；校验SHA/ETag并复用缓存 | 不修改共享CE数据，不推断历史过滤原因 |
| `audit-original-rxr-identities` | 与冻结的原始Guide逐条核对身份、路径及文本差异 | 不提供缺失的Habitat连续动作 |
| `probe-native-aliases` | 复核冻结状态混叠反例，执行原生动作并重放，检查接触证书 | 不代表完整路线通过或搜索完备 |
| `audit-continuous-assets` | 全33954逐条核对官方CE episode/GT及动作—位置索引语义 | 不代表官方动作可按当前体型/滑动协议执行 |
| `audit-heading-conventions` | 按稳定身份核对Guide heading与CE四元数/安装环境轴定义 | 不证明Landmark自身初朝向与Guide相同 |
| `audit-landmark-heading-lineage` | 保留Landmark heading/headings、核对其自身及Guide关系 | 数值差异不自动等于数据错误，不自动覆盖任何heading |
| `prepare-route-study` / `run-route-study` | 冻结并执行有限开发任务成对对照，每条另进程回放 | 不代替全3062/33954及盲测泛化 |
| `report-route-study` | 核对归档源码、任务/环境/结果/审计身份并分别生成成对效果及成本 | 不混算不同目的，不丢弃失败成本 |
| `prepare-official-study` | 固定历史192条范围，133官方动作实际重执行、59缺源保留 | 不将不同初态的旧Oracle成绩作为算法对照 |
| `prepare-portfolio-study` | 冻结同信息条件下的受保护建议控制臂及固定搜索接续臂 | 相同预算上限不表示实际计算相同，不能提前声称恢复 |
| `prepare-search-ablation` | 在相同物理初态/目标/profile下移除官方动作载荷与特权 | 属于不同实际信息条件，不能混入同信息主表 |
| `audit-capability-ablation` | 核对三方法物理任务身份、真实结果集合及互补性 | 成功集合的并集不是一个执行过的方法，不登记其成绩 |
| `audit-execution-evidence` | 只读核对历史逐步日志与冻结输入/结果 | 不补造历史producer哈希或实际reset计数 |
| `prepare-execution-gate` | 验证真实初始化计数、初姿态及原始日志绑定的工程入口 | 单例工程门槛不是新算法成绩或全量替代 |
| `audit-unified-inputs` | 生成37016条源绑定JSONL和偏移索引，保留未解析坐标 | 输入库存不是可执行manifest或运动验收 |
| `prepare-full-validation` | 冻结完整输入、先验适用分支、源码、预算及逐任务成员证明 | 编译完成不代表导航通过 |
| `run-full-validation` | 流式执行/独立审计，按身份与持久日志恢复未完成工作 | 普通失败不择优重跑，不触发模型测评或push |
| `review-full-validation` | 核验全覆盖、逐任务输入/原始流/静态与运动回执 | 队列结束与全部导航验收通过分别报告 |
| `classify-official-study` | 全192逐条分类及旧/新验收口径对照 | 不能把严格接触或有限失败当物理不可达 |
| `diagnose-official-contacts` | 对已记录失败分离实际落点接触与仅线性扫掠接触 | 不更改轨迹/门槛，不追加原生导航 |

每个研究运行保存实际入口、导入路径及哈希、有效配置、特权信息、预算、资源、源码快照和输出绑定。源码变化或身份不符时拒绝；失败产物保留。

## 已有证据与限制

- 全33954条Landmark身份台账保留；25920条精确匹配已安装CE Guide，8034条未匹配；461缺图视点中365有官方连续参考位置，96仍缺直接对应证据。
- 官方原始Guide三文件共96507569字节已冻结。全部33954条（含8034）在原始Guide中的身份、场景、split、语言、path_id和有序路径一致；710处文本差异仅为边界引号/空白。CE缺失原因仍未知，不能称为已证明的官方过滤。
- `train:43144` 的原完整路径有一条子段间连接边。独立映射候选显式保留它，其他33953条精确映射无退化；原标注未改，连接边尚未完成原生路线验证。
- 25对旧状态键混叠反例完成100次原生调用（含独立模拟器实例回放），全部仍具有相同取整键但不同合法后继；4处接触有有理数证书交叉核验。这不是完整路线恢复，回放和几何模型仍存在各自证明边界。
- 早期记录为73项CPU回归；收尾实际为104项（当前配置）；覆盖契约、状态混叠、剪枝、几何证书、原始来源、顺序/零长度边界、官方动作转换、固定切换、来源篡改拒绝、分母/信息条件分组、朝向与四元数、原字段保留、真实初始化计数、原始日志一致性、追加日志中断恢复、任务成员证明、PID复用/僵尸识别、预算结算及统一输入不删除缺坐标记录。self-test临时文件固定在case1/.cache/oracle-self-tests。

固定12任务×2状态键开发对照已完整执行并独立进程回放，共1009实际动作、位置回放误差0。端点参考两臂均4/8，Landmark顺序两臂均1/4，恢复0/退化0；无损键耗时/CPU未显示总体优势。开发报告在`outputs/oracleAdapter/route-development-paired-report-v1`，不同任务类别分别统计，所有失败纳入成本。首次运行因契约frozenset编码失败停止，失败及source.zip保留；更正编码后的运行在`route-development-v1-serialization-retry`，已终态，不重启。

官方动作资产审查在`outputs/oracleAdapter/continuous-assets-v1-source-metadata`：全33954保留，25920精确匹配CE及GT且schema通过，8034无匹配CE。GT locations是初始位置加每次前进落点，不含转向中间状态。6555条有语音时间戳NaN，均在timed_instruction元数据；源指纹显式记录，源文件不改，导航有限性规则不放宽。官方RxR体型/滑动与当前固定协议不同，见RELATED_WORK和公开来源配置，不以30°拆两次15°声称运动等价。

Oracle与映射分别归因、分别验收。有限组合及同初态消融已完成，新全3062/33954及原Landmark初态下的适配仍待完成；创新尚未成立。原R2R/原RxR模型结果保持原身份，不由本模块结果替代。

固定组合`outputs/oracleAdapter/guarded-prefix-development-v1`已266执行完成，另59缺源保留192来源范围；没有按新结果挑样本。两臂共享初态/目标/profile/实际官方动作信息及总上限，组合90/133、控制51/133，保留51+恢复39/退化0。执行CPU445.828→2530.914秒，实际增加计算必须披露。第一条不合法建议在执行前被拒绝，组合从当前未违规状态接续；独立回放核验每动作来源与单向切换。原始证据及报告均保留，不重启终态。

`matched-search-ablation-v1`已133/133终态，移除了官方动作输入/特权，保留相同物理任务和上限，54通过、执行CPU4645.626秒。`capability-ablation-v1`逐项核对三方法：组合保留纯搜索54个成功，另有8条两个单方法都失败而组合成功。不同信息条件分别报告，不声称这是同信息算法优势，也不登记事后并集为方法。全部初态属于明确的Guide/CE官方回放谱系，不能当作原Landmark全量成绩。

`source-heading-audit-v1`核对全33954：25920有CE的Guide方向与CE xyzw一致（最大2.11e-8rad），8034无CE对应。`landmark-heading-lineage-angular-v1`进一步显示28057个Landmark heading在同弧度假设下与Guide不等价；59条header与首subheading也不同，均保留。旧v11清单的全部33954 heading与原Landmark字段一致，3条实际轨迹样例转换也一致，不据此否定旧v11。全量前必须保持Landmark自身初态并显式处理官方参考初态的适用条件，不得覆盖成Guide值。

`unified-input-inventory-v1`已完整生成37016条源绑定记录（1839 R2R、1223 RxR、33954 Landmark）。Landmark33213条坐标齐全、741条缺坐标保留；齐全不代表连通或运动通过。保留原目标坐标和Landmark原heading，明确完整reference出现顺序及landmark边界。新生产者记录实际显式restore次数、初始旋转及executed.jsonl哈希；独立回放核对原始流。556条历史记录的63897动作只读一致性核查无偏差，但旧producer未捕获日志哈希的限制保留。

**完整连续验证已启动**：`outputs/oracleAdapter/full-continuous-reference-v1`，manifest SHA `1e2d9c826aa71f04ad3d5bd9c123fbae2ce339dffd14047d9a187c9ae534f125`，全部37016条保留，最多16个空闲逻辑CPU槽位、无GPU。初态兼容时使用官方动作建议（RxR1185、Landmark2786），其余运行既有有界搜索，绝不为复用动作改变任务初态。追加式journal与身份许可已接入调度；4任务工程队列验证了干净检查点恢复，首次静态失败没有重跑或覆盖。突发父进程崩溃接管分支尚未故障注入，不夸大其测试覆盖。全量执行、最终独立review和全部导航门槛仍待完成；运行中冻结源码/config/输入，不重启健康任务。

官方动作严格复验已完成：`official-reexecution-strict-v1`重执行133条及逐任务独立进程回放，51通过、82失败；另59缺CE身份保留在192分母。15985实际动作的位置/朝向回放误差均0。82失败为80源接触和2原生运动限制；`official-contact-causes-v1`进一步复核为62实际落点接触、18仅线性扫掠接触、2运动限制，接触复现分歧0。全部80源接触位于前进动作，不能笼统归因转向投影。旧109较弱原生门槛PASS中51仍通过、58未通过严格门槛；旧24失败未恢复。保持历史官方回放初态和父profile，未混入不同初态/网格的Oracle结果。报告在`official-reexecution-strict-report-v1`，全192分类在`official-reexecution-classification-v1`。这验证了可复用计划的实际边界，不是新的算法收益；18扫掠类仍需解释原生台阶语义，当前验收没有替换。


### 本地已验收、待远端冻结运行结束后同步的来源审查入口

`audit-graph-lineage`和`audit-raw-graph-paths`只读核对原始/发布图与原任务身份，已完成461视点及33954路径台账；不提供替代落点、不修改正在运行的全量验证。公开配置在src/oracle/configs/experiments/graph_lineage.json，代码在adapters/landmark_rxr/graph_lineage.py及graph_path_audit.py。当前本地78项CPU回归通过，远端仍使用全量启动时的冻结代码，不能在远端提前调用新命令。证据见outputs/oracleAdapter/original-graph-lineage-bound-v2和raw-source-graph-paths-bound-v2。


本地新增 `audit-reference-lineage`，从官方CE源重新构造完整任务身份及reference出现索引。25920条对应、8034条缺源保留；7264节点候选与旧表完全一致，未发现额外候选。回执 `outputs/oracleAdapter/continuous-reference-lineage-v1`；本地81项CPU回归。此入口同样尚未同步远端冻结源码，不代表连续运动验收。


### 全量收尾效果与成本报告（本地待同步）

`report-full-validation --case-root <case1> --input <run> --manifest <independent-review/validation.json> --output <new-report>` 只接收完整、已通过独立覆盖审查的回执。按数据集/split/语言/任务目标/profile/实际特权信息/方法分别列出有效分母、通过/失败、耗时P50/P95、搜索次数/展开、原生预演、源检查、实际动作、回退原因及进程峰值内存。执行与审计的全部尝试成本另列，静态失败不补成零成本导航。控制器未记录实际CPU，其预算预留不能当实际值；贪心内部探测计数仍缺失。

已用既有4任务工程结果的只读导出验证，原任务未重跑。输出在`outputs/oracleAdapter/full-controller-engineering-cost-report-v2`；这是工程报告验证，不是37016全量成绩。显式`--source-case-root`仅用于保留原始字节的跨平台导出路径重定位；它不会改回执或运行导航。旧工程回执缺少后加字段，首次报告失败已保留，兼容分支显式记录字段缺失；当前全量格式缺字段仍拒绝。86项本地CPU回归通过。待远端冻结全量终态后才同步活动源码和执行正式收尾报告。


### 独立打包的已验证范围

本地干净导出与离线wheel已验证：`outputs/oracleAdapter/clean-export-build-v1`。源码导出和wheel解包入口在`python -I`下分别通过89项CPU测试，111源码/公开配置成员逐一哈希一致；构建夹具中的`configs/local/nested/do-not-package.json`被排除。pyproject声明NumPy，并显式排除机器配置进入wheel。构建使用`pip wheel --no-index --no-deps --no-build-isolation`，没有安装/升级依赖或访问包网络。

本次CPU验证使用既有本机Python3.13.5、NumPy2.1.3、setuptools72.1.0，不代表原生Habitat已在该环境运行。原生任务继续使用服务器冻结的case1运行环境；打包不自动安装或替换Habitat。每次实际运行以manifest记录的环境、源码和资产身份为准。打包修改尚未同步远端活动模块，也不触发模型评测或发布。


### 已完成端点子集与仍在运行的父任务

`outputs/oracleAdapter/endpoint-cohort-review-v1/report.md`已核对父完整运行中的3062端点任务，保持父37016任务manifest和源码身份，没有替代分母。统一入口`review-completed-endpoints`使用公开endpoint_cohort_review.json校验完整选定集合与原始回执；只是已有执行/独立回放证据归集，不执行新动作。R2R1280通过/559失败，RxR654通过/569失败，244516动作回放0，失败全部保留。严格通过总数未达到旧v3；控制器/墙钟预算非完整匹配，不宣称全量收益，不当模型SR。Landmark33954与父完整审查仍待结束。本地95CPU回归，远端新审查入口待冻结运行终态后才同步。


### 几何回执兼容修复及新身份续跑

旧统一运行v1在train:101576/XcA2TqTSSAj读取旧式几何回执时，因native_geometry_path字段不存在而停止。文件没有丢失：冻结catalog已给出路径/hash，原回执以native_triangle_dump_sha256记录。新加载器只支持明确的catalog绑定格式，拒绝缺失来源或哈希/场景不一致；不猜文件名、不改几何或门槛。

本地/服务器101项CPU回归通过；geometry-schema-catalog-v1验证全71场景（70标准、1历史格式），解码三角面和包围盒与规范控制字节一致。搜索、原生动作接口、碰撞核心及物理协议文件保持；6个调用模块的AST差异仅为传递catalog，接触判定AST相同。原运行10289个已拥有进程身份检查无存活者，旧结果/源码快照保留。

`full-continuous-reference-v2`执行剩余31872条，父prefix-review审查封存5144条，二者完整范围仍37016。普通失败不重跑，不复制旧PASS成新PASS。新manifest SHA04db815594c8e89c095eba6ab7b6b4a1cfa28dbff7a2ccfec35e8523bcb7c31a，控制器2262168/start44143263。剩余CPU预算2437006秒，已扣原运行154993.248秒保守账目；没有重置720CPU小时总额度。每剩余phase只给一次新基础设施尝试，额外错误停止审查；导航单任务预算不变。

当前第一条原异常任务已成为有独立审计的静态拓扑失败，不能计作导航恢复。新运行已有实际143动作及独立回放通过的任务，用于确认真实执行链路。最终需分别核对两执行版本并合并完整不重复任务集合，再报告原1839/1223/33954分母；不能把子运行31872完成当整个研究完成。旧v1不可用新源码原身份重启，源码再次冻结至v2终态。


### 两执行身份的最终合并（本地准备，真实全量尚未执行）

`review-full-lineage --case-root <case1> --input <full-continuous-reference-v2> --manifest <child-independent-review/validation.json> --output <new-logical-review>`要求完整子运行与独立review先完成，才验证父5144+子31872恰好覆盖原37016。公开配置lineage_review.json锁定两manifest；目标/姿态/数据/privileges/profile等必须不变，仅执行源码标识可不同。结果逐条保留生产版本，资源按版本/信息条件分别统计，不伪称单源码或复制PASS。当前仅本地104CPU测试通过，远端仍冻结在续跑时的101测试版本，真实全量合并与集成尚待终态。准备证据lineage-review-preparation-v1。


## 最新有限研究入口与终态证据

- `prepare-priority-study` / `run-priority-study`：固定16个Landmark train任务、两种优先级的开发比较；已在reference-priority-development-v2完成，不为查看结果重跑。
- `diagnose-camera-surface`：固定4视点/33历史查询的拒绝分类；已在camera-surface-rejections-v2完成，不扩大范围或重复采样。
- 当前没有后台实验待完成。优先读取outputs/oracleAdapter/finite-stage-closeout-20261020/validation.json和docs/FINAL_RESULTS.md最新章节；新的实验必须有新的根因依据、有限计划和身份/预算检查。
