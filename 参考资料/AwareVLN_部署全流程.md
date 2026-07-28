# AwareVLN 本地与服务器部署全流程

> 适用仓库：/mnt/data/Project/vln/zx-experiment/AwareVLN  
> 项目主页：<https://gwxuan.github.io/AwareVLN/>  
> 官方代码：<https://github.com/GWxuan/AwareVLN>  
> 官方模型：<https://huggingface.co/gwx22/AwareVLN-ck>  
> 官方训练集：<https://huggingface.co/datasets/gwx22/AwareVLN>

本文覆盖两个可独立运行的工作流：

1. awarevln-eval：在 Habitat 中执行 R2R-CE 与 RxR-CE 的推理和评测。
2. awarevln-train：使用 AwareVLN reasoning 数据进行 SFT 训练。

本地工作站和服务器必须使用相同的代码、模型、数据格式、Python 与依赖版本。两者真正的区别只有 GPU 数量、绝对路径、网络、调度器和分布式启动参数；不要因切换到服务器而随意升级 Python、PyTorch、Transformers 或 Habitat。

---

## 1. 工作流、模型和数据

| 工作流 | 模型 | 数据 | 主命令 | 是否需要 Habitat |
|---|---|---|---|---|
| SFT 训练 | navila-llama3-8b-8f | reasoning 视频帧、标注 | scripts/train/sft_8frames.sh | 否 |
| R2R-CE 推理/评测 | awarevln | MP3D + R2R-CE | evaluation/scripts/eval/r2r.sh | 是 |
| RxR-CE 推理/评测 | awarevln | MP3D + RxR-CE | evaluation/scripts/eval/rxr.sh | 是 |

awarevln 是已训练的推理权重；navila-llama3-8b-8f 是官方 SFT 的训练起点。二者均在官方 checkpoint 仓库中。

训练和评测建议使用两个独立虚拟环境。评测依赖旧版 Habitat 0.1.7；训练则主要依赖 VILA 和 DeepSpeed。混装容易产生依赖冲突。

---

## 2. 系统、硬件和容量

### 2.1 软件前提

~~~text
系统：              Ubuntu 20.04 或 22.04
Python：            3.10
GPU：               NVIDIA CUDA GPU
驱动：              支持 CUDA 12.x 的 NVIDIA 驱动
CUDA Toolkit：      12.2
编译工具：          gcc/g++、cmake、ninja
下载工具：          git、git-lfs、curl 或 wget、tar
~~~

NVIDIA 驱动由系统维护，不应由 Python 环境替换。CUDA Toolkit 主要用于 Habitat-Sim 源码构建和编译扩展。

### 2.2 本地与服务器差异

| 项目 | 本地单机 | 服务器/多节点 |
|---|---|---|
| 环境版本 | 与服务器一致 | 与本地一致 |
| 最小评测 | GPU_LIST="0"，TOTAL_CHUNKS=1 | 可按 GPU 数分块 |
| 训练启动 | NNODES=1，NPROC_PER_NODE=1 | 按节点和每节点 GPU 数设置 |
| 官方训练默认值 | 仅适合冒烟/调试 | 默认 3 节点 × 8 GPU |
| 大数据路径 | 本机路径 | 所有节点可见的共享路径 |
| 图形后端 | 可用桌面 OpenGL | 推荐 headless/EGL |

当前 RTX 4090 48GB 可支持单卡推理、R2R 最小评测和训练冒烟测试。官方默认训练不是单卡完整复现配置；单卡必须先缩小 micro-batch。

### 2.3 存储预算

| 内容 | 大小 | 是否必须 |
|---|---:|---|
| 官方 checkpoint | 约 33.0 GB | 是 |
| 四个 reasoning 视频压缩包 | 约 233.9 GB | SFT 是 |
| reasoning 标注 | 约 1.4 GB | SFT 是 |
| 解压视频目录 | 额外约 234 GB 或更多 | SFT 是 |
| R2R-CE 预处理集 | 约 250 MB | R2R 是 |
| RxR-CE 数据 | 以官方包为准 | 仅 RxR 是 |
| MP3D 的 90 个场景 | 约 21 GB | 评测是 |
| 环境、缓存、日志 | 50--100 GB | 是 |

若同时保留压缩包和解压帧，建议至少有 650 GB 空闲空间；多实验服务器建议预留 1 TB。

---

## 3. 推荐目录布局

~~~text
PROJECT_ROOT=/mnt/data/Project/vln/zx-experiment
├── AwareVLN/
│   ├── .venv-awarevln-train/
│   ├── .venv-awarevln-eval/
│   ├── .vendor/habitat-lab-v0.1.7/
│   ├── ck/
│   │   ├── navila-llama3-8b-8f/
│   │   └── awarevln/
│   ├── data/AwareVLN-Dataset/
│   ├── outputs/
│   └── evaluation/
│       ├── data/
│       │   ├── datasets/R2R_VLNCE_v1-3_preprocessed/
│       │   ├── datasets/RxR_VLNCE_v0/
│       │   └── scene_datasets/mp3d/
│       └── eval_awarevln/
└── .codex/tmp/
~~~

已有 MP3D、R2R 等大数据若位于只读共享目录，推荐只在 AwareVLN/evaluation/data 下创建指向它们的符号链接。不要复制、移动或修改外部原始数据；下载缓存、模型、解压数据、训练输出和日志都保留在当前项目内。

---

## 4. 当前资源和部署缺口

当前可只读复用：

~~~text
/mnt/data/Project/vln/mp3d
    90 个 MP3D 场景，可复用

/mnt/data/Project/vln/data/datasets/R2R_VLNCE_v1-3_preprocessed_xlmr
    有 R2R episode，但目录名和官方配置不同
~~~

仍需准备：

1. 官方 AwareVLN checkpoint；
2. AwareVLN reasoning 训练集；
3. 官方 R2R_VLNCE_v1-3_preprocessed 数据包，推荐下载以严格匹配配置；
4. RxR-CE 数据，只在运行 RxR 时需要；
5. Human 数据，只在保留默认 +human 训练组合时需要。

现有 _xlmr R2R 数据不能在未做字段和配置验证前直接作为官方目标目录的等价替代。

---

## 5. 固定版本矩阵

| 组件 | 版本/来源 | 说明 |
|---|---|---|
| Python | 3.10 | 官方 AwareVLN 评测要求 |
| PyTorch | 2.3.0 | VILA / AwareVLN |
| torchvision | 0.18.0 | 与 Torch 配套 |
| FlashAttention | 2.5.8，cu122torch2.3，CPython 3.10 wheel | 训练与推理 |
| Transformers | Hugging Face v4.37.2 | 安装后覆盖仓库补丁 |
| DeepSpeed | 0.9.5 | ZeRO-3 SFT |
| WebDataset | 0.1.103 | 官方评测流程最终指定版本 |
| Habitat-Sim | 0.1.7 | VLN-CE 仿真器 |
| Habitat-Lab | v0.1.7 | VLN-CE 运行时 |

注意：pyproject.toml 中存在较新的 WebDataset 0.2.86，而官方评测说明要求最后安装 WebDataset 0.1.103。部署时应以 0.1.103 为最终版本，并在安装后显式确认。

---

## 6. 环境变量和缓存位置

部署前定义以下变量，确保所有可写缓存均位于项目内：

~~~bash
export PROJECT_ROOT=/mnt/data/Project/vln/zx-experiment
export AWAREVLN_ROOT=$PROJECT_ROOT/AwareVLN
export TMPDIR=$PROJECT_ROOT/.codex/tmp
export PIP_CACHE_DIR=$TMPDIR/pip-cache
export HF_HOME=$TMPDIR/huggingface
export HF_HUB_CACHE=$HF_HOME/hub
export TORCH_HOME=$TMPDIR/torch
export XDG_CACHE_HOME=$TMPDIR/xdg-cache
mkdir -p $TMPDIR $PIP_CACHE_DIR $HF_HOME $TORCH_HOME $XDG_CACHE_HOME
~~~

服务器上只需替换 PROJECT_ROOT，并确保所有训练节点都能访问数据和模型路径。

---

## 7. 建立训练环境

~~~bash
cd $AWAREVLN_ROOT
python3.10 -m venv .venv-awarevln-train
source .venv-awarevln-train/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install torch==2.3.0 torchvision==0.18.0 --index-url https://download.pytorch.org/whl/cu121
python -m pip install https://github.com/Dao-AILab/flash-attention/releases/download/v2.5.8/flash_attn-2.5.8+cu122torch2.3cxx11abiFALSE-cp310-cp310-linux_x86_64.whl
python -m pip install -e .
python -m pip install -e ".[train]"
python -m pip install -e ".[eval]"
python -m pip install git+https://github.com/huggingface/transformers@v4.37.2
python -m pip install webdataset==0.1.103
~~~

官方 FlashAttention 文件名必须是 cp310-cp310-linux_x86_64.whl，其中 linux_x86_64 使用下划线。

---

## 8. 建立评测环境

~~~bash
cd $AWAREVLN_ROOT
python3.10 -m venv .venv-awarevln-eval
source .venv-awarevln-eval/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install torch==2.3.0 torchvision==0.18.0 --index-url https://download.pytorch.org/whl/cu121
python -m pip install https://github.com/Dao-AILab/flash-attention/releases/download/v2.5.8/flash_attn-2.5.8+cu122torch2.3cxx11abiFALSE-cp310-cp310-linux_x86_64.whl
python -m pip install -r evaluation/requirements.txt
python -m pip install -e .
python -m pip install -e ".[eval]"
python -m pip install git+https://github.com/huggingface/transformers@v4.37.2
python -m pip install webdataset==0.1.103
~~~

每个运行 AwareVLN 的环境都应覆盖官方补丁：

~~~bash
cd $AWAREVLN_ROOT
SITE_PACKAGES=$(python -c 'import site; print(site.getsitepackages()[0])')
cp -rv llava/train/transformers_replace/* $SITE_PACKAGES/transformers/
cp -rv llava/train/deepspeed_replace/* $SITE_PACKAGES/deepspeed/
~~~

环境检查：

~~~bash
python - <<'PY'
import torch, transformers, webdataset
print(torch.__version__, torch.version.cuda)
print('cuda:', torch.cuda.is_available())
print('transformers:', transformers.__version__)
print('webdataset:', webdataset.__version__)
PY
~~~

预期：GPU 可见，Transformers 为 4.37.2，WebDataset 为 0.1.103。

---

## 9. 安装 Habitat-Sim 与 Habitat-Lab

只有 awarevln-eval 需要。AwareVLN 评测基于 VLN-CE，必须固定 Habitat 0.1.7。

### 9.1 Habitat-Lab

~~~bash
source $AWAREVLN_ROOT/.venv-awarevln-eval/bin/activate
cd $AWAREVLN_ROOT/.vendor
git clone --branch v0.1.7 --depth 1 https://github.com/facebookresearch/habitat-lab.git habitat-lab-v0.1.7
cd habitat-lab-v0.1.7
python -m pip install -r requirements.txt
python -m pip install -r habitat_baselines/rl/requirements.txt
python -m pip install -r habitat_baselines/rl/ddppo/requirements.txt
python setup.py develop --all
~~~

### 9.2 Habitat-Sim

二选一，并在本地和服务器采用同一种方法：

1. 官方 headless/conda 包，适合允许 Conda、希望避免 C++ 编译的服务器。

   ~~~bash
   conda install -c aihabitat -c conda-forge habitat-sim=0.1.7 headless
   ~~~

2. 源码构建，适合必须将环境严格置于项目目录、或旧版预编译包不可用的机器。固定到 Habitat-Sim v0.1.7，使用 headless/EGL 构建，并按该标签的官方 README 进行编译。

构建后必须验证：

~~~bash
python - <<'PY'
import habitat
import habitat_sim
print('habitat import succeeded')
print('habitat_sim import succeeded')
PY
~~~

### 9.3 NumPy 兼容性风险

当前 AwareVLN README 提到 evaluation/scripts/habitat_sim_autofix.py，但本地仓库未包含该脚本。完整评测前必须取得与当前代码匹配的 NumPy/Habitat-Sim 补丁，或核查 habitat_sim/utils/common.py 的兼容逻辑，然后用最小 episode 验证动作转换与渲染。

---

## 10. 下载模型和训练数据

### 10.1 Checkpoint

~~~bash
source $AWAREVLN_ROOT/.venv-awarevln-eval/bin/activate
python -m pip install huggingface_hub
hf download gwx22/AwareVLN-ck --local-dir $AWAREVLN_ROOT/ck
~~~

下载后检查：

~~~text
ck/awarevln/config.json
ck/awarevln/llm/model.safetensors.index.json
ck/navila-llama3-8b-8f/config.json
ck/navila-llama3-8b-8f/llm/model.safetensors.index.json
~~~

### 10.2 Reasoning SFT 数据

~~~bash
hf download gwx22/AwareVLN --repo-type dataset --local-dir $AWAREVLN_ROOT/data/AwareVLN-Dataset
cd $AWAREVLN_ROOT/data/AwareVLN-Dataset
for subset in r2r rxr r2rfollow rxrfollow; do tar -xzf reason/$subset/videos.tar.gz -C reason/$subset; done
~~~

检查：

~~~bash
find reason -path '*/videos/*' -type f | head
find reason -path '*/_anno_cot/annotations_shuffle_uni.json' -type f
find reason -path '*/_anno_cot/cot_new.json' -type f
~~~

### 10.3 Human 数据

默认训练组合为：

~~~text
r2r+rxr+r2rfollow+rxrfollow+human
~~~

但 Human 数据不随 AwareVLN 数据集发布。若保留 +human，必须按 NaVILA Dataset 的视频 ID、yt-dlp 和抽帧流程准备 Human/raw_frames 与标注。若不准备，训练时必须改为：

~~~text
r2r+rxr+r2rfollow+rxrfollow
~~~

---

## 11. 配置 R2R、RxR 和 MP3D

R2R 目标结构：

~~~text
evaluation/data/datasets/R2R_VLNCE_v1-3_preprocessed/
└── val_unseen/
    ├── val_unseen.json.gz
    └── val_unseen_gt.json.gz
~~~

MP3D 目标结构：

~~~text
evaluation/data/scene_datasets/mp3d/
└── 17DRP5sb8fy/
    └── 17DRP5sb8fy.glb
~~~

复用当前只读 MP3D 的示例：

~~~bash
mkdir -p $AWAREVLN_ROOT/evaluation/data/scene_datasets
ln -s /mnt/data/Project/vln/mp3d $AWAREVLN_ROOT/evaluation/data/scene_datasets/mp3d
~~~

RxR 仅在跑 RxR 时需要：

~~~text
evaluation/data/datasets/RxR_VLNCE_v0/
└── val_unseen/
    ├── val_unseen_guide.json.gz
    └── val_unseen_guide_gt.json.gz
~~~

建议先补齐 R2R 和 MP3D，验证最小 R2R，再下载和接入 RxR。VLN-CE 数据说明：<https://github.com/jacobkrantz/VLN-CE?tab=readme-ov-file#data>。

---

## 12. 训练配置与启动

训练脚本是 scripts/train/sft_8frames.sh，关键默认值如下：

~~~text
模型：             ./ck/navila-llama3-8b-8f
数据：             ./data
视觉编码器：       google/siglip-so400m-patch14-384
视频帧数：         8
精度：             bf16
DeepSpeed：        scripts/zero3.json
默认拓扑：         3 节点 × 8 GPU
~~~

### 12.1 单机单卡冒烟训练

~~~bash
source $AWAREVLN_ROOT/.venv-awarevln-train/bin/activate
cd $AWAREVLN_ROOT
export AWAREVLN_DATA_ROOT=$AWAREVLN_ROOT/data/AwareVLN-Dataset
export CKPT=$AWAREVLN_ROOT/ck/navila-llama3-8b-8f
export OUTPUT=$AWAREVLN_ROOT/outputs/awarevln-smoke
export NNODES=1
export NPROC_PER_NODE=1
export RANK=0
export MASTER_ADDR=127.0.0.1
export MASTER_PORT=29500
export DATA_MIXTURE=r2r+rxr+r2rfollow+rxrfollow
export WANDB_MODE=disabled
bash scripts/train/sft_8frames.sh
~~~

首次启动应从 per_device_train_batch_size=1 开始。确认单个 batch 的数据加载、前向、反向和 checkpoint 保存成功后，再调整 batch、累积步数和数据组合。

### 12.2 多节点服务器训练

每个节点必须有相同的代码提交、虚拟环境、模型、数据路径和可访问的主节点地址。3 节点、每节点 8 GPU 示例：

~~~bash
export NNODES=3
export NPROC_PER_NODE=8
export MASTER_ADDR=<rank-0-host>
export MASTER_PORT=29500
export RANK=<0-or-1-or-2>
bash scripts/train/sft_8frames.sh
~~~

使用 Slurm、Kubernetes 或平台调度器时，统一映射其 rank/host 变量到上述变量；不要让调度器和脚本同时独立决定 rank。

---

## 13. 推理和评测

### 13.1 评测前检查

~~~bash
source $AWAREVLN_ROOT/.venv-awarevln-eval/bin/activate
cd $AWAREVLN_ROOT/evaluation
python - <<'PY'
import torch, habitat, habitat_sim
print('CUDA:', torch.cuda.is_available())
print('Habitat imports succeeded')
PY
test -f ../ck/awarevln/config.json
test -f data/datasets/R2R_VLNCE_v1-3_preprocessed/val_unseen/val_unseen.json.gz
find data/scene_datasets/mp3d -name '*.glb' | wc -l
~~~

最后一条应输出 90。

### 13.2 R2R 单卡最小评测

~~~bash
cd $AWAREVLN_ROOT/evaluation
MODEL_PATH=../ck/awarevln TOTAL_CHUNKS=1 GPU_LIST="0" bash scripts/eval/r2r.sh
~~~

官方脚本默认评测整个 val_unseen。首次部署可通过调试 split 或 EVAL.EPISODE_COUNT 先验证少量 episode，但调试结果不能作为完整 benchmark。

结果目录：

~~~text
evaluation/eval_awarevln/awarevln/VLN-CE-v1/val_unseen/
~~~

### 13.3 R2R 多 GPU

~~~bash
MODEL_PATH=../ck/awarevln TOTAL_CHUNKS=8 GPU_LIST="0,1,2,3,4,5,6,7" bash scripts/eval/r2r.sh
~~~

多节点时，所有节点的 chunk-idx 区间必须完整且不重叠；所有输出完成后只执行一次结果 JSON 聚合。

### 13.4 RxR

~~~bash
cd $AWAREVLN_ROOT/evaluation
MODEL_PATH=../ck/awarevln TOTAL_CHUNKS=1 GPU_LIST="0" bash scripts/eval/rxr.sh
~~~

结果目录：

~~~text
evaluation/eval_awarevln/awarevln/RxR-VLN-CE-v1/val_unseen/
~~~

---

## 14. 部署验收顺序

1. Python 为 3.10，PyTorch 能发现 GPU。
2. Transformers、DeepSpeed、Habitat、Habitat-Sim 均可导入。
3. FlashAttention 可导入。
4. awarevln 和 navila-llama3-8b-8f 权重均完整。
5. MP3D 有 90 个 glb 文件，R2R 的 val_unseen 文件完整。
6. 最小 Habitat headless RGB observation 或 episode 成功。
7. 少量 R2R episode 推理成功并生成结果 JSON。
8. 完整 R2R val_unseen 聚合指标成功。
9. RxR 数据就绪后重复 RxR 验证。
10. 训练先通过单 batch 的数据加载、前向、反向与保存检查，再开始正式多卡训练。

---

## 15. 常见问题

| 现象 | 优先检查 |
|---|---|
| 找不到 habitat_sim | 是否激活评测环境；版本是否为 0.1.7 |
| NumPy / action 转换报错 | README 提到的 autofix 缺失；先处理 Habitat-Sim 补丁 |
| FlashAttention 无法加载 | Python ABI、Torch 2.3、CUDA runtime 与官方 wheel 是否一致 |
| torch.cuda.is_available() 为 False | 驱动、容器 GPU 挂载、CUDA_VISIBLE_DEVICES、CUDA PyTorch wheel |
| 找不到 glb | scene_datasets/mp3d 是否直接包含 90 个场景目录 |
| 找不到 episode JSON | evaluation/data/datasets 目录名与配置是否精确匹配 |
| 训练找不到 Human | 默认 DATA_MIXTURE 含 +human；补齐数据或移除该项 |
| 单卡 OOM | 从 batch 1 开始；保留 bf16/ZeRO-3；先短跑 |
| 多节点卡住 | 检查 MASTER_ADDR、端口、rank、NCCL 网卡、防火墙和共享文件系统 |

---

## 16. 可复现性记录

每次正式训练或评测都保存：

~~~text
AwareVLN git commit
Habitat-Sim / Habitat-Lab 版本
Python、PyTorch、CUDA、驱动版本
完整启动命令
CUDA_VISIBLE_DEVICES、NNODES、RANK、MASTER_ADDR
数据集和 checkpoint 来源、revision
运行配置文件副本
~~~

只要代码、模型、数据、配置、随机种子和包版本一致，本地单卡与服务器单卡应具备同等功能。服务器多卡与多节点的数值差异通常来自有效 batch size、数据切分和分布式归约顺序。

