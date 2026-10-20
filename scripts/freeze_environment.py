"""Record actual independent package/native identities, not just declared versions."""

import hashlib, importlib, json, os, subprocess, sys
from pathlib import Path
from workspace import ROOT, atomic_json, digest


def main():
    if (
        not os.environ.get("CASE1_PROTECTION")
        or Path(sys.prefix).resolve() != ROOT / "runtime/awarevln"
    ):
        raise RuntimeError("Independent protected runtime required")
    os.environ["CUDA_VISIBLE_DEVICES"] = ""  # Import/identity check cannot occupy an external GPU.
    modules = {}
    files = {}
    bases = []
    for name in (
        "habitat_sim",
        "habitat",
        "habitat_baselines",
        "torch",
        "transformers",
        "flash_attn",
        "magnum",
        "corrade",
        "numpy",
        "quaternion",
        "fastdtw",
        "PIL",
        "tokenizers",
        "torchvision",
        "accelerate",
        "peft",
        "deepspeed",
        "llava",
        "habitat_extensions",
        "vlnce_baselines",
    ):
        module = importlib.import_module(name)
        origin = Path(module.__file__).resolve()
        base = origin.parent
        if ROOT not in origin.parents:
            raise RuntimeError("Module escaped new deployment: " + name)
        modules[name] = {
            "origin": str(origin),
            "version": str(getattr(module, "__version__", "unversioned")),
        }
        bases.append(base)
    for base in sorted(set(bases)):
        for p in base.rglob("*"):
            if (
                p.is_file()
                and "__pycache__" not in p.parts
                and (p.suffix in (".py", ".so", ".json", ".yaml") or ".so." in p.name)
            ):
                files[str(p.resolve())] = digest(p)
    # Package wrappers import native extensions at the site-packages root.
    # Freeze those actual loaded extensions rather than their wrappers alone.
    for name in ('_corrade','_magnum','flash_attn_2_cuda'):
        module=importlib.import_module(name)
        origin=Path(module.__file__).resolve()
        if ROOT/'runtime/awarevln' not in origin.parents:
            raise RuntimeError('Native extension escaped environment: '+name)
        files[str(origin)]=digest(origin)
        modules[name]={'origin':str(origin),'version':'native-extension'}
    records = [{"path": path, "sha256": sha} for path, sha in sorted(files.items())]
    identity = hashlib.sha256(
        json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    commits = {
        name: subprocess.check_output(
            ["git", "-C", str(ROOT / "upstream" / name), "rev-parse", "HEAD"], text=True
        ).strip()
        for name in ("habitat-sim", "habitat-lab")
    }
    atomic_json(
        ROOT / "outputs/setup/runtime-files.json",
        {"environment_sha256": identity, "files": records},
    )
    atomic_json(
        ROOT / "configs/locks/environment-summary.json",
        {
            "python": sys.version,
            "prefix": sys.prefix,
            "modules": modules,
            "environment_sha256": identity,
            "file_count": len(records),
            "upstream_commits": commits,
            "runtime_files_manifest_sha256": digest(ROOT / "outputs/setup/runtime-files.json"),
        },
    )
    print({"environment_sha256": identity, "files": len(records), "modules": list(modules)})


if __name__ == "__main__":
    main()
