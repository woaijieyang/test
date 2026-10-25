# awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r

状态：complete。核验并登记时间：2026-10-25T17:28:02.404271+08:00（Asia/Singapore）。

## 实验身份

| 字段 | 实际身份 |
|---|---|
| run_id | `awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r` |
| 原始证据 | `/data/zy/vln/case1/outputs/awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r` |
| model | `AwareVLN official` |
| model_sha256 | `f467265fc17f68cbc256ef4a65b8d196e8317a316cb858102d72095f2cdf8df5` |
| source_sha256 | `1336e3595037976c4d296a2c8d3779336f4ed23bf877508378af7541974368e4` |
| config_sha256 | `2141f34387a578c2de99b29af590c4f5109dabc9c2a26beaf89aaf19a3c69187` |
| navmesh_sha256 | `85328a019b541b1336c7f2d7ae6d50341d68a9b0fe20f3ee719070918e4d036c` |
| benchmark_sha256 | `9453e3ad54f596b99a849ab37467f775671bea8edce33da4a7bc21bdb80525a9` |
| split | `val_unseen` |
| language | `en` |
| base_config_sha256 | `42f1c1e197352eb449b3c706a4c5d40d8a72eba3ba1b12cba21ccbc8433f1189` |
| model_code_path | `/data/zy/vln/case1/src` |
| dataset_paths | `{"r2r": "/data/zy/vln/data/checkpoint-choice/VLN-awareVLN/annotations/r2r/val_unseen/val_unseen.json.gz"}` |
| dataset_manifest_path | `/data/zy/vln/case1/outputs/awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-r2r/run_manifest.json` |
| navmesh_profile | `/data/zy/vln/case1/data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json` |
| annotation_protocol | `{"schema_version": 1, "protocol_id": "awarevln-scene-minimal-endpoint9-v2", "status": "AUTHORIZED_PENDING_VALIDATION", "authorization": "2026-10-15 用户明确同意派生标注，仅修正9条并保留全局原始数据；全部验收后完整测评及push", "dataset_roots": {"rxr": "data/derived/annotations/rxr-endpoint9-v1"}, "old_position": [5.300414085388184, 0.04583600163459778, 2.102294683456421], "new_position": [5.370209217071533, 0.009996652603149414, 2.14882493019104], "start_episode_ids": ["3888", "7963", "8829", "10116", "10287"], "goal_episode_ids": ["6171", "6243", "10646", "10757"], "scene_id": "mp3d/oLBMNvg9in8/oLBMNvg9in8.glb", "mesh_profile": "data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json", "claim": "Derived annotations and repaired mesh; not unchanged official benchmark", "mesh_recipe": "configs/navmesh-recipe.json"}` |
| annotation_derivative_sha256 | `6c16430072916de4f90e3ebf1f5e053942922524fbfec499a11a35bba7b4090e` |

## 正式指标与覆盖

| Dataset | 完成/计划 | SR (%) | SPL (%) | nDTW (%) | NE (m) | Oracle SR (%) | 普通失败 |
|---|---:|---:|---:|---:|---:|---:|---:|
| r2r | 1839/1839 | 65.633 | 57.278 | 65.370 | 3.9786 | 75.095 | 632 |

## 验证与可追溯证据

登记前核对了原始标注的完整身份集合、缺失/重复、输入与源码哈希、原生指标和轨迹独立复算，以及模型输出解析到实际primitive动作的一致性。普通导航失败仍计入分母。

| 运行目录内文件 | SHA-256 |
|---|---|
| run_manifest.json | `894e674fc0ac53169fbcbcc15ff11d302571bd07f4062bb7eeb53346a6947a9d` |
| results.jsonl | `e209e6088f704b792d3d163726116741624a25a89f7ad99055de83d1c02225f5` |
| independent_metrics.json | `06a645c27b90db2e46226911a1fcc1c00cee2955d2ea3dde795d3b7323febf87` |
| semantic_audit.json | `0973160279845ce534fe7030763be0785b6c00eea8e8250f3c9650b78a977953` |
| effective-configs.json | `2141f34387a578c2de99b29af590c4f5109dabc9c2a26beaf89aaf19a3c69187` |
| summary.json | `6b80e13cb974ef0358190d08a1702a97f52171dac05cc70b40a82d4cb07e0c57` |
| validation.json | `1c1936730a09a35daeb10c8f04283a757367a52e4555743254cfa2fd6a73075b` |

## 协议与结论边界

修复网格使用独立版本，不与旧网格历史成绩直接计算收益。模型到动作的一致性验证不等于每条导航语义正确；实际导航失败如实保留。33条修复过程、所有尝试和限制见[本阶段结论](../docs/zx/2026-10-14-2-conclusion-基线重建与全量测评.md)。
