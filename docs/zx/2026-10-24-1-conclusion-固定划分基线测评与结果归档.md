# 固定划分 AwareVLN baseline 测评与结果归档结论

状态：R2R/RxR完整推理、独立审计、结果登记、对比总表、精确归档和GitHub发布均已完成；main分支commit/tree已核验。对应[执行计划](2026-10-24-1-plan-固定划分基线测评与结果归档.md)。本轮不训练模型、不重跑原始旧baseline、不改Oracle/Landmark工作。

## 范围、数据与身份

用户指定`/data/zy/vln/data/checkpoint-choice/VLN`固定14叶子、seed86 A/B/Remaining清单，并明确采用已发布endpoint9修复协议。按授权创建`/data/zy/vln/data/checkpoint-choice/VLN-awareVLN`独立副本：R2R 1,839条原annotation/GT不变，RxR-US沿用endpoint9版本，9条annotation和5条GT有逐字段差异台账。全体3,062任务、6,124条源annotation/GT记录哈希检查通过；14叶子的ID、去重、互斥、完整并集和Habitat原生读取均通过，原VLN目录未修改。原VLN `_SUCCESS`所指的历史audit目录缺失；新副本保存本次独立核验，不冒充旧回执。场景、权重、共享环境仍只读复用。

范围：R2R val_unseen/en=1,839，RxR-US val_unseen/guide/en-US=1,223。RxR标注协议`awarevln-scene-minimal-endpoint9-v2`，mesh profile SHA `85328a019b541b1336c7f2d7ae6d50341d68a9b0fe20f3ee719070918e4d036c`。Plan SHA `feeeee2f57433a37a533c06eaba4b4659b8ed5aa9bae9570647732457a318f01`，assignment SHA `6812d6a76f0b4e1c0104301608f133e7df99764a1c6f667418d2478575c8f4ec`。物化台账及差异：`/data/zy/vln/data/checkpoint-choice/VLN-awareVLN/audit/materialization.json`。R2R manifest SHA `894e674fc0ac53169fbcbcc15ff11d302571bd07f4062bb7eeb53346a6947a9d`，RxR manifest SHA `f724637cecd0408abffa35f7047f188df9d87b8f0dcea7f9a04c996ea05ae439`。基线模型SHA `f467265fc17f68cbc256ef4a65b8d196e8317a316cb858102d72095f2cdf8df5`。

## 两套完整结果与审计

| 数据集 / 新run | 完成/分母 | SR | SPL | nDTW | NE | Oracle SR | 普通导航失败 | 非有限/运行错误 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| R2R endpoint9 | 1,839/1,839 | 65.633496% | 57.278175% | 65.369522% | 3.978647m | 75.095160% | 632 | 0/0 |
| RxR-US endpoint9 | 1,223/1,223 | 67.620605% | 55.934696% | 67.661981% | 4.279348m | 75.143091% | 396 | 0/0 |

两个新run均通过完整任务覆盖/重复检查、模型输出到动作语义审计、独立轨迹指标复算和validate_results；所有指标有效覆盖等于完整分母，nonfinite=0，runtime error=0。普通失败全部保留。

14个分区及A1+A2/A/B1+B2/B/Full的逐任务聚合在[统一总表](../../results-show/MODEL_TEST_RESULTS.md)和[新run详情](../../results-show/checkpoint-choice-20261024.md)。原docs/results内容已字节校验迁入根results-show，登记索引保留旧记录并追加两条新run。

R2R提前审计和主控制器最终审计均PASS并绑定同一manifest/results SHA。两次semantic JSON哈希不同；早期原semantic JSON被主控制器覆盖，早期和最终动作审计日志均显示1839任务、fallback调用1、errors0。最终semantic文件由最终validation绑定，是本次权威回执；不宣称两版semantic JSON字节一致。

## 与旧完整endpoint9 run逐任务对照

同数据集全部task_key相同；model、base config、environment、profile、benchmark、endpoint9 annotation/GT相同；427个冻结的model/data/evaluator策略文件逐SHA一致。整体source SHA不同，因为新的固定子集数据绑定和报告功能进入源码身份。逐任务五项指标在绝对1e-12容差下差异均0；终止原因、primitive动作步数、模型调用数差异也均0。R2R 1,839条、RxR 1,223条trace SHA全部不同，不声称原始轨迹字节一致。新旧配对差值（新减旧）全部为0；逐分区差值已在总表列出。

旧R2R保持retracted：既有额外严格几何审计发现5处off-mesh。本次标准动作语义、指标复算和validation通过不解除该独立几何限制，不能将新run登记解释为修复了off-mesh。旧RxR登记complete不变。新RxR采用用户授权的9条annotation/5条GT endpoint9派生修正；原标注、场景几何均未改。

## 成本与资源

控制器从`2026-10-24T08:31:07.475722+00:00`运行至source-freeze CLOSED `2026-10-25T09:25:34.158917+00:00`，端到端墙钟约24.907小时。14个worker回执累计批次墙钟：R2R 35.535小时、RxR 34.668小时。批次并行重叠，两个和不是端到端墙钟，也不是CPU用时。退出worker没有最终CPU计数器，CPU总秒未知，不估填。逐worker开始/结束/GPU/墙钟证据见`outputs/checkpoint-choice-20261024-shared24-v1/final-review-receipt.json`。

GPU仅4–7；本任务进程树五秒采样最大23758MiB/24,576MiB。本采样不是硬件级隔离，也不证明采样间瞬时峰值。CPU用户更新后总上限72、高编号优先、nice10；稳定32个逻辑核，活跃worker每个8核。资源更新前已启动并完成的早期worker，其原启动亲和性保留在worker-done回执；尚未结束的worker由sidecar重绑。没有修改外部进程亲和性或优先级，详细变更见`outputs/checkpoint-choice-20261024-shared24-v1/cpu-tail-changes.jsonl`和资源closeout。

## 精确归档与Git交付

临时辅助脚本已按allowlist逐SHA归档：本地42个、服务器2个；清单[intermediate-cleanup-20261025.json](../../results-show/intermediate-cleanup-20261025.json)，原始runs、逐任务结果、图像、轨迹、worker日志、manifest、失败、审计和源码快照完整保留。用户所有权未确认的process-show目录及另阶段plan/conclusion保留且不暂存。此前clean-export历史证据也保留；归档`outputs/checkpoint-choice-20261024-shared24-v1/cleanup-archive/clean-vln-checkpoint-choice-20261025.tar`对应归档时暂存树`c6d76a054b34d851afe71e6a6c5110b4f9347314`，SHA256见`outputs/checkpoint-choice-20261024-shared24-v1/clean-export-archive-receipt.json`，它只作为该时间点的来源快照，不代表最终发布树；`.cache`源副本在字节校验后移除。最终待发布树由末次prepush audit单独核验。

结果包已以正常追加提交推送到GitHub `woaijieyang/FirstPaper-VLN` 的`main`，未强推。提交SHA `1f79a7cb6747d03b7b5b1f370e73dfab6c6e71fd`，tree `bc3d6a4d6af27361be7dea94b2094cc3381cdfae`，parent `c3b5010c8a5e4efdf1a7063bc0f2f95df6ff9376`，message `awareVLN-baseline-construct`。成功push后，GitHub REST API核对到完全相同的SHA/tree/parent/message；本地远端跟踪核对也匹配。发布回执为`outputs/publication/push-verified-20261025.json`（运行目录忽略文件）；main中的本结论记录了提交身份及核验方式。
