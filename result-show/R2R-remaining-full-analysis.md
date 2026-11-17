# R2R Remaining与Full差异分析

本报告只在1839条完整R2R独立审计通过后生成。RxR仍按独立状态运行，不能据此宣称全部测评结束。

| Scope | N | 本次SR% | baseline SR% | 原HAMLET SR% | ΔSR vs baseline pp | ΔSR vs 原版 pp | 恢复/退化 |
|---|---:|---:|---:|---:|---:|---:|---|
| Remaining | 615 | 64.552846 | 64.715447 | 64.552846 | -0.162602 | +0.000000 | 18/19 |
| Full | 1839 | 65.144100 | 65.633496 | 64.872213 | -0.489396 | +0.271887 | 64/73 |

## Remaining

相对baseline：SR -0.162602个百分点，SPL -0.493051个百分点，nDTW -0.070567个百分点，NE -0.064939m，Oracle SR +0.325203个百分点。恢复18条、退化19条，净成功变化-1条。

相对原历史HAMLET：SR +0.000000个百分点，SPL +0.050219个百分点，nDTW -0.619237个百分点，NE +0.006225m。此对照保留旧parser、reset和环境协议差异，不能归因为单个模块。

## Full

相对baseline：SR -0.489396个百分点，SPL -0.653340个百分点，nDTW -0.096615个百分点，NE -0.006130m，Oracle SR +0.489396个百分点。恢复64条、退化73条，净成功变化-9条。

相对原历史HAMLET：SR +0.271887个百分点，SPL +0.187872个百分点，nDTW -0.909718个百分点，NE -0.018825m。此对照保留旧parser、reset和环境协议差异，不能归因为单个模块。

## Remaining对总体判断的影响

A+B共1224条相对baseline净成功变化-8条，Remaining615条净变化-1条，二者合计构成Full1839条。Full按所有任务汇总，不能把A、B、Remaining三个均值简单平均。Remaining已完整纳入，不是仅展示A+B。

SR只反映成功数量，SPL/nDTW/NE反映不同的路径与终点性质。若各指标方向不一致，不能概括成全面提升。应结合逐任务恢复/退化检查首次动作分歧、路由选择、实际注入、碰撞和停止时机；本报告不把相关性当因果，也不据val_unseen结果修改正在运行的参数。

该Remaining是既有固定划分的剩余集合，不自动具有独立无偏holdout资格。几何/GT离网局限和历史训练来源限制继续保留。

独立审计证据：outputs/independent-r2r-full-audit-20261101/validation.json、semantic_audit.json、independent_metrics.json、hamlet_dataflow_audit.json；快照来源见snapshot-provenance.json。详细五指标见R2R-remaining-full-independent.md/json。
