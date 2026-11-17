# case2-hamlet-abc-20261031-v2-r2r

状态：complete。核验并登记时间：2026-11-01T20:49:48.141016+08:00（Asia/Singapore）。

## 实验身份

| 字段 | 实际身份 |
|---|---|
| run_id | `case2-hamlet-abc-20261031-v2-r2r` |
| 原始证据 | `/data/zy/vln/case2/outputs/independent-r2r-full-audit-20261101` |
| model | `HAMLET-Z V2 / CBEM aw4 seed10` |
| model_sha256 | `e15ef26d8d1d528cc556ba082e358b2067fbc079490a17e8f3aacd7ddd54addc` |
| source_sha256 | `ed8461301ce972ba9684e49fe199cf9b8295529859c0582a8b2d5d49c61b118a` |
| config_sha256 | `abdec7daca6a01630586e17ae473ae5c06cc9bcf42ef1e2c05650698e25ce65c` |
| navmesh_sha256 | `a94b5d48f065cee13db20b3fa0ee0cbfe18e9ae182bb6d763b27cd4456e970f9` |
| benchmark_sha256 | `9453e3ad54f596b99a849ab37467f775671bea8edce33da4a7bc21bdb80525a9` |
| split | `val_unseen` |
| language | `en` |
| base_config_sha256 | `42f1c1e197352eb449b3c706a4c5d40d8a72eba3ba1b12cba21ccbc8433f1189` |
| model_code_path | `/data/zy/vln/case2/src` |
| dataset_paths | `{"r2r": "/data/zy/vln/data/checkpoint-choice/VLN-awareVLN/annotations/r2r/val_unseen/val_unseen.json.gz"}` |
| dataset_manifest_path | `/data/zy/vln/case2/outputs/independent-r2r-full-audit-20261101/run_manifest.json` |
| navmesh_profile | `/data/zy/vln/case2/data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json` |
| annotation_protocol | `{"schema_version": 1, "protocol_id": "awarevln-scene-minimal-endpoint9-v2", "status": "AUTHORIZED_PENDING_VALIDATION", "authorization": "2026-10-15 用户明确同意派生标注，仅修正9条并保留全局原始数据；全部验收后完整测评及push", "dataset_roots": {"rxr": "data/derived/annotations/rxr-endpoint9-v1"}, "old_position": [5.300414085388184, 0.04583600163459778, 2.102294683456421], "new_position": [5.370209217071533, 0.009996652603149414, 2.14882493019104], "start_episode_ids": ["3888", "7963", "8829", "10116", "10287"], "goal_episode_ids": ["6171", "6243", "10646", "10757"], "scene_id": "mp3d/oLBMNvg9in8/oLBMNvg9in8.glb", "mesh_profile": "data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json", "claim": "Derived annotations and repaired mesh; not unchanged official benchmark", "mesh_recipe": "configs/navmesh-recipe.json"}` |
| annotation_derivative_sha256 | `bbdc611ce0e6f719356f0e40a0c74baeb5c7c2d9e5180321980dedbfd8daf775` |

## 正式指标与覆盖

| Dataset | 完成/计划 | SR (%) | SPL (%) | nDTW (%) | NE (m) | Oracle SR (%) | 普通失败 |
|---|---:|---:|---:|---:|---:|---:|---:|
| r2r | 1839/1839 | 65.144 | 56.625 | 65.273 | 3.9725 | 75.585 | 641 |

## 验证与可追溯证据

登记前核对了原始标注的完整身份集合、缺失/重复、输入与源码哈希、原生指标和轨迹独立复算，以及模型输出解析到实际primitive动作的一致性。普通导航失败仍计入分母。

| 运行目录内文件 | SHA-256 |
|---|---|
| run_manifest.json | `ed96ac4cf6b38f255d2c94c35836c8d6b010e8ba57810e09712d45c361c70b90` |
| results.jsonl | `0d5d11594234c41430fdbe2ee7cbb5b72a85caf073bd88dcc32c8fd5e18a317f` |
| independent_metrics.json | `822f1c2afb699a7e41b20096d8ed43d2837c80df9646eb036d1326fa2c64d152` |
| semantic_audit.json | `00e13a92f3b2da4da82d15a4654fa0aa65babef21f089d14dbfcf6a16cd06a7d` |
| effective-configs.json | `abdec7daca6a01630586e17ae473ae5c06cc9bcf42ef1e2c05650698e25ce65c` |
| hamlet_dataflow_audit.json | `7f02665137537c775943b535415bbc71d86fcc47d3e15fefbb3af723c4cca543` |
| summary.json | `479d7390b82be927d9ff8ebfa37f5e7654ffa116aa4b987d3eeb854f1223ea9f` |
| validation.json | `18eb5d45f128dfdc35470c68e440dd3e6a02fe7f76fcc625997a7302688efbc2` |

## 协议与结论边界

修复网格使用独立版本，不与旧网格历史成绩直接计算收益。模型到动作的一致性验证不等于每条导航语义正确；实际导航失败如实保留。33条修复过程、所有尝试和限制见[本阶段结论](../docs/zx/2026-10-14-2-conclusion-基线重建与全量测评.md)。
