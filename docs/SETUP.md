# 独立环境搭建与复现

本指南描述部署入口与验收条件。各条命令的实际执行、失败和通过证据见阶段 conclusion；在验收完成前，不把安装说明当作安装成功回执。

## 工作根与前置条件

所有服务器操作从 `/data/zy/vln/case1` 开始。首次迁移由控制器确认归档清单、哈希回执及目的路径后才导入源码。新环境不依赖 backup 或旧 case1 源码。环境脚本自身不读取迁移控制目录，供干净导出使用。

部署采用冻结的官方 AwareVLN 源码。当前起点为 Python 3.10、Habitat-Lab/Sim 0.1.7、Torch 2.3.0 和 Transformers 4.37.2。实际依赖锁、上游提交和模块位置需要在构建后记录，并以本次测试验证。

## 构建入口及目录

```bash
bash scripts/setup_environment.sh
```

环境放在 `runtime/awarevln`，构建工具在 `runtime/tools`，缓存和临时文件在 `.cache/`，第三方源码在 `upstream/`。micromamba 可由 `MAMBA_EXE` 指向既有工具，复制到任务目录后记录 SHA；共享环境不被激活或修改。

构建启动器限制写入范围并隐藏 GPU。包管理器不能向 backup、共享安装、全局数据或用户目录写缓存。安装过程中的权限错误必须诊断，不能放宽到全局可写来通过。

官方 README 与 pyproject 的 WebDataset 要求不一致；采用的兼容版本及理由必须记录，最终 `pip check` 需要无冲突。官方提供的 Transformers/DeepSpeed 替换文件只能应用于新环境，并保存逐文件前后哈希。
原生 BaseVLNCETrainer 无条件导入 TensorFlow；安装配方补齐 tensorflow-cpu 2.15.1 与 tensorboard 2.15.2，保留原导入而不改导航逻辑。该CPU版本有[Python 3.10 Linux发行包](https://pypi.org/project/tensorflow-cpu/2.15.1/)，也是本次只读核对既有共享安装所见的版本；新环境仍需独立安装与验证，不复用其包目录。

## 数据、环境与权重身份

```bash
python3 -B scripts/setup_data_links.py
scripts/with_runtime.sh --prepare-configs runtime/awarevln/bin/python -B scripts/build_derived_annotations.py
scripts/with_runtime.sh --prepare-configs runtime/awarevln/bin/python -B scripts/freeze_environment.py
scripts/with_runtime.sh runtime/awarevln/bin/python -B scripts/preflight.py
scripts/with_runtime.sh runtime/awarevln/bin/python -B scripts/check_native_dataset.py
scripts/with_runtime.sh runtime/awarevln/bin/python -B scripts/freeze_model.py
scripts/with_runtime.sh runtime/awarevln/bin/python -B scripts/check_model_inputs.py
```

环境身份包含实际解释器、关键包来源、Python/native 文件哈希和 Habitat 源码提交。只记录版本号不足以证明实际导入的是新环境。权重按已有官方文件重新计算哈希，不重复下载。

启动器设置独立的 Python 搜索路径，并隔离 HF、Torch、Triton、CUDA、Numba、图形驱动、Matplotlib 和 XDG 缓存；禁用 user-site，避免从其他环境意外导入。不得执行旧的全局激活脚本来替代本入口。

## 渲染与模型检查

EGL 必须使用与当前驱动匹配的库。先核对空闲 GPU，再验证真实 RGB/深度与 primitive 动作。CUDA mask 下的逻辑 GPU 与物理设备应能对应，不能只凭启动参数判断归属。

模型加载检查需确认官方模式 token、独立环境前缀、模型类的实际源码位置和 checkpoint。一次成功加载不能替代真实生成；随后需核对实际输入图像、token、处理后张量、输出及动作。

## 复现验收

干净导出必须能完成项目安装、预检和 CPU 回归，并明确实际使用的依赖身份。源码位置不得回落到旧工作区或 backup；原始权重和数据仍通过受保护入口复用。构建、依赖、组件渲染、模型调用和正式全量是不同门槛，分别记录。

## 从拟提交树验证干净导出

在完成文件边界审查并暂存拟交付文件后，运行 `python3 -B scripts/export_clean.py --name <唯一名称>`。脚本只导出 Git index 对应的 tree，拒绝数据/模型/环境/历史目录及链接成员，写入 `.cache/clean-<名称>` 并保存 tree 与 tar 哈希。导出本身仅表示文件集合成立，不是安装通过。

在该导出目录执行本指南的构建、数据链接、受保护预检和 `scripts/run_checks.py`，检查实际解释器及模块来自新导出目录。不得把原工作目录加入 PYTHONPATH 来修复导出错误。原始输入继续只读复用，导出中的环境、缓存和输出完全独立。各步成功后才能给干净导出验收记为 PASS。

## 已确认的版本兼容事项

`python-requirements.txt`固定pip发行版本/直接Git提交，`conda-explicit.txt`固定原生包URL；脚本在干净环境优先读取这些锁，构建前检查Habitat源码提交。原始freeze输出另存，不能直接拿含旧绝对路径的editable记录当可移植锁。

Gym0.17.3的cloudpickle约束与joblib1.6冲突，固定joblib1.5.2。Habitat-Lab核心安装不包含baselines的IL/DDP导入依赖，因此配方还显式安装lmdb、ifcfg和与该时期API兼容的moviepy1.0.3；不直接安装其旧rl清单中的TensorFlow1.13.1。Decord0.6.0官方wheel有内部标签及一项RECORD错误，`repair_decord_wheel.py`验证官方整体SHA后只重建两个元数据成员，逐文件确保其余内容相同；本环境真实视频解码已通过。原始与修正wheel均保留在缓存，安装仍需pip check。

OpenGL/EGL开发包仅装入runtime；CMAKE_PREFIX_PATH指向该环境。Habitat0.1.7的旧pybind11头文件通过已记录补丁补齐cstdint声明。所有修正均保留失败证据和源码/产物身份，不能拿包导入成功代替真实渲染与动作验证。

## 本次迁移备份与恢复

本地和服务器各自的旧内容位于 `backup/pre-rebuild-20261014-baseline/`。本地前后完整SHA通过；服务器前置完整SHA、移动及移动后路径/大小/链接通过，剩余后置全量哈希按用户最新指令停止，状态保存在 `.rebuild/archive-20261014-baseline-accepted.json`，不得改称完整后验哈希PASS。

恢复时先确认并停止本case自己的活动写入者，把当前新部署另行归档，确认原位置无同名冲突，再按 `.rebuild/archive-20261014-baseline-moves.jsonl` 逆向恢复原项目。链接按链接移动，不跟随复制全局目标；保留旧文档内容和绝对路径。服务器父Git不属于该恢复操作，不能操作 `/data/zy/vln/.git`。完整清单和恢复控制材料保存在各自 `.rebuild/`，均不发布到代码仓库。本次没有执行回滚。


## 受保护父进程与子进程

从普通shell进入项目运行环境仍必须使用`scripts/with_runtime.sh`。父进程已由该入口进入私有只读挂载并应用Landlock时，运行子任务应使用该父进程的Python直接`subprocess.Popen`，继承只读挂载、Landlock和NoNewPrivs；不要在该私有视图内再次初始化挂载/底层链接检查。重复初始化会把已挂载的真实目录误作不符合外层链接形态，本次17DRP诊断已保留这种启动失败。

环境变量CASE1_PROTECTION仅是记录，不能作为可绕过启动器的授权。继承路径已在自有夹具上验证直接写/链接逃逸均被拒绝、允许输出可写、共享视图只读，见`outputs/verification/runtime-child-inheritance-20261016/validation.json`及`tests/landmark_diagnostics/verify_runtime_child_inheritance.py`。这个修正仅作用于新诊断控制器，没有热改正式评测启动脚本或降低保护。


配置快照说明：当前launch/effective-config.yaml保存的是YACS显示形式，其中tuple表示未必是标准可重载YAML。它们用于身份与审阅；启动/复现应使用公开configs和冻结启动参数，不能把显示快照直接当作输入配置。当前实际RGB_SENSOR.POSITION=[0,1.25,0]，身体HEIGHT=1.5/RADIUS=0.1；按配置字段区分相机和碰撞体高度。原快照保持不变。
