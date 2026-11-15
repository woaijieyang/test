# Evaluation｜分开评价文本、审查、格式和导航

本包的离线 smoke24 只验证格式路径。`paired.py` 负责固定 task_key 分母的配对指标汇总；每条记录必须含 baseline/candidate 结果与 disposition。不要把 fallback、技术失败或 unresolved 从分母删除。SR/SPL/nDTW/NE/steps/path 的单位和缺失值处理见脚本说明。

推荐顺序：
1. 冻结样本，对 Generator G0 分别标注 fidelity、closure/handoff、segmentation adequacy。
2. 在相同候选上盲审 Reviewer，统计 TP/FP/FN、误报、建议采纳/拒绝、G0→G1 净修复。
3. 冻结语义候选后，独立做 LF vs SPACE 格式对照；不得把格式实验混入语义修订。
4. 固定模型、图像、预算、提示词和环境做成对导航；报告恢复/退化和全分母指标。
5. 用 scene/path-disjoint held-out set 检验泛化；不按单条导航成绩挑文本。

当前上传的 evaluation 子集已用于开发分析，不能当作独立 held-out 集。通过本地测试不代表导航效果已验证。
