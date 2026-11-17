# R2R与Landmark-RxR：训练扩充、监督形式与数据流分析

本报告针对现有HAMLET-inspired memory/CBEM训练扩充，不启动新训练、采集或修改正在评测的模型。所有数量来自本次对服务器原始JSON的统计；历史几何结果另标为发布快照，不等于当前case2已复验。

## 数据定位与规模

R2R是整条导航指令与参考路线的粗粒度配对。Landmark-RxR基于RxR English Guide，增加人工子指令—子路径对齐。它不是当前RxR-US1223条评测子集的另一个名字，也不是已经渲染好的memory训练特征。

|数据|split|指令记录|路径ID数量|场景|子指令—子路径对|
|---|---|---:|---:|---:|---:|
|R2R连续版本|train|10819|3603|61|无对应人工分段字段|
|R2R连续版本|val_seen|778|259|53|—|
|R2R连续版本|val_unseen|1839|613|11|—|
|Landmark-RxR原始|train|26464|8824|60|133531|
|Landmark-RxR原始|val_seen|2939|980|58|13586|
|Landmark-RxR原始|val_unseen|4551|1517|11|19546|

R2R路径数按trajectory_id计，Landmark按(scan,path_id)计，不等同于已检查每条路径几何字节完全唯一。相同路径的不同语言描述不能当成相互独立的训练/开发任务。训练Landmark语言为en-US8816、en-IN17648。平均R2R指令26.65个空格分词，Landmark完整指令100.71个、子指令19.91个，平均每条5.05个子段；这是本地统一统计口径，不是论文tokenizer长度。

Landmark全33954记录的sub_paths和sub_instructions数量对应；没有空或单节点子路径，也没有整条path中重复视点ID。但这只是JSON结构检查，不证明子指令语义、地图映射和连续运动都正确。

## 当前接入核验

按instruction_id+scene+language精确对齐现有RxR continuous guide：train26464中19996唯一匹配、6468缺失；val_seen2939中2255匹配、684缺失；val_unseen4551中3669匹配、882缺失。三个split共8034条不能直接借用当前guide记录。不能用仅数字ID、文本相似或最近点替代身份对齐。

train匹配项中19579条文本字节相同，另417条差异均可用仅去除外层双引号/空白的诊断性规范化消除。语义差异不能从字节差异直接推断；后续正式转换需保存原文本、规范化规则和映射回执，而非静默覆盖。

当前case2没有data/datasets/landmark-rxr链接，运行的baseline/RxR链不等于已接入Landmark训练链。原始文件位于/data/zy/vln/data/raw_data/landmark-rxr。无需因此移动或修改源文件。

Landmark路径存储离散viewpoint ID；R2R当前数据包含Habitat连续坐标及reference_path。两者不能直接共用位置字段。应经过原视点身份、坐标系/相机到地面转换、起始朝向、子路径边界顺序、网格和动作可执行性验证。历史case1文档记录过坐标映射、几何接触、拓扑及有限预算失败；它们不能因复制代码被视为已解决。

发布快照中的Oracle研究记录为Landmark train26464条仅15805严格通过，并保留其余失败类别；它是特权Oracle的旧协议结果，不是模型导航成绩，也不证明这些样本已能直接进入当前训练。后续若复用，须重新绑定对应run/source/profile/动作回放及train权限。原实验中的失败也不能一概视为数据不可达或直接删除。

## R2R适合怎么扩充

优先在已验证的连续环境接口上扩大train场景和路线覆盖。保持完整指令和实际历史，采集合法的模型/专家训练轨迹，冻结同状态branch起点，再比较archive/empty/移除候选等条件。独立检查真实分支结果后生成router偏好或无效果标签。

10819条指令不等于10819条有效CBEM pair；一条路线可产生多个状态，多个anchor也可能强相关。应按场景、路径和指令家庭分组，限制每路径贡献，记录成功/失败、短/长路线、转向/前进/停止、记忆有效/无效/有害等覆盖。

优点是与当前R2R评测接口和数据分布更近，可较快得到可复核的增量。局限是粗粒度整条指令缺少“当前对应哪个子目标”的人工标签；标量终点reward或过短分支常产生tie。先扩展覆盖并检查anchor与reward有效性，不简单降低tie阈值或重复epoch。

## Landmark-RxR适合补什么

人工子指令—子路径对齐提供比整条终点更细的监督机会：
- 表示学习：将某段真实视觉历史与其子指令/地标关联，保留完整轨迹上下文，避免只截局部子段后把记忆任务变成无历史任务。
- 进度监督：训练模型根据观测和自身历史辨别已完成/当前/后续子任务，区分经过门口和进入房间等阶段。
- 候选anchor构建：在跨子任务、关键地标离开视野、重复外观或状态转换处生成历史依赖候选。
- 过程reward：在train-only分支中使用参考子路径衡量局部进展/顺序一致性，再验证是否真的能产生更可靠的偏好。

关键区别：**子指令—子路径对齐是alignment标签，不是memory benefit标签。** 某个地标与当前子指令相关，不代表把该时刻的hidden state注入就一定改善动作。CBEM仍需同状态反事实结果或其他明确验证的训练目标。133531个子段不能宣称等于133531个有效router pairs。

完整GT子路径、当前真值进度、未来地标顺序/坐标可以用于训练标签或reward，但不能在测试时直接告诉模型“现在是第几个子任务”“该去哪个GT坐标”。如果部署接口使用子指令，切换机制必须由可见输入推断并单独验证，否则引入oracle progress泄漏。

## 两种数据怎样联合

建议采用两条互补数据流，而非将文件简单拼接：

R2R train → 当前部署兼容的完整rollout → 因果moment → 同状态分支 → router有益/有害/无效果监督。

Landmark-RxR train → 身份与连续几何验证 → 子指令/子路径/真实RGB/时间边界对齐 → memory表示/进度监督与anchor候选 → 必要的分支效益验证。

如果下一版走忠实原文HAMLET路线，可在通过验证的完整train轨迹上构建learned moment/TCL/动作预测训练；如果保留当前CBEM，则需要明确保留其独立路由训练目标。两种路线均可扩大数据，但不能混称为已完成论文方法复现。

本地R2R train与Landmark train共享60个场景：有利于统一部署，但不构成独立泛化证据。训练场景与对方val_unseen场景的交集本次检查均为0；若从train中划开发集，应采用跨数据集一致的scene分组，避免同场景或同parent trajectory的子段分散到两边。en-IN与en-US来自同路径的描述也须一起分组。

## 建议的最小实施顺序（未执行）

1. 固定当前评测版本，完成本次全量收尾，不把val_unseen案例回填训练。
2. 建立训练数据manifest：来源SHA、split、scene、parent trajectory、instruction/language、子段边界、原始和映射坐标、视觉帧引用、过滤原因和是否能执行。
3. 用R2R train先扩大覆盖，并将Landmark唯一身份匹配的19996条作为接入候选池；剩余6468条单列追溯，不能静默丢掉或伪造匹配。
4. 从两池中按当前协议验证可执行性，明确“原始量→身份匹配量→可执行量→候选anchor→有效监督量”的每层分母。
5. 在训练/dev中做规模学习曲线；例如500/2000/10000有效pair仅为候选档位，不是已具备的数据量或性能保证。另保留no-effect样本，不硬造chosen标签。
6. 验证写入/检索/actual generation消费，以及baseline原正确任务的破坏率，再作独立评测。增加样本不保证有效，扩大覆盖与改进监督同样重要。

结论：可以显著扩大训练。R2R是较直接的行为与效益训练来源；Landmark-RxR更有价值的增量是细粒度监督，而非只多几万条记录。当前真正瓶颈是合法可执行的数据流与有辨识度的memory效益标签，不是原始数据数量。

依据：outputs/training-data-analysis-20261101/inventory.json、landmark-guide-identity-join.json、text-difference-check.json；case2/docs/DATA_INTEGRATION.md、oracleAdapter/docs/FINAL_RESULTS.md（历史快照）。
论文与作者数据说明：https://github.com/hekj/Landmark-RxR ；https://proceedings.neurips.cc/paper/2021/file/0602940f23884f782058efac46f64b0f-Paper.pdf ；https://arxiv.org/abs/1711.07280 。
