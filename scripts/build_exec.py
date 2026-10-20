"""Constrain dependency installation to new owned build directories, excluding archives."""

import os, sys
from pathlib import Path
from workspace import ROOT
from landlock import restrict


def main():
    command = sys.argv[1:]
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise SystemExit("Provide the build command")
    writable = []
    for rel in (
        "runtime",
        ".cache",
        "upstream",
        "src",
        "configs/locks",
        "outputs",
        "logs",
        "build",
        "dist",
    ):
        p = ROOT / rel
        for ancestor in [p, *p.parents]:
            if ancestor == ROOT:
                break
            if ancestor.is_symlink():
                raise RuntimeError("Build path traverses symlink: " + str(ancestor))
        if ROOT not in p.resolve().parents:
            raise RuntimeError("Build path escapes workspace")
        p.mkdir(parents=True, exist_ok=True)
        writable.append(p)
    for rel in ("tmp", "xdg", "matplotlib", "triton", "cuda", "ccache"):
        (ROOT / ".cache" / rel).mkdir(exist_ok=True)
    for name in ("/dev/null", "/dev/zero", "/dev/urandom", "/dev/shm"):
        writable.append(Path(name))
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:64])
    abi = restrict(writable)
    os.environ.update(
        {
            "CASE1_BUILD_PROTECTED": "1",
            "CASE1_BUILD_LANDLOCK_ABI": str(abi),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "CUDA_VISIBLE_DEVICES": "",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "TMPDIR": str(ROOT / ".cache/tmp"),
            "XDG_CACHE_HOME": str(ROOT / ".cache/xdg"),
            "MPLCONFIGDIR": str(ROOT / ".cache/matplotlib"),
            "TRITON_CACHE_DIR": str(ROOT / ".cache/triton"),
            "CUDA_CACHE_PATH": str(ROOT / ".cache/cuda"),
            "CCACHE_DIR": str(ROOT / ".cache/ccache"),
        }
    )
    os.chdir(ROOT)
    os.execvpe(command[0], command, os.environ)


if __name__ == "__main__":
    main()
