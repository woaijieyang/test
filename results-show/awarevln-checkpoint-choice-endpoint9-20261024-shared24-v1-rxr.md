# awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr

状态：complete。核验并登记时间：2026-10-25T17:30:37.201443+08:00（Asia/Singapore）。

## 实验身份

| 字段 | 实际身份 |
|---|---|
| run_id | `awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr` |
| 原始证据 | `/data/zy/vln/case1/outputs/awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr` |

派生标注协议：9条修正任务与1214条未修改标注任务分别统计；两组仅用于解释同一次完整测评，不作为独立的正式全量结果。

corrected_9: {"completed": 9, "metrics": {"sr": 0.6666666666666666, "spl": 0.6407238505262374, "ndtw": 0.8056647434556705, "ne": 1.9670594533284504, "oracle_sr": 0.6666666666666666}}
unchanged_1214: {"completed": 1214, "metrics": {"sr": 0.6762767710049423, "spl": 0.558743676122552, "ndtw": 0.6756631392468412, "ne": 4.2964898420642, "oracle_sr": 0.7520593080724877}}
| model | `AwareVLN official` |
| model_sha256 | `f467265fc17f68cbc256ef4a65b8d196e8317a316cb858102d72095f2cdf8df5` |
| source_sha256 | `1336e3595037976c4d296a2c8d3779336f4ed23bf877508378af7541974368e4` |
| config_sha256 | `a6ffcf579fb3f171ebb3fcd2aa6b3b562646e2bbe692af57a0dcfb4f16519961` |
| navmesh_sha256 | `85328a019b541b1336c7f2d7ae6d50341d68a9b0fe20f3ee719070918e4d036c` |
| benchmark_sha256 | `556b628ad57c945448e013d98cb206619086da54788798703adce3a9b1cc5b9f` |
| split | `val_unseen` |
| language | `en-US` |
| base_config_sha256 | `bf4f2ec564f64b40b6abd5eb48ee1056bb2f3dc40777a1892b45510a13ab91b4` |
| model_code_path | `/data/zy/vln/case1/src` |
| dataset_paths | `{"rxr": "/data/zy/vln/data/checkpoint-choice/VLN-awareVLN/annotations/rxr/val_unseen/val_unseen_guide.json.gz"}` |
| dataset_manifest_path | `/data/zy/vln/case1/outputs/awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1-rxr/run_manifest.json` |
| navmesh_profile | `/data/zy/vln/case1/data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json` |
| annotation_protocol | `{"schema_version": 1, "protocol_id": "awarevln-scene-minimal-endpoint9-v2", "status": "AUTHORIZED_PENDING_VALIDATION", "authorization": "2026-10-15 用户明确同意派生标注，仅修正9条并保留全局原始数据；全部验收后完整测评及push", "dataset_roots": {"rxr": "data/derived/annotations/rxr-endpoint9-v1"}, "old_position": [5.300414085388184, 0.04583600163459778, 2.102294683456421], "new_position": [5.370209217071533, 0.009996652603149414, 2.14882493019104], "start_episode_ids": ["3888", "7963", "8829", "10116", "10287"], "goal_episode_ids": ["6171", "6243", "10646", "10757"], "scene_id": "mp3d/oLBMNvg9in8/oLBMNvg9in8.glb", "mesh_profile": "data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json", "claim": "Derived annotations and repaired mesh; not unchanged official benchmark", "mesh_recipe": "configs/navmesh-recipe.json"}` |
| annotation_derivative_sha256 | `6c16430072916de4f90e3ebf1f5e053942922524fbfec499a11a35bba7b4090e` |

## 正式指标与覆盖

| Dataset | 完成/计划 | SR (%) | SPL (%) | nDTW (%) | NE (m) | Oracle SR (%) | 普通失败 |
|---|---:|---:|---:|---:|---:|---:|---:|
| rxr | 1223/1223 | 67.621 | 55.935 | 67.662 | 4.2793 | 75.143 | 396 |

## 验证与可追溯证据

登记前核对了原始标注的完整身份集合、缺失/重复、输入与源码哈希、原生指标和轨迹独立复算，以及模型输出解析到实际primitive动作的一致性。普通导航失败仍计入分母。

| 运行目录内文件 | SHA-256 |
|---|---|
| run_manifest.json | `f724637cecd0408abffa35f7047f188df9d87b8f0dcea7f9a04c996ea05ae439` |
| results.jsonl | `8436c8a20c684cb874adfc538d51f71d354f1ba300284e8b36ee3171fe5007ef` |
| independent_metrics.json | `3308613d43f02ce1ffa8ff3a339f31ab8a622bce1ca24251156b7b0ed731c480` |
| semantic_audit.json | `55f6bdb2ff4c2bfeac1719e3121d2c281deada7e4994ec1e7184748c49ef684b` |
| effective-configs.json | `a6ffcf579fb3f171ebb3fcd2aa6b3b562646e2bbe692af57a0dcfb4f16519961` |
| summary.json | `24de024e00b99ec90a5d6066a08787433cce8be101298b82053b9be82444dde4` |
| validation.json | `0a43d3f16db2e65f33d19ce1dfae051a741a21233b4d60b02a3ee4233c008993` |

## 协议与结论边界

修复网格使用独立版本，不与旧网格历史成绩直接计算收益。模型到动作的一致性验证不等于每条导航语义正确；实际导航失败如实保留。33条修复过程、所有尝试和限制见[本阶段结论](../docs/zx/2026-10-14-2-conclusion-基线重建与全量测评.md)。
