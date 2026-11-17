# Case2 部署链路测试

以下是本次独立环境中的完整 episode 诊断，不是全量 benchmark 成绩。历史 case1 成绩保留原来源。

| Scope | Episodes | Case | Model | Status | Model calls | Primitive actions | 证据 |
|---|---:|---|---|---|---:|---:|---|
| r2r diagnostic | 2 | case2 | AwareVLN baseline | diagnostic PASS | 78 | 146 | `outputs/case2-baseline-dataflow-20261031-r2r/diagnostic_validation.json` |
| rxr diagnostic | 11 | case2 | AwareVLN baseline | diagnostic PASS | 291 | 665 | `outputs/case2-baseline-dataflow-20261031-rxr/diagnostic_validation.json` |

41 项 CPU 回归通过（0 failures/errors/skips）；6 项资产链接、3 种内核权限模式通过；3062 条任务静态距离均有限；48 条模拟器运动及独立回放通过，最大位置误差 0。101 条 GT 参考轨迹存在离网点的既有局限继续保留。

实际导入、原生链接、pip check、官方权重 Git/LFS 校验通过。以上不证明 HAMLET 已装配或全量测评通过。
