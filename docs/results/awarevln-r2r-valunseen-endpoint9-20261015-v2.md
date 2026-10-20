# awarevln-r2r-valunseen-endpoint9-20261015-v2

状态：retracted。核验并登记时间：2026-10-16T23:04:44.223736+08:00（Asia/Singapore）。

## 实验身份

| 字段 | 实际身份 |
|---|---|
| run_id | `awarevln-r2r-valunseen-endpoint9-20261015-v2` |
| 原始证据 | `/data/zy/vln/case1/outputs/awarevln-r2r-valunseen-endpoint9-20261015-v2` |
| model | `AwareVLN official` |
| model_sha256 | `f467265fc17f68cbc256ef4a65b8d196e8317a316cb858102d72095f2cdf8df5` |
| source_sha256 | `c2280a04c33b972034de5660954513b922e334fc55c2ef2b9d7e338e3ece6026` |
| config_sha256 | `dbe8f20d04caf873101f2abe52219a2110b39c49169d45b764e129945287c95e` |
| navmesh_sha256 | `85328a019b541b1336c7f2d7ae6d50341d68a9b0fe20f3ee719070918e4d036c` |
| benchmark_sha256 | `9453e3ad54f596b99a849ab37467f775671bea8edce33da4a7bc21bdb80525a9` |
| split | `val_unseen` |
| language | `en` |
| base_config_sha256 | `42f1c1e197352eb449b3c706a4c5d40d8a72eba3ba1b12cba21ccbc8433f1189` |
| model_code_path | `/data/zy/vln/case1/src` |
| dataset_paths | `{"r2r": "/data/zy/vln/data/raw_data/eval_annotations/R2R_VLNCE_v1-3_preprocessed/val_unseen/val_unseen.json.gz"}` |
| dataset_manifest_path | `/data/zy/vln/case1/outputs/awarevln-r2r-valunseen-endpoint9-20261015-v2/run_manifest.json` |
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
| run_manifest.json | `389ccee468a2882642e343679873dd5293cc809c2e1f6a96e91a228f9aad4024` |
| results.jsonl | `b8776925d2582351eed813d986e4c9de340529f84dbc392b8a526b213847955e` |
| independent_metrics.json | `4924db2f2f6cf2704293683eb213b826f0fba075705368b0d899eacc6efe31a9` |
| semantic_audit.json | `43864071198913a740bded63930bbbf10d1a064da4f8f3f424c572b562987d47` |
| effective-configs.json | `dbe8f20d04caf873101f2abe52219a2110b39c49169d45b764e129945287c95e` |
| summary.json | `3f6e8c5a2ec0fbd9aead118d6f0487cae1a8990689d64cc5d65ca5b3771a6b5a` |
| validation.json | `a7f5502d58b04aeb615fb964696f78fd399a082558d4ce2b2f7221eb711572e9` |

## 协议与结论边界

修复网格使用独立版本，不与旧网格历史成绩直接计算收益。模型到动作的一致性验证不等于每条导航语义正确；实际导航失败如实保留。33条修复过程、所有尝试和限制见[本阶段结论](../zx/2026-10-14-2-conclusion-基线重建与全量测评.md)。
