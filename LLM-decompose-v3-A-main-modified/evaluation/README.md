# Evaluation：独立于生成和审核

`metrics.paired`计算已准备配对行；`paired_from_results`要求预先锁定的expected_keys、baseline真实导航结果与candidate真实导航结果。重复、缺失、额外任务或把pipeline结果当SR会被拒绝。全部回退保留在分母，不以流程accepted认定导航成功。

报告基线成功中退化比例、基线失败中恢复比例、净SR和提供的连续指标；缺失的成本或轨迹指标不捏造为零。示例运行只说明数学与记录处理，无实际导航。

`render_controls.variants(frozen)`构造LF、空格、紧连等诊断候选，保留逻辑阶段内部字符。SOURCE_EXACT不生成伪格式变体。对照不是默认生产renderer；生成后不能复用原pass回执，因为实际instruction已经不同。必须预先冻结评测策略，不按每条轨迹结果择优。

`python -m evaluation.smoke`对source_text_smoke24.json的24条文本只运行adapter/renderer，不调用模型，不评价语义，也不算新导航。数据没有得分/GT，属于开发烟测，不能用来报告泛化准确率。
