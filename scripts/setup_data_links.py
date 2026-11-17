"""Create exact non-destructive asset links, never download or alter their targets."""

import argparse, json, os
from pathlib import Path
from workspace import ROOT, atomic_json

LINKS = {
    "data/.shared-ro/raw_data": "/data/zy/vln/data/raw_data",
    "data/datasets/R2R_VLNCE_v1-3_preprocessed": "../.shared-ro/raw_data/eval_annotations/R2R_VLNCE_v1-3_preprocessed",
    "data/datasets/RxR_VLNCE_v0": "../.shared-ro/raw_data/eval_annotations/rxr_vlnce_v0",
    "data/scene_datasets/mp3d": "../.shared-ro/raw_data/scenes/mp3d",
    "models/.shared-ro/awarevln": "/data/zy/vln/model/upstream/awarevln",
    "models/awarevln": ".shared-ro/awarevln",
}


def check_link_parent(path):
    path = Path(path).absolute()
    if ROOT not in path.parents:
        raise ValueError("Link entry is outside the owned workspace")
    for ancestor in path.parents:
        if ancestor == ROOT:
            break
        if ancestor.is_symlink():
            raise ValueError("Link creation traverses a parent symlink: " + str(ancestor))
    if path.parent.resolve() != ROOT and ROOT not in path.parent.resolve().parents:
        raise ValueError("Resolved link parent escapes the workspace")


def ensure_link(path, target):
    path = Path(path)
    check_link_parent(path)
    if path.is_symlink():
        if os.readlink(path) != target:
            raise ValueError("Existing link mismatch: " + str(path))
    elif path.exists():
        raise ValueError("Existing non-link must be preserved: " + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target, target_is_directory=True)
    if not path.is_dir():
        raise ValueError("Missing source target: " + str(path))


def check_links(root=ROOT):
    for rel, target in LINKS.items():
        p = root / rel
        if not p.is_symlink() or os.readlink(p) != target or not p.is_dir():
            raise ValueError("Incorrect asset link: " + rel)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    a = parser.parse_args()
    if a.check:
        check_links()
    else:
        # Validate all existing entries before mutating any link.

        for rel, target in LINKS.items():
            p = ROOT / rel
            check_link_parent(p)
            if p.is_symlink() and os.readlink(p) != target:
                raise ValueError("Existing link mismatch: " + rel)
            if p.exists() and not p.is_symlink():
                raise ValueError("Existing entity: " + rel)
        for rel, target in LINKS.items():
            ensure_link(ROOT / rel, target)
        check_links()
        atomic_json(
            ROOT / "configs/local/data-links.json",
            {
                "schema_version": 1,
                "links": [
                    {"path": k, "target": v, "resolved": str((ROOT / k).resolve())}
                    for k, v in LINKS.items()
                ],
            },
        )
    print(
        json.dumps(
            {"status": "PASS", "links": len(LINKS), "protection": "must run with with_runtime.sh"}
        )
    )


if __name__ == "__main__":
    main()
