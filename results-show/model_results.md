# AwareVLN Case1 统一测评结果

本表由已验收逐任务结果生成；原始证据保留在各运行目录。

## R2R 正式导航评测

| Record ID | Scope | Episodes | Case | Model | Version | Status | SR (%) | SPL (%) | nDTW (%) | NE (m) | Oracle SR (%) | Benchmark SHA | Model code path | Dataset/manifest path |
|---|---|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|
| [awarevln-r2r-valunseen-endpoint9-20261015-v2](awarevln-r2r-valunseen-endpoint9-20261015-v2.md) | Full | 1839/1839 | case1 | AwareVLN official | c2280a04c33b / mesh 85328a019b54 / awarevln-scene-minimal-endpoint9-v2 | retracted | 65.633 | 57.278 | 65.370 | 3.9786 | 75.095 | `9453e3ad54f596b99a849ab37467f775671bea8edce33da4a7bc21bdb80525a9` | `/data/zy/vln/case1/src` | `/data/zy/vln/case1/outputs/awarevln-r2r-valunseen-endpoint9-20261015-v2/run_manifest.json` |
| [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r](awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r.md) | Full | 1839/1839 | case1 | AwareVLN official | 1336e3595037 / mesh 85328a019b54 / awarevln-scene-minimal-endpoint9-v2 | complete | 65.633 | 57.278 | 65.370 | 3.9786 | 75.095 | `9453e3ad54f596b99a849ab37467f775671bea8edce33da4a7bc21bdb80525a9` | `/data/zy/vln/case1/src` | `/data/zy/vln/case1/outputs/awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r/run_manifest.json` |

### 有限值与失败统计

| Record ID | SPL valid/nonfinite | NE valid/nonfinite | nDTW valid/nonfinite | 普通导航失败 | 运行异常 |
|---|---:|---:|---:|---:|---:|
| awarevln-r2r-valunseen-endpoint9-20261015-v2 | 1839/0 | 1839/0 | 1839/0 | 632 | 0 |
| awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r | 1839/0 | 1839/0 | 1839/0 | 632 | 0 |

## RxR-US 正式导航评测

| Record ID | Scope | Episodes | Case | Model | Version | Status | SR (%) | SPL (%) | nDTW (%) | NE (m) | Oracle SR (%) | Benchmark SHA | Model code path | Dataset/manifest path |
|---|---|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|
| [awarevln-rxr-valunseen-endpoint9-20261015-v2](awarevln-rxr-valunseen-endpoint9-20261015-v2.md) | Full | 1223/1223 | case1 | AwareVLN official | c2280a04c33b / mesh 85328a019b54 / awarevln-scene-minimal-endpoint9-v2 | complete | 67.621 | 55.935 | 67.662 | 4.2793 | 75.143 | `556b628ad57c945448e013d98cb206619086da54788798703adce3a9b1cc5b9f` | `/data/zy/vln/case1/src` | `/data/zy/vln/case1/outputs/awarevln-rxr-valunseen-endpoint9-20261015-v2/run_manifest.json` |
| [awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr](awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr.md) | Full | 1223/1223 | case1 | AwareVLN official | 1336e3595037 / mesh 85328a019b54 / awarevln-scene-minimal-endpoint9-v2 | complete | 67.621 | 55.935 | 67.662 | 4.2793 | 75.143 | `556b628ad57c945448e013d98cb206619086da54788798703adce3a9b1cc5b9f` | `/data/zy/vln/case1/src` | `/data/zy/vln/case1/outputs/awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr/run_manifest.json` |

### 有限值与失败统计

| Record ID | SPL valid/nonfinite | NE valid/nonfinite | nDTW valid/nonfinite | 普通导航失败 | 运行异常 |
|---|---:|---:|---:|---:|---:|
| awarevln-rxr-valunseen-endpoint9-20261015-v2 | 1223/0 | 1223/0 | 1223/0 | 396 | 0 |
| awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr | 1223/0 | 1223/0 | 1223/0 | 396 | 0 |
