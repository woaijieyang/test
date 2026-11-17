"""Resolve historical profile variants without guessing missing identity fields."""
import json
from pathlib import Path
from oracle.common.artifacts import digest


def resolve(case_root, task):
    root = Path(case_root).resolve()
    profile_path = Path(task["profile_path"])
    if not profile_path.resolve().is_relative_to(root) or digest(profile_path) != task["profile_sha256"]:
        raise RuntimeError("Task profile drift/escape")
    profile = json.loads(profile_path.read_text())
    asset = profile["assets"][f"mp3d/{task['scene']}/{task['scene']}.glb"]
    catalog_path = root / "outputs/landmark-connectivity/native-source-catalog-v1/catalog.json"
    if digest(catalog_path) != task["geometry_catalog_sha256"]:
        raise RuntimeError("Native geometry catalog drift")
    geometry = next(r for r in json.loads(catalog_path.read_text())["scenes"] if r["scene"] == task["scene"])
    scene_path = root / "data/scene_datasets/mp3d" / task["scene"] / (task["scene"] + ".glb")
    if digest(scene_path) != geometry["scene_sha256"]:
        raise RuntimeError("Original scene changed")
    if asset.get("scene_sha256", geometry["scene_sha256"]) != geometry["scene_sha256"]:
        raise RuntimeError("Profile and native geometry belong to different scenes")
    if profile["agent"] != {"height": 1.5, "radius": .1}:
        raise RuntimeError("Fixed body contract changed")
    if digest(geometry["receipt_path"]) != geometry["receipt_sha256"]:
        raise RuntimeError("Native geometry receipt drift")
    return asset, geometry
