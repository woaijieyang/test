# R2R 专项整改记录

## 本次实现边界

基于 `a1139e1eb2897e8bbaf2a4fbf6eb2e77b00295e8` 完成模块归属、现有规则细化、模板证据、独立Reviewer作者逻辑及来源关系互补检索。Shared通用契约、通用角色Prompt、Adapter、Renderer、输出Schema、Actor及RxR专属行为不变。不承诺导航收益。

## 工程与资产

四份根目录文档移至docs，包校验脚本移至tools，历史包验证记录移至provenance，运行时R2R教学索引移至r2r。FILE_HASHES保留为仓库级清单，VERSION保留兼容身份。具体旧新路径见 `provenance/layout_migration.json`。迁移同步覆盖CI、ROOT定位、构建及发布白名单，不保留两份活动事实来源。

P0保留完整角色定位。Reviewer独立来源清单与候选对齐分开；Generator只提交候选；P2通过引用和具体操作消除重复。新增事实举证、终态作用域、持续约束、修饰附着、连续通行及必要锚点在既有规则中细化，未增加P2节点。

125份作者资产由119份不可变历史来源和6份显式合成教学组成。GEN030/035保持正确候选，修复目标、来源证据、旧边界说明和WAIT描述；R06保留合法粗粒度PASS，修正条件及旧缺陷说明；DIAG28重建事件级覆盖与交接。新增合成案例仅教授条件分支和返回过程，无虚假官方数据身份，也未使用评测失败原文。

配对Reviewer只同步候选文本；审计依据来源要求、候选和作者显式定义独立生成。污染Generator自审不改变Reviewer结果；候选缺少完成动作时构建拒绝。此处独立指不继承Generator自审，不代表两名独立人类标注认证。

教学索引连接角色规则ID、具体关系子类型、教学极性及可检索来源关系。第五第六条Dynamic需具有真正新增子关系或正反判别价值；诊断考虑配对教学的覆盖但不把正例等同负例。来源家族身份只用于Host内部排除，未进入模型或参与成绩驱动排序。

## 已运行验证

325项自动化回归通过，包括24项新增精修测试。一个依赖仓库外manage_release.py的测试缺失，单列且不计通过。RxR隔离覆盖205个受保护文件、47来源×4阶段=188组请求、混合Profile及已编译字节，均一致。具体结果以已提交JSON报告为准。

37条唯一教学来源执行148阶段Prompt投影检查：固定Core及每个所选投影均准确出现一次；选择确定性与投影Hash一致。本组Generator均选4条；Reviewer诊断27条输入选2条、10条输入选3条。第五第六条逻辑由独立正反测试覆盖，不能据本组结果宣称真实数据覆盖收益。11条查询与固定Core原文相同，21条存在原文或来源家族重叠——因为本组本就是教学来源自检，不是独立评测名单。不能将这些数字解释为1068评测泄漏率。

## 尚未完成或不能证明的内容

原始工作簿、1068条运行记录及轨迹不在本次可用文件中，73退化/52恢复及各历史案例因果未重新计算。真实LLM的规则遵循率、纠错质量及导航SR/SPL/nDTW未测试。代码和模板正确性不能替代这些实验。

未构造无充分依据的C10欠分割反例。R06已被确认应接受合法粗粒度；需要取得具有独立目标及可证明实质聚焦损失的来源后再建立欠分割金标准。当前任务24保留待独立裁定，不以形式上的多阶段强制取代语义证据。

固定Core仍含val_seen来源。已实现来源家族排除和固定Core碰撞报告，但缺少真实测评名单，不能认证正式数据隔离；近重复语义检测也没有凭空实现。

## 逐项状态

以下状态描述实现，不代表导航收益。详细文件及证据边界见 `provenance/r2r_issue_ledger.json`。

|编号|问题|状态|完成内容或限制|
|---|---|---|---|
|1|模块文件归属|implemented|移动四份文档、校验脚本、验证记录、R2R索引；保留全局哈希与兼容身份|
|2|硬编码路径与调用|implemented|同步ROOT、REQUIRED、Workflow、发布白名单及索引读取|
|3|旧构建覆盖当前文件|implemented|README不再从旧提交覆盖；重建逻辑和迁移路径一致|
|4|版本身份与来源区分|implemented|保留真实兼容身份和历史提交；不增加模型可见开发版本|
|5|保留完整P0|implemented|保持角色身份和运行条件，不机械压缩|
|6|独立来源与候选映射|implemented|R-P1-A只建来源清单，R-P1-B执行一次候选映射|
|7|候选冻结职责|implemented|G-P1-C改为submit；Host与Renderer负责冻结放行|
|8|规则层级去重|implemented|按父规则引用与场景操作分工，维持12/10条P2|
|9|纠错新增导航事实|implemented_effect_unverified|来源判据和返修双重举证；历史525原始记录缺失|
|10|最终STOP前移|implemented_effect_unverified|同一事件、跨越动作、终态作用域三项核对；未重跑556|
|11|持续关系弱化|implemented_effect_unverified|保持on/from作用域，局部修复保护extent及approach|
|12|修饰附着风险|implemented_effect_unverified|明确归属与GEN035教学；1623/1311仍为待核实假设|
|13|连续通行与独立目标|implemented_effect_unverified|区分连续通行、独立目标、关系细化；不强制改变合法分组|
|14|锚点与继承|implemented_effect_unverified|继承、必要锚点、补真实动作三种路径，不按关键词禁用|
|15|Actor敏感性|blocked_missing_evidence|未获得原始Excel/轨迹/推理状态；不新增案例特例|
|16|分支与返回教学|implemented|新增6份显式合成正反教学，未使用评测原文|
|17|GEN030证据与旧说明|implemented|不改正确候选；完整对象相对目标引用、阶段源片段、WAIT说明|
|18|GEN035旧切点说明|implemented|同步实际hallway entry与后续ordinal目标，移除chair-only边界理由|
|19|R06判定与说明矛盾|implemented|保留PASS，补空间条件及具体C10合法替代解释|
|20|DIAG28审核过粗|implemented|三项来源要求、目标过程区分、until条件、真实交接，无虚假Finding|
|21|R04/R08保护|implemented|原有高价值判据保留并受既有回归保护|
|22|重建错误审计与复制自审|implemented|按scope生成ending；配对Reviewer依据来源和候选，不复制Generator自审|
|23|显式作者清单|implemented|119历史blob锁定+6新增精确来源SHA；未登记修改拒绝|
|24|真实欠分割金标准|pending_independent_adjudication|未将合法粗粒度强行改判错误；需要独立来源级实质focus-loss证据|
|25|规则与教学映射|implemented|125份资产建立rule_ids、关系子类型、极性和真实教学依据|
|26|检索技能对齐|implemented|教学技能与来源检索信号区分；lost_action不预测候选未来错误|
|27|可选第五第六条|implemented|依据新子关系/正反例价值而非粗标签；测试验证可选slot及不重复补齐|
|28|Reviewer互补诊断|implemented|配对案例纳入prior；正例不自动抑制负例|
|29|来源家族和测评隔离|partial_evaluation_roster_missing|Host-only显式family排除及core碰撞报告；实际评测家族重叠仍待原始名单|
|30|完整教学投影|implemented|保留完整Core/前两Dynamic/首诊断；摘要增加Process与Entry|
|31|实际注入一致性|partial_original_1068_missing|37教学来源148阶段核对通过；1068原始输入缺失未复算|
|32|四阶段接口冻结|implemented|关系实现纳入freeze；Host-only家族不进入模型；现有回放回归|
|33|错误分类|implemented|保持既有技术/源级/候选错误契约，缺资产/Hash/配对fail closed|
|34|发布和重建一致性|implemented|迁移路径及登记新增资产同步构建、测试和发布|
|35|工程与语义验证边界|partial_live_evaluation_unavailable|325回归通过；缺外部fixture单列；未调用真实LLM或导航|
|36|RxR隔离|implemented|205文件、47来源188阶段及混合Profile一致|

## 可重复执行

```sh
python -B -m tools.r2r_authoring.integrate
python -B -m tools.r2r_authoring.build --check
python -B -m tools.r2r_authoring.test_expectations
python -B -m host.compile
python -B -m tools.r2r_authoring.verify --isolation
python -B -m tools.r2r_authoring.audit
python -B -m tools.r2r_authoring.verify --refresh
python -B tools/verify_package.py
python -B -m tools.r2r_authoring.regression
python -B -m tools.r2r_authoring.smoke
python -B -m tools.r2r_authoring.verify --refresh
python -B tools/verify_package.py
```

发布只允许基于当前已验证提交进行非强制快进；远端变化时停止，不覆盖他人工作。索引、快照及报告重建必须与声明清单相同。
