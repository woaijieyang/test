# VLN 模型测试总表 / Case1

R2R/RxR分别展示；不同scope或配置不自动计算收益。原始轨迹在outputs，不随Git发布。

## r2r

| Scope | Episodes | Model | Run | Status | SR % | SPL % | nDTW % | NE m | Oracle SR % | ΔSR pp | ΔSPL pp | ΔnDTW pp | ΔNE m | ΔOracle pp | 来源 |
|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A1 | 123 | AwareVLN official | [awarevln-r2r-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | retracted | 68.293 | 59.443 | 66.642 | 3.7192 | 78.049 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| A2 | 183 | AwareVLN official | [awarevln-r2r-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | retracted | 63.934 | 55.294 | 62.915 | 3.9118 | 73.224 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| A3 | 306 | AwareVLN official | [awarevln-r2r-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | retracted | 64.706 | 57.346 | 65.055 | 4.0358 | 75.163 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| B1 | 123 | AwareVLN official | [awarevln-r2r-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | retracted | 75.610 | 63.722 | 66.230 | 2.9867 | 85.366 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| B2 | 183 | AwareVLN official | [awarevln-r2r-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | retracted | 66.667 | 57.134 | 66.065 | 3.7771 | 74.863 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| B3 | 306 | AwareVLN official | [awarevln-r2r-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | retracted | 63.725 | 55.699 | 64.790 | 4.4369 | 73.529 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| Remaining | 615 | AwareVLN official | [awarevln-r2r-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | retracted | 64.715 | 56.942 | 65.912 | 4.0524 | 73.821 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| A1+A2 | 306 | AwareVLN official | [awarevln-r2r-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | retracted | 65.686 | 56.962 | 64.413 | 3.8344 | 75.163 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| A | 612 | AwareVLN official | [awarevln-r2r-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | retracted | 65.196 | 57.154 | 64.734 | 3.9351 | 75.163 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| B1+B2 | 306 | AwareVLN official | [awarevln-r2r-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | retracted | 70.261 | 59.782 | 66.131 | 3.4594 | 79.085 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| B | 612 | AwareVLN official | [awarevln-r2r-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | retracted | 66.993 | 57.741 | 65.460 | 3.9481 | 76.307 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| Full | 1839 | AwareVLN official | [awarevln-r2r-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | retracted | 65.633 | 57.278 | 65.370 | 3.9786 | 75.095 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| A1 | 123 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r](checkpoint-choice-20261024.md) | complete | 68.293 | 59.443 | 66.642 | 3.7192 | 78.049 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| A2 | 183 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r](checkpoint-choice-20261024.md) | complete | 63.934 | 55.294 | 62.915 | 3.9118 | 73.224 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| A3 | 306 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r](checkpoint-choice-20261024.md) | complete | 64.706 | 57.346 | 65.055 | 4.0358 | 75.163 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| B1 | 123 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r](checkpoint-choice-20261024.md) | complete | 75.610 | 63.722 | 66.230 | 2.9867 | 85.366 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| B2 | 183 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r](checkpoint-choice-20261024.md) | complete | 66.667 | 57.134 | 66.065 | 3.7771 | 74.863 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| B3 | 306 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r](checkpoint-choice-20261024.md) | complete | 63.725 | 55.699 | 64.790 | 4.4369 | 73.529 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| Remaining | 615 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r](checkpoint-choice-20261024.md) | complete | 64.715 | 56.942 | 65.912 | 4.0524 | 73.821 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| A1+A2 | 306 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r](checkpoint-choice-20261024.md) | complete | 65.686 | 56.962 | 64.413 | 3.8344 | 75.163 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| A | 612 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r](checkpoint-choice-20261024.md) | complete | 65.196 | 57.154 | 64.734 | 3.9351 | 75.163 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| B1+B2 | 306 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r](checkpoint-choice-20261024.md) | complete | 70.261 | 59.782 | 66.131 | 3.4594 | 79.085 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| B | 612 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r](checkpoint-choice-20261024.md) | complete | 66.993 | 57.741 | 65.460 | 3.9481 | 76.307 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| Full | 1839 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r](checkpoint-choice-20261024.md) | complete | 65.633 | 57.278 | 65.370 | 3.9786 | 75.095 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |

## rxr

| Scope | Episodes | Model | Run | Status | SR % | SPL % | nDTW % | NE m | Oracle SR % | ΔSR pp | ΔSPL pp | ΔnDTW pp | ΔNE m | ΔOracle pp | 来源 |
|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A1 | 81 | AwareVLN official | [awarevln-rxr-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | complete | 64.198 | 52.522 | 67.813 | 4.6125 | 74.074 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| A2 | 122 | AwareVLN official | [awarevln-rxr-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | complete | 60.656 | 51.210 | 64.699 | 5.4957 | 64.754 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| A3 | 204 | AwareVLN official | [awarevln-rxr-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | complete | 68.137 | 56.998 | 66.600 | 4.7731 | 74.020 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| B1 | 81 | AwareVLN official | [awarevln-rxr-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | complete | 65.432 | 51.945 | 66.258 | 3.4575 | 79.012 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| B2 | 122 | AwareVLN official | [awarevln-rxr-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | complete | 68.033 | 56.319 | 70.005 | 3.9402 | 74.590 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| B3 | 204 | AwareVLN official | [awarevln-rxr-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | complete | 68.137 | 55.767 | 68.716 | 4.1947 | 75.000 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| Remaining | 409 | AwareVLN official | [awarevln-rxr-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | complete | 70.171 | 58.248 | 68.099 | 3.9104 | 78.484 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| A1+A2 | 203 | AwareVLN official | [awarevln-rxr-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | complete | 62.069 | 51.734 | 65.942 | 5.1432 | 68.473 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| A | 407 | AwareVLN official | [awarevln-rxr-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | complete | 65.111 | 54.372 | 66.272 | 4.9577 | 71.253 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| B1+B2 | 203 | AwareVLN official | [awarevln-rxr-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | complete | 66.995 | 54.574 | 68.510 | 3.7476 | 76.355 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| B | 407 | AwareVLN official | [awarevln-rxr-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | complete | 67.568 | 55.172 | 68.613 | 3.9717 | 75.676 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| Full | 1223 | AwareVLN official | [awarevln-rxr-valunseen-endpoint9-20261015-v2](checkpoint-choice-historical.md) | complete | 67.621 | 55.935 | 67.662 | 4.2793 | 75.143 | — | — | — | — | — | historical_reaggregation_not_new_inference |
| A1 | 81 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr](checkpoint-choice-20261024.md) | complete | 64.198 | 52.522 | 67.813 | 4.6125 | 74.074 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| A2 | 122 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr](checkpoint-choice-20261024.md) | complete | 60.656 | 51.210 | 64.699 | 5.4957 | 64.754 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| A3 | 204 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr](checkpoint-choice-20261024.md) | complete | 68.137 | 56.998 | 66.600 | 4.7731 | 74.020 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| B1 | 81 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr](checkpoint-choice-20261024.md) | complete | 65.432 | 51.945 | 66.258 | 3.4575 | 79.012 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| B2 | 122 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr](checkpoint-choice-20261024.md) | complete | 68.033 | 56.319 | 70.005 | 3.9402 | 74.590 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| B3 | 204 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr](checkpoint-choice-20261024.md) | complete | 68.137 | 55.767 | 68.716 | 4.1947 | 75.000 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| Remaining | 409 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr](checkpoint-choice-20261024.md) | complete | 70.171 | 58.248 | 68.099 | 3.9104 | 78.484 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| A1+A2 | 203 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr](checkpoint-choice-20261024.md) | complete | 62.069 | 51.734 | 65.942 | 5.1432 | 68.473 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| A | 407 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr](checkpoint-choice-20261024.md) | complete | 65.111 | 54.372 | 66.272 | 4.9577 | 71.253 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| B1+B2 | 203 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr](checkpoint-choice-20261024.md) | complete | 66.995 | 54.574 | 68.510 | 3.7476 | 76.355 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| B | 407 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr](checkpoint-choice-20261024.md) | complete | 67.568 | 55.172 | 68.613 | 3.9717 | 75.676 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |
| Full | 1223 | AwareVLN official | [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr](checkpoint-choice-20261024.md) | complete | 67.621 | 55.935 | 67.662 | 4.2793 | 75.143 | +0.000 | +0.000 | +0.000 | +0.0000 | +0.000 | fresh_model_evaluation |

Δ列仅在冻结身份/数据/profile/task集合一致的逐任务配对下报告，均为新减旧；SR/SPL/nDTW/Oracle SR单位百分点，NE单位米。历史重分组只说明历史同一完整run按固定集合拆分，不是新模型推理。R2R旧结果保持retracted；新旧分数相等不解除其额外严格几何限制。
[原完整测评登记与详细身份](model_results.md)。新运行未结束/未审计时不填完整成绩；状态见outputs/checkpoint-choice-20261024/state.json。
