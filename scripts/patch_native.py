"""Minimal audited build compatibility patches for frozen Habitat dependencies."""

import difflib
from workspace import ROOT, atomic_json, digest


def main():
    relative = "upstream/habitat-sim/src/deps/pybind11/include/pybind11/attr.h"
    p = ROOT / relative
    original = "4f6a98774b7f27cbc91e5762ff3bf2430e291807c9b26a1a158016efdda04bce"
    text = p.read_text()
    if "#include <cstdint>" not in text:
        if digest(p) != original:
            raise RuntimeError("Unknown pybind11 header version")
        updated = text.replace(
            '#include "cast.h"', '#include "cast.h"\n#include <cstdint>'
        )
        expected_patch = "".join(
            difflib.unified_diff(
                text.splitlines(True),
                updated.splitlines(True),
                fromfile=relative,
                tofile=relative,
            )
        )
        if (
            ROOT / "patches/native-pybind11-cstdint.patch"
        ).read_text() != expected_patch:
            raise RuntimeError("Native patch source does not match")
        p.write_text(updated)
    if digest(p) != "86d03bf90cc6027ceeba14d11f1ffd7911997cfe3e18298de4bc096d21f6daac":
        raise RuntimeError("Native header changed beyond the accepted patch")
    atomic_json(
        ROOT / "configs/locks/native-patches.json",
        [
            {
                "path": relative,
                "before_sha256": original,
                "after_sha256": digest(p),
                "reason": "attr.h uses std::uint16_t without including cstdint; standalone header probe fails with current system compiler.",
                "semantic_scope": "header declaration only; no navigation or simulator parameter changes",
            }
        ],
    )
    print("Native header compatibility applied")


if __name__ == "__main__":
    main()
