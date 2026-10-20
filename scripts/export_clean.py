"""Export exactly the proposed Git index for isolated deployment verification."""

import argparse, hashlib, subprocess, tarfile
from pathlib import Path
from workspace import ROOT, atomic_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    a = p.parse_args()
    if not a.name or any(
        c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in a.name
    ):
        raise ValueError("Use a lowercase immutable export name")
    if not (ROOT / ".git").is_dir():
        raise RuntimeError("Independent repository required")
    names = (
        subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
        .decode()
        .split("\0")
    )
    names = [n for n in names if n]
    if (
        not names
        or "pyproject.toml" not in names
        or "scripts/setup_environment.sh" not in names
    ):
        raise RuntimeError("Stage the complete proposed delivery before clean export")
    denied = {
        "backup",
        "upstream",
        "runtime",
        "data",
        "models",
        "outputs",
        "logs",
        ".cache",
        ".rebuild",
    }
    if any(Path(n).parts[0] in denied for n in names):
        raise RuntimeError("Ignored artifact in staged tree")
    tree = subprocess.check_output(["git", "write-tree"], cwd=ROOT, text=True).strip()
    dst = ROOT / ".cache" / ("clean-" + a.name)
    if dst.exists():
        raise RuntimeError("Prior clean export must be preserved")
    dst.mkdir(parents=True)
    archive = ROOT / ".cache" / ("clean-" + a.name + ".tar")
    with archive.open("xb") as f:
        subprocess.run(
            ["git", "archive", "--format=tar", tree], cwd=ROOT, stdout=f, check=True
        )
    with tarfile.open(archive) as t:
        for member in t:
            target = dst / member.name
            if (
                member.issym()
                or member.islnk()
                or not (member.isfile() or member.isdir())
            ):
                raise RuntimeError(
                    "Delivery may only contain regular files and directories"
                )
            if dst not in target.resolve().parents:
                raise RuntimeError("Unsafe export member")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(t.extractfile(member).read())
                target.chmod(member.mode & 0o777)
    atomic_json(
        ROOT / "outputs/verification" / ("clean-export-" + a.name + ".json"),
        {
            "status": "EXPORTED_PENDING_INSTALL_AND_TEST",
            "tree": tree,
            "destination": str(dst),
            "files": len(names),
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        },
    )
    print(str(dst))


if __name__ == "__main__":
    main()
