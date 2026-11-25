# R2R 最小改动实现与验证记录

## 实施基底和范围

基于 `d4cce47841c817083217a7fffa3a1e6235316491`，按审核后的最小改动方案完成职责迁移、专用教学适用性、最小必要改写和返修对照教学。目录迁移与语义修改分别提交。未改变通用 Shared、角色公共 Prompt、输出 Schema、Adapter、Renderer、Actor、模型角色数或返修轮数；没有修改 RxR 专属规则、模板或选择策略。

此前 `R2R_REFINEMENT_REPORT.md` 和 `provenance/r2r_issue_ledger.json` 是前一轮历史交付记录。其“原始工作簿不可用”仅描述前一轮，当前已重新读取用户提供工作簿，并完成下述来源重放；未将历史记录伪装成新的测评结果。

## 模块所有权

根目录不再保留 `r2r/` 和 `r2r_authoring/`：运行时的选择、来源关系、教学投影和索引归入 `host/r2r/`；离线构建、显式作者定义、校验和发布归入 `tools/r2r_authoring/`；测试归入 `tests/r2r/`。24个文件迁移，旧活动副本移除，import、ROOT定位、CLI、测试发现、CI、冻结清单、发布白名单和文档路径同步。历史 Git 来源路径和不可变来源身份没有改写。迁移映射见 `provenance/layout_migration.json`。

迁移阶段单独验证37条来源×4阶段共148组：选例ID、投影字节、Prompt和Schema均一致。路径引起的内部溯源Hash变化不等于模型输入变化。见 `provenance/r2r_layout_equivalence.json`。

## 精确规则与实际教学

Generator 保持12条P2、Reviewer保持10条P2，不增加层级。

- G-P2-B4：先完整理解路线和决定边界，再优先保留清晰来源片段；每次编辑须解决具体身份、关系或依赖问题。不是优化逐字复制率，也不是禁止合法改写。
- G-P2-B2：检查省略拟新增入口锚点后，目标/区域/计数/参照是否仍唯一；能继承则继承，确有歧义才补最短关系，未执行动作不能用From/Inside冒充。
- G-P2-A4及Reviewer关系检查：合并前后保持每个方向、目标短语和持续条件的动作归属，而非仅保留关键词。
- Reviewer将生成偏好与验收标准分离：可省略但无害的锚点并非实质缺陷。来源唯一支持的纠错举证适用于活动候选和needs_review，不只适用于误拒绝。

GEN011/015/019/021/030/034/035及相应教学投影增加具体边界解释：独立目标与耦合转向、必要计数/对象参照与可继承普通位置、同一事件细化与错误范围变更。既有125份普通模板的候选文本与来源身份均保持不变；合法粗粒度R06、合法细粒度DIAG28及高价值R04/R08继续保护。

新增两个显式合成返修案例族（不是新Dynamic模板）：无依据添加数量、无依据移动最终停止位置。每族分别生成G1和R1完整示范，R0错误建议明确标为故意错误的输入，不能作为金标准。G1拒绝无依据建议、R1据原候选证据重新放行。只在R2R对应repair/recheck阶段加载，固定Core、前两Dynamic、首Diagnostic完整示范策略不变，所有新增文件纳入Host冻结。运行时不调用作者工具。

`provenance/r2r_operation_coverage.json` 连接规则、具体证据路径、投影字段及阶段。覆盖检查包括G-P2-B4、G-P2-C1、R-P2-C2/C3；它不宣称所有自然语言规则已经被证明有效，也不以无关标签充数。真实C10欠分割金标准仍待独立裁定。

## 专用教学适用性

在互补评分之前检查 `required_query_facets`。返回模板不能仅凭scope/terminal竞争；条件分支诊断不能仅凭entry/terminal竞争。六份分支/返回专用资产有明确门槛，一般案例保持一般校准资格。无专用匹配是正常排除，不触发技术回退；丢资产、Hash/配对/元数据错误仍fail closed。

排序权重、动态数量、配对顺序与四阶段冻结策略不变。either side、Do not enter either room不再触发未知名称；普通back to不自动认定为已发生访问后的返回。新增表面路径持续关系线索，但只作检索信号，不当成语义真值，未宣称已有完整表面约束对照教学。所选记录区分一般校准与专用关系适用依据。

## 已执行的工程和来源重放

| 检查 | 结果 |
|---|---|
| 目录迁移单独回归 | 325项通过 |
| 当前完整回归 | 349项通过，含24项新增测试 |
| 缺失外部夹具 | 1项manage_release.py依赖不可用，明确列出，不计通过 |
| RxR对历史父提交与本轮基底的隔离 | 205个受保护文件、47来源×4阶段=188组请求、混合Profile均一致 |
| Renderer和离线闭环 | 24条Smoke、四阶段Demo通过 |
| 构建 | 作者清单、活动协议、重复编译、完整性校验通过 |
| 工作簿来源重放 | 基底与候选各1068条、各4272个实际编译阶段请求 |
| 教学实际注入 | 固定Core、所选投影与Hash、返修专用示范逐请求核对 |

完整回归中的模型接口使用确定性测试替身，未调用真实LLM。重放检查实际编译请求，但不执行模型或导航。

工作簿摘要和SHA在 `provenance/r2r_workbook_replay.json`。只提取《指令问题定位》的任务键和原始Instruction，不把成绩、轨迹或结果标签交给选择器。任务键和来源SHA逐条对齐；未从episode ID推断trajectory ID。原始工作簿和原文重放记录不提交到运行时资产。

在同一适用条件下复核：Generator不适用专用模板选例槽位由380降为0；Reviewer诊断由129降为0。37条教学来源自检对应9→0和1→0。全量Generator选例ID在367条输入发生变化，Reviewer在430条发生变化。两版Generator仍均为1047条选4例、21条选5例；Reviewer诊断从739条选2例/329条选3例变为743/325。没有为了显示自适应而强制增加模板。

以上是检索槽位计数，不是恢复成功的任务数，不能据此推导SR/SPL/nDTW提升。适用门槛是来源线索，不是完备语义判定。普通branch/back-to弱信号没有满足专用条件时，保留未覆盖记录而不是虚报覆盖。

## 可复现入口

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
```

在仓库外指定输出，避免将评测来源混入正式包：

```sh
python -B -m evaluation.r2r_replay /path/to/VLN_Split_Impact_Analysis.xlsx --records /tmp/r2r_sources.json
python -B -m tools.r2r_authoring.audit --records /tmp/r2r_sources.json --output /tmp/r2r_audit.json
```

基底需在独立worktree使用当时的 `r2r_authoring.audit`，以相同来源文件重放。当前记录中的源文件和完整审计Hash可核查输入一致性。

## 仍不能证明的内容

未运行真实LLM纠错评测或端到端导航，未完成四配置导航消融，不承诺大幅性能提升。1068条历史数据用于开发诊断，不是新的独立泛化集。固定Core仍含val_seen来源；本工作簿没有路径ID，零精确文本碰撞不能认证来源家族隔离。C10真实欠分割负例、表面持续约束的专用正反教学及近重复语义检测仍有明确证据边界，不用人为错误标签或关键词断言替代。
