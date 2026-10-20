#!/usr/bin/env bash
# Build only inside case1; never activate or modify the shared environment.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$root"
case "$root" in
    /data/zy/vln/case1|/data/zy/vln/case1/.cache/clean-*) ;;
    *) echo 'Build root is outside the authorized workspace' >&2; exit 2 ;;
esac
# The migration controller checks the archive gate; clean exports need no .rebuild files.
if [[ "${CASE1_BUILD_PROTECTED:-}" != 1 ]]; then
    exec /usr/bin/python3 -B "$root/scripts/build_exec.py" -- bash "$root/scripts/setup_environment.sh" "$@"
fi
mkdir -p runtime/tools .cache/tmp .cache/pip .cache/mamba .cache/huggingface outputs/setup configs/locks
export TMPDIR="$root/.cache/tmp" PIP_CACHE_DIR="$root/.cache/pip" MAMBA_ROOT_PREFIX="$root/.cache/mamba" CONDA_PKGS_DIRS="$root/.cache/mamba/pkgs" HF_HOME="$root/.cache/huggingface" PYTHONDONTWRITEBYTECODE=1
export CMAKE_BUILD_PARALLEL_LEVEL=8 MAX_JOBS=8
export PYTHONNOUSERSITE=1
export PIP_CONFIG_FILE=/dev/null
unset PYTHONPATH PYTHONHOME LD_PRELOAD PIP_INDEX_URL PIP_EXTRA_INDEX_URL PIP_USER PIP_PREFIX PIP_TARGET PYTHONUSERBASE
if [[ ! -x runtime/tools/micromamba ]]; then
    cp "${MAMBA_EXE:-/data/zy/vln/harness/.cache/micromamba/bin/micromamba}" runtime/tools/micromamba
fi
sha256sum runtime/tools/micromamba > configs/locks/build-tool.sha256
if [[ ! -x runtime/awarevln/bin/python ]]; then
    if [[ -f configs/locks/conda-explicit.txt ]]; then
        runtime/tools/micromamba --no-rc create -y -p "$root/runtime/awarevln" --file configs/locks/conda-explicit.txt
    else
        runtime/tools/micromamba --no-rc create -y -p "$root/runtime/awarevln" --override-channels -c conda-forge python=3.10 pip setuptools=69 wheel cmake=3.22 ninja=1.11 git
    fi
fi
if [[ ! -f configs/locks/conda-explicit.txt ]]; then
    runtime/tools/micromamba --no-rc install -y -p "$root/runtime/awarevln" --override-channels -c conda-forge libgl-devel libglx-devel libopengl-devel libegl-devel
fi
export CMAKE_PREFIX_PATH="$root/runtime/awarevln"
py="$root/runtime/awarevln/bin/python"
export PATH="$root/runtime/awarevln/bin:$PATH"
if [[ -f configs/locks/python-requirements.txt ]]; then
    "$py" -m pip install --no-deps -r configs/locks/python-requirements.txt
    "$py" -m pip install --no-deps --no-build-isolation -e .
else
"$py" -m pip install -e .
"$py" -m pip install joblib==1.5.2 lmdb ifcfg moviepy==1.0.3 word2number python-Levenshtein deepspeed==0.9.5 gym==0.17.3 attrs fastdtw==0.3.4 dtw==1.4.0 jsonlines yacs tensorflow-cpu==2.15.1 tensorboard==2.15.2 'numpy-quaternion<2024' numba imageio imageio-ffmpeg gitpython matplotlib
"$py" -m pip install 'https://github.com/Dao-AILab/flash-attention/releases/download/v2.5.8/flash_attn-2.5.8+cu122torch2.3cxx11abiFALSE-cp310-cp310-linux_x86_64.whl'
fi
if [[ ! -d upstream/habitat-sim/.git ]]; then
    git clone --branch v0.1.7 --depth 1 --recursive --shallow-submodules https://github.com/facebookresearch/habitat-sim.git upstream/habitat-sim
fi
if [[ ! -d upstream/habitat-lab/.git ]]; then
    git clone --branch v0.1.7 --depth 1 https://github.com/facebookresearch/habitat-lab.git upstream/habitat-lab
fi
"$py" - <<'PY'
import json, pathlib, subprocess
p=pathlib.Path('configs/locks/native-sources.json')
if p.exists():
    for name, identity in json.loads(p.read_text()).items():
        actual=subprocess.check_output(['git','-C','upstream/'+name,'rev-parse','HEAD'],text=True).strip()
        if actual!=identity['commit']:
            raise RuntimeError('Frozen native source mismatch: '+name)
PY
"$py" scripts/patch_native.py
(
    cd upstream/habitat-sim
    "$py" setup.py bdist_wheel --headless --no-update-submodules
)
"$py" -m pip install --no-deps upstream/habitat-sim/dist/*.whl
"$py" -m pip install --no-deps --no-build-isolation -e upstream/habitat-lab
# Official compatibility replacements are scoped to this new environment only.
"$py" scripts/install_compatibility.py
"$py" scripts/repair_decord_wheel.py
"$py" -m pip check
"$py" -m pip freeze --all > configs/locks/python-freeze.txt
runtime/tools/micromamba --no-rc env export -p "$root/runtime/awarevln" --explicit > configs/locks/conda-explicit.txt
"$py" -m pip list --format=json > outputs/setup/installed-packages.json
"$py" scripts/freeze_dependencies.py
printf '%s\n' 'Environment installation finished; real model/render gates remain separate.'
