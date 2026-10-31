# HAMLET 基线迁移与复测结论

状态：进行中。对应计划 2026-10-31-1-plan-HAMLET基线迁移与复测.md。

已完成发布快照 991 文件导入、case2 独立 Git 初始化、6 个只读资产链接检查、3 种真实内核权限模式检查。环境正在独立重建；未执行新导航或发布。历史 HAMLET 的来源身份已核验，不能据此宣称 case2 复现通过。

原始证据：.planning/2026-10-31-hamlet-construct/baseline-import.json；historical-source-resolution.json；historical-metrics-checkpoints.json；outputs/verification/protection-attempt1.json；outputs/setup/environment-build-attempt1.log。

安装 attempt1 因下载缓慢由本任务主动停止，改用独立复制的已下载分发包缓存后重新安装；不复制或复用源环境。Git 从部分克隆源 fetch 失败，转由完整 GitHub clone 的 bundle 导入，未修改源 Git。

## baseline 部署验证已完成，HAMLET 集成仍待执行
独立环境安装、41/41 CPU、实际模块导入、原生库链接、官方模型身份、6 资产链接、3 内核权限模式均通过。3062 条静态距离有限；101 条 GT 参考轨迹离网限制保留。48 条模拟器运动与独立动作回放 PASS，最大误差 0。R2R 2/2、RxR 11/11 完整 episode 诊断通过，分别 78/291 次模型调用、146/665 个 primitive 动作；实际图片、模型输出、解析与动作一致，独立指标复算一致。见 results-show/deployment-tests.md 及原始 outputs 回执。

正式全量校验器正确拒绝 diagnostic scope，已保留日志；诊断独立审计未修改 scope 或绕过正式准入。台账 finish-run 首次因 artifacts 参数用字典而失败，改为列表后发现缺少 task-flow 目录；已补建本 case 目录并正常归档三项诊断，未修改校验器。初始发布仅标注 baseline 部署测试通过，HAMLET 尚未集成。
