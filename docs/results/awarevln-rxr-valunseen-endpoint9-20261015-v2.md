# awarevln-rxr-valunseen-endpoint9-20261015-v2

状态：complete。核验并登记时间：2026-10-18T08:32:26.374971+08:00（Asia/Singapore）。

## 实验身份

| 字段 | 实际身份 |
|---|---|
| run_id | `awarevln-rxr-valunseen-endpoint9-20261015-v2` |
| 原始证据 | `/data/zy/vln/case1/outputs/awarevln-rxr-valunseen-endpoint9-20261015-v2` |

派生标注协议：9条修正任务与1214条未修改标注任务分别统计；两组仅用于解释同一次完整测评，不作为独立的正式全量结果。

corrected_9: {"completed": 9, "metrics": {"sr": 0.6666666666666666, "spl": 0.6407238505262374, "ndtw": 0.8056647434556705, "ne": 1.9670594533284504, "oracle_sr": 0.6666666666666666}}
unchanged_1214: {"completed": 1214, "metrics": {"sr": 0.6762767710049423, "spl": 0.5587436761225527, "ndtw": 0.6756631392468406, "ne": 4.2964898420642, "oracle_sr": 0.7520593080724877}}
| model | `AwareVLN official` |
| model_sha256 | `f467265fc17f68cbc256ef4a65b8d196e8317a316cb858102d72095f2cdf8df5` |
| source_sha256 | `c2280a04c33b972034de5660954513b922e334fc55c2ef2b9d7e338e3ece6026` |
| config_sha256 | `9b2145b9df3d71385dd7afc8201d93b0c0d64fd950853b90c2bce5b229e5be9d` |
| navmesh_sha256 | `85328a019b541b1336c7f2d7ae6d50341d68a9b0fe20f3ee719070918e4d036c` |
| benchmark_sha256 | `556b628ad57c945448e013d98cb206619086da54788798703adce3a9b1cc5b9f` |
| split | `val_unseen` |
| language | `en-US` |
| base_config_sha256 | `bf4f2ec564f64b40b6abd5eb48ee1056bb2f3dc40777a1892b45510a13ab91b4` |
| model_code_path | `/data/zy/vln/case1/src` |
| dataset_paths | `{"rxr": "/data/zy/vln/case1/data/derived/annotations/rxr-endpoint9-v1/val_unseen/val_unseen_guide.json.gz"}` |
| dataset_manifest_path | `/data/zy/vln/case1/outputs/awarevln-rxr-valunseen-endpoint9-20261015-v2/run_manifest.json` |
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
| run_manifest.json | `c775a735b6a31f30fb08d33a860c245350373777faa35bd5e4cf0c16875e7310` |
| results.jsonl | `7d0ab0f73b62d86f034fd3787baf9792322a6172527635ace5f2c2cd227b2064` |
| independent_metrics.json | `85e0bf89defaa8e8478a094c2bdb2f210faa160e6e68ca8518c91499d3ceb824` |
| semantic_audit.json | `070d53fc61adc586f4c3f516b5a7ef98598d2c60c16f50b4053e2c2ecf4cf6e6` |
| effective-configs.json | `9b2145b9df3d71385dd7afc8201d93b0c0d64fd950853b90c2bce5b229e5be9d` |
| summary.json | `3e7aa22c917caeb917b0c44db7d4c85d8d2a746bb810e9b6159bbd92646982c4` |
| validation.json | `76743a00e5a99b27e31ca4d2502e252a323ce66d73113a6d018e21f87c273ace` |

## 协议与结论边界

修复网格使用独立版本，不与旧网格历史成绩直接计算收益。模型到动作的一致性验证不等于每条导航语义正确；实际导航失败如实保留。33条修复过程、所有尝试和限制见[本阶段结论](../zx/2026-10-14-2-conclusion-基线重建与全量测评.md)。
