# 002 图记忆接入与验证

注入实现、调用图和修改入口见 [注入目录说明](../../map_memory/retrieval/README.md)。原生八槽与预算见 [宿主图像槽](native_image_slots.md)，验收项见 [acceptance_matrix.json](acceptance_matrix.json)。当前状态为小样本开发。

当前候选根为 `outputs/graph_memory/graph002-organized-candidate-01/`。整理前源码及既有实验位于 `outputs/graph_memory/graph002-work-20261113/`。运行输出和失败现场保留在原 run。正式入口与候选入口通过独立目录选择。

整理后的合同测试见 `validation/unified-check-final/test_results.json`，IPC 与异步回归见 `ipc-check-01.log`。同配置 R2R 1099 的原始配对报告见 `validation/paired-r2r.json`。
