# Landmark剩余端点源接触诊断


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
