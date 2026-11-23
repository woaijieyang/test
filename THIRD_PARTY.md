# 第三方来源

AwareVLN https://github.com/GWxuan/AwareVLN，Apache-2.0，保留原LICENSE和版权。Habitat-Lab/Sim使用官方0.1.7，实际源码及构建身份记入依赖锁，保留各自许可。MP3D、标注、模型只读复用，不随Git发布，使用遵循原授权。

Recast/Detour 隔离网格构建诊断复用已冻结 Habitat-Sim 的 Recast 源码，遵循其 zlib 许可并保留原版权和许可文本。实验工具回移植官方修复 [PR #626](https://github.com/recastnavigation/recastnavigation/pull/626)，commit `9432fd6381d5b7c0567b06e6baff3783e80a3eb1`，明确标记为派生构建；不表示安装中的 Habitat-Sim 已升级。构建源码/工具身份、旧版对照和实际采用状态见导航连通性专项 conclusion。第三方完整副本及编译产物留在忽略目录，不作为自有原创代码发布。

补充诊断来源：Recast官方PR #672 / commit 3e94c3b6fcb5361bc30e87cacfa0ff46bde37a2c，原zlib许可；仅在忽略的.cache中隔离回补两处ledge边界比较，未升级安装环境。来源与对照证据见导航连通性专项conclusion及outputs/landmark-connectivity/recast672-boundary-test.json。

HAMLET-v2 短时训练增量：Moment/TCL/窗口聚合设计参考官方 HAMLET N1.5 分支 https://github.com/myungkyuKoo/HAMLET-Isaac-GR00T/tree/n1.5 ，不复制 GR00T Action Expert，也不声称等价复现原论文。具体实现复用本仓库 AwareVLN 的图像/文本准备、GatedPromptInjection 和 CBEMRouter，并使用项目已有 PyTorch、Transformers、Accelerate 0.27.2 与 safetensors。新入口未引入额外 RL/DPO 框架；框架许可证和既有版权声明保持不变。
