# case2-hamlet-abc-20261031-v2-rxr

状态：complete。核验并登记时间：2026-11-01T20:51:25.797310+08:00（Asia/Singapore）。

## 实验身份

| 字段 | 实际身份 |
|---|---|
| run_id | `case2-hamlet-abc-20261031-v2-rxr` |
| 原始证据 | `/data/zy/vln/case2/outputs/independent-rxr-full-audit-20261101` |

派生标注协议：9条修正任务与1214条未修改标注任务分别统计；两组仅用于解释同一次完整测评，不作为独立的正式全量结果。

corrected_9: {"completed": 9, "metrics": {"sr": 0.6666666666666666, "spl": 0.6407238505262374, "ndtw": 0.8056647434556704, "ne": 1.9670594533284504, "oracle_sr": 0.6666666666666666}}
unchanged_1214: {"completed": 1214, "metrics": {"sr": 0.6746293245469522, "spl": 0.5582082400417915, "ndtw": 0.6714152597209831, "ne": 4.363950912756278, "oracle_sr": 0.757001647446458}}
| model | `HAMLET-Z V2 / CBEM aw4 seed10` |
| model_sha256 | `e15ef26d8d1d528cc556ba082e358b2067fbc079490a17e8f3aacd7ddd54addc` |
| source_sha256 | `ed8461301ce972ba9684e49fe199cf9b8295529859c0582a8b2d5d49c61b118a` |
| config_sha256 | `40bed54efce2ff4f5095d3d4a23d389704d1ffdfc41620729a2981434ee00e85` |
| navmesh_sha256 | `a94b5d48f065cee13db20b3fa0ee0cbfe18e9ae182bb6d763b27cd4456e970f9` |
| benchmark_sha256 | `556b628ad57c945448e013d98cb206619086da54788798703adce3a9b1cc5b9f` |
| split | `val_unseen` |
| language | `en-US` |
| base_config_sha256 | `bf4f2ec564f64b40b6abd5eb48ee1056bb2f3dc40777a1892b45510a13ab91b4` |
| model_code_path | `/data/zy/vln/case2/src` |
| dataset_paths | `{"rxr": "/data/zy/vln/data/checkpoint-choice/VLN-awareVLN/annotations/rxr/val_unseen/val_unseen_guide.json.gz"}` |
| dataset_manifest_path | `/data/zy/vln/case2/outputs/independent-rxr-full-audit-20261101/run_manifest.json` |
| navmesh_profile | `/data/zy/vln/case2/data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json` |
| annotation_protocol | `{"schema_version": 1, "protocol_id": "awarevln-scene-minimal-endpoint9-v2", "status": "AUTHORIZED_PENDING_VALIDATION", "authorization": "2026-10-15 用户明确同意派生标注，仅修正9条并保留全局原始数据；全部验收后完整测评及push", "dataset_roots": {"rxr": "data/derived/annotations/rxr-endpoint9-v1"}, "old_position": [5.300414085388184, 0.04583600163459778, 2.102294683456421], "new_position": [5.370209217071533, 0.009996652603149414, 2.14882493019104], "start_episode_ids": ["3888", "7963", "8829", "10116", "10287"], "goal_episode_ids": ["6171", "6243", "10646", "10757"], "scene_id": "mp3d/oLBMNvg9in8/oLBMNvg9in8.glb", "mesh_profile": "data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json", "claim": "Derived annotations and repaired mesh; not unchanged official benchmark", "mesh_recipe": "configs/navmesh-recipe.json"}` |
| annotation_derivative_sha256 | `bbdc611ce0e6f719356f0e40a0c74baeb5c7c2d9e5180321980dedbfd8daf775` |

## 正式指标与覆盖

| Dataset | 完成/计划 | SR (%) | SPL (%) | nDTW (%) | NE (m) | Oracle SR (%) | 普通失败 |
|---|---:|---:|---:|---:|---:|---:|---:|
| rxr | 1223/1223 | 67.457 | 55.882 | 67.240 | 4.3463 | 75.634 | 398 |

## 验证与可追溯证据

登记前核对了原始标注的完整身份集合、缺失/重复、输入与源码哈希、原生指标和轨迹独立复算，以及模型输出解析到实际primitive动作的一致性。普通导航失败仍计入分母。

| 运行目录内文件 | SHA-256 |
|---|---|
| run_manifest.json | `b54f358bd2048d256c6d1cd5bc0a020ea3a20052ab73c820282ebac0b4572094` |
| results.jsonl | `a3bd338d51cb970df27ea328ff5cc40842121aab828c0e14e4887a6e8f3362df` |
| independent_metrics.json | `1ea91d7f4b2783bea94fc8c4df8b602d42fd4f70d54ea99393b19dd39724f733` |
| semantic_audit.json | `ca01146eb992d2a5005fd22bfbc69989b4b85428a2de6ffbd055c5a648a1fae3` |
| effective-configs.json | `40bed54efce2ff4f5095d3d4a23d389704d1ffdfc41620729a2981434ee00e85` |
| hamlet_dataflow_audit.json | `2a4326aac32f4380f61b6a8bc0d99ea1224bdf3917eb24ffdcd6cd4dfc6fb1cb` |
| summary.json | `22500ad29e600b1a4b043aa77045745039a8546b4600e9a41994681d80bdc216` |
| validation.json | `6f952e7aad7c5971ead73b27eac068797cbdea35d68a2b8d9579d4c8f5599124` |

## 协议与结论边界

修复网格使用独立版本，不与旧网格历史成绩直接计算收益。模型到动作的一致性验证不等于每条导航语义正确；实际导航失败如实保留。33条修复过程、所有尝试和限制见[本阶段结论](../docs/zx/2026-10-14-2-conclusion-基线重建与全量测评.md)。
