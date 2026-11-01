"""Enforce protected assets and owned caches before executing runtime commands."""

import argparse, glob, json, os, subprocess, sys
from pathlib import Path
from workspace import ROOT, owned
from setup_data_links import check_links
from landlock import restrict


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mounted", action="store_true")
    p.add_argument("--results-write", action="store_true")
    p.add_argument("--prepare-configs", action="store_true")
    p.add_argument("command", nargs=argparse.REMAINDER)
    a = p.parse_args()
    command = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not command:
        raise SystemExit("Provide executable and arguments after --")
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[-72:])
    check_links()
    if not a.mounted:
        probe = subprocess.run(
            ["unshare", "--user", "--map-root-user", "--mount", "true"], capture_output=True
        )
        if probe.returncode == 0:
            os.execvp(
                "unshare",
                [
                    "unshare",
                    "--user",
                    "--map-root-user",
                    "--mount",
                    "--propagation",
                    "private",
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--mounted",
                    *(["--results-write"] if a.results_write else []),
                    *(["--prepare-configs"] if a.prepare_configs else []),
                    "--",
                    *command,
                ],
            )
    if a.mounted:
        for source, target in [
            ("/data/zy/vln/data", ROOT / "data/.shared-ro"),
            ("/data/zy/vln/model/upstream", ROOT / "models/.shared-ro"),
        ]:
            if target.is_symlink() or target.resolve() != target:
                raise RuntimeError("Mount destination must be owned real directory")
            subprocess.run(["mount", "--bind", source, str(target)], check=True)
            subprocess.run(["mount", "-o", "remount,bind,ro", str(target)], check=True)
            if not os.statvfs(target).f_flag & os.ST_RDONLY:
                raise RuntimeError("Mount is not read-only")
    writable = []
    for rel in ("runtime", ".cache", "outputs", "logs", "data/derived", "configs/local"):
        d = owned(ROOT / rel)
        d.mkdir(parents=True, exist_ok=True)
        writable.append(d)
    if a.results_write:
        directory = owned(ROOT / "results-show")
        directory.mkdir(parents=True, exist_ok=True)
        writable.append(directory)
    if a.prepare_configs:
        for relative in ("configs/locks", "configs/diagnostics"):
            directory = owned(ROOT / relative)
            directory.mkdir(parents=True, exist_ok=True)
            writable.append(directory)
    for d in (
        ".cache/tmp",
        ".cache/huggingface",
        ".cache/torch",
        ".cache/xdg",
        ".cache/matplotlib",
    ):
        (ROOT / d).mkdir(exist_ok=True)
    os.environ.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "TMPDIR": str(ROOT / ".cache/tmp"),
            "HF_HOME": str(ROOT / ".cache/huggingface"),
            "HF_HUB_CACHE": str(ROOT / ".cache/huggingface/hub"),
            "HUGGINGFACE_HUB_CACHE": str(ROOT / ".cache/huggingface/hub"),
            "TRANSFORMERS_CACHE": str(ROOT / ".cache/huggingface/transformers"),
            "TORCH_HOME": str(ROOT / ".cache/torch"),
            "TORCH_EXTENSIONS_DIR": str(ROOT / ".cache/torch_extensions"),
            "TRITON_CACHE_DIR": str(ROOT / ".cache/triton"),
            "CUDA_CACHE_PATH": str(ROOT / ".cache/cuda"),
            "NUMBA_CACHE_DIR": str(ROOT / ".cache/numba"),
            "__GL_SHADER_DISK_CACHE_PATH": str(ROOT / ".cache/nvidia"),
            "XDG_CACHE_HOME": str(ROOT / ".cache/xdg"),
            "XDG_CONFIG_HOME": str(ROOT / ".cache/xdg-config"),
            "MPLCONFIGDIR": str(ROOT / ".cache/matplotlib"),
            "TOKENIZERS_PARALLELISM": "false",
            "TF_NUM_INTRAOP_THREADS": "1",
            "TF_NUM_INTEROP_THREADS": "1",
            "PYTHONPATH": str(ROOT / "src"),
            "PATH": str(ROOT / "runtime/awarevln/bin") + ":" + os.environ.get("PATH", ""),
            "AWAREVLN_ROOT": str(ROOT),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }
    )
    os.environ.pop("DISPLAY", None)
    os.environ.pop("PYTHONHOME", None)
    os.environ.pop("LD_PRELOAD", None)
    # Device I/O and POSIX shared memory; no additional ordinary filesystem roots.

    for pattern in (
        "/dev/nvidia*",
        "/dev/dri",
        "/dev/shm",
        "/dev/null",
        "/dev/zero",
        "/dev/urandom",
    ):
        writable.extend(Path(x) for x in glob.glob(pattern))
    abi = restrict(writable)
    os.environ["CASE1_PROTECTION"] = json.dumps(
        {
            "landlock_abi": abi,
            "readonly_mount": a.mounted,
            "results_write": a.results_write,
            "prepare_configs": a.prepare_configs,
        }
    )
    os.chdir(ROOT)
    os.execvpe(command[0], command, os.environ)


if __name__ == "__main__":
    main()
