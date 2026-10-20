"""Make portable exact dependency locks from the successfully installed environment."""

import json, subprocess, sys, importlib.metadata, urllib.parse
from pathlib import Path
from workspace import ROOT, atomic_json, digest


def main():
    if Path(sys.prefix).resolve() != ROOT / "runtime/awarevln":
        raise RuntimeError("Use the independent installed environment")
    explicit = subprocess.check_output(
        [
            str(ROOT / "runtime/tools/micromamba"),
            "--no-rc",
            "env",
            "export",
            "--explicit",
            "-p",
            sys.prefix,
        ],
        text=True,
    )
    entries = [
        line for line in explicit.splitlines() if line and not line.startswith("#")
    ]
    if (
        not entries
        or entries[0] != "@EXPLICIT"
        or len(entries) < 2
        or any(
            not line.startswith("https://conda.anaconda.org/conda-forge/")
            for line in entries[1:]
        )
    ):
        raise RuntimeError("Conda export is not a portable exact URL lock")
    (ROOT / "configs/locks/conda-explicit.txt").write_text(explicit)
    lines = subprocess.check_output(
        [sys.executable, "-m", "pip", "freeze", "--all"], text=True
    ).splitlines()
    (ROOT / "configs/locks/python-freeze.txt").write_text("\n".join(lines) + "\n")
    installed = json.loads(
        subprocess.check_output(
            [sys.executable, "-m", "pip", "list", "--format=json"], text=True
        )
    )
    atomic_json(ROOT / "outputs/setup/installed-packages.json", installed)
    retained = []
    for line in lines:
        if not line or line.startswith("#"):
            continue
        if line.startswith("-e "):
            matched = False
            for dist_name, expected in (
                ("vila", ROOT),
                ("habitat", ROOT / "upstream/habitat-lab"),
            ):
                try:
                    dist = importlib.metadata.distribution(dist_name)
                except importlib.metadata.PackageNotFoundError:
                    continue
                direct = json.loads(dist.read_text("direct_url.json") or "{}")
                path = Path(
                    urllib.parse.unquote(
                        urllib.parse.urlsplit(direct.get("url", "")).path
                    )
                )
                if (
                    direct.get("dir_info", {}).get("editable")
                    and path.resolve() == expected
                ):
                    egg = urllib.parse.parse_qs(
                        urllib.parse.urlsplit(line[3:]).fragment
                    ).get("egg", [])
                    if dist_name in egg or Path(line[3:]).resolve() == expected:
                        matched = True
            if not matched:
                raise RuntimeError("Unexpected editable dependency: " + line)
            continue
        name = line.split(" @ ", 1)[0].split("==", 1)[0].lower().replace("_", "-")
        if name in (
            "habitat-sim",
            "habitat",
            "habitat-lab",
            "vila",
            "magnum",
            "corrade",
        ):
            continue
        if "file:" in line or str(ROOT) in line:
            if name not in (
                "packaging",
                "pip",
                "setuptools",
                "wheel",
                "decord",
                "joblib",
            ):
                raise RuntimeError("Machine-local dependency in portable lock: " + name)
            line = name + "==" + importlib.metadata.version(name)
        retained.append(line)
    target = ROOT / "configs/locks/python-requirements.txt"
    target.write_text("\n".join(sorted(retained, key=str.lower)) + "\n")
    native = {}
    for name in ("habitat-sim", "habitat-lab"):
        source = ROOT / "upstream" / name
        native[name] = {
            "url": subprocess.check_output(
                ["git", "-C", str(source), "remote", "get-url", "origin"], text=True
            ).strip(),
            "commit": subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
            ).strip(),
        }
    atomic_json(ROOT / "configs/locks/native-sources.json", native)
    atomic_json(
        ROOT / "outputs/setup/dependency-lock.json",
        {
            "status": "FROZEN_PENDING_CLEAN_REBUILD",
            "requirements_sha256": digest(target),
            "conda_explicit_sha256": digest(ROOT / "configs/locks/conda-explicit.txt"),
            "count": len(retained),
            "native_sources": native,
        },
    )
    print({"locked_distributions": len(retained)})


if __name__ == "__main__":
    main()
