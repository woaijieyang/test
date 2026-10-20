# 第三方来源

AwareVLN https://github.com/GWxuan/AwareVLN，Apache-2.0，保留原LICENSE和版权。Habitat-Lab/Sim使用官方0.1.7，实际源码及构建身份记入依赖锁，保留各自许可。MP3D、标注、模型只读复用，不随Git发布，使用遵循原授权。

Recast/Detour 隔离网格构建诊断复用已冻结 Habitat-Sim 的 Recast 源码，遵循其 zlib 许可并保留原版权和许可文本。实验工具回移植官方修复 [PR #626](https://github.com/recastnavigation/recastnavigation/pull/626)，commit `9432fd6381d5b7c0567b06e6baff3783e80a3eb1`，明确标记为派生构建；不表示安装中的 Habitat-Sim 已升级。构建源码/工具身份、旧版对照和实际采用状态见导航连通性专项 conclusion。第三方完整副本及编译产物留在忽略目录，不作为自有原创代码发布。

补充诊断来源：Recast官方PR #672 / commit 3e94c3b6fcb5361bc30e87cacfa0ff46bde37a2c，原zlib许可；仅在忽略的.cache中隔离回补两处ledge边界比较，未升级安装环境。来源与对照证据见导航连通性专项conclusion及outputs/landmark-connectivity/recast672-boundary-test.json。
