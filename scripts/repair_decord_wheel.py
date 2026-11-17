"""Repair Decord 0.6.0's inconsistent internal wheel tag, preserving payload bytes."""

import subprocess, sys, zipfile
from pathlib import Path
from workspace import ROOT, atomic_json, digest

SOURCE_SHA = "51997f20be8958e23b7c4061ba45d0efcd86bffd5fe81c695d0befee0d442976"


def main():
    if Path(sys.prefix).resolve() != ROOT / "runtime/awarevln":
        raise RuntimeError("Independent Python required")
    folder = ROOT / ".cache/wheel-sources"
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "decord-0.6.0-py3-none-manylinux2010_x86_64.whl"
    if not source.exists():
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--no-deps",
                "--dest",
                str(folder),
                "decord==0.6.0",
            ],
            check=True,
        )
    if digest(source) != SOURCE_SHA:
        raise RuntimeError("Unexpected official wheel bytes")
    corrected = folder / "decord-0.6.0-1-py3-none-manylinux2010_x86_64.whl"
    # The official archive also has a stale RECORD hash for top_level.txt.
    # Rebuild metadata after checking the exact whole-wheel source hash above.
    from wheel.wheelfile import WheelFile

    with zipfile.ZipFile(source) as original, WheelFile(corrected, "w") as rebuilt:
        for member in original.infolist():
            if member.filename.endswith(".dist-info/RECORD"):
                continue
            content = original.read(member.filename)
            if member.filename.endswith(".dist-info/WHEEL"):
                old = b"Tag: cp36-cp36m-manylinux2010_x86_64"
                if content.count(old) != 1:
                    raise RuntimeError("Unexpected original tag metadata")
                content = content.replace(
                    old, b"Build: 1\nTag: py3-none-manylinux2010_x86_64"
                )
            rebuilt.writestr(member, content)
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(corrected) as after:
        if set(before.namelist()) != set(after.namelist()):
            raise RuntimeError("Wheel member set changed")
        changes = [n for n in before.namelist() if before.read(n) != after.read(n)]
        if set(changes) != {
            "decord-0.6.0.dist-info/WHEEL",
            "decord-0.6.0.dist-info/RECORD",
        }:
            raise RuntimeError("Unexpected payload change")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--force-reinstall",
            str(corrected),
        ],
        check=True,
    )
    atomic_json(
        ROOT / "outputs/setup/decord-wheel-repair.json",
        {
            "source_sha256": SOURCE_SHA,
            "corrected_sha256": digest(corrected),
            "changed_members": changes,
            "upstream_stale_record_entry": "decord-0.6.0.dist-info/top_level.txt",
            "all_code_and_native_payloads_byte_identical": True,
            "reason": "Official py3-none wheel contains cp36-cp36m internal tag; ctypes C API, no CPython extension ABI. Restore official published filename tag using wheel tool.",
            "upstream_ffi": "https://github.com/dmlc/decord/blob/v0.6.0/python/decord/_ffi/base.py",
        },
    )


if __name__ == "__main__":
    main()
