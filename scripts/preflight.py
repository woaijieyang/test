"""Freeze exact dataset identity and scene assets. Not a navigation result."""

import argparse, gzip, json, os
from workspace import ROOT, atomic_json, digest

SPECS = {
    "r2r": ("R2R_VLNCE_v1-3_preprocessed", "val_unseen.json.gz", "val_unseen_gt.json.gz", 1839),
    "rxr": ("RxR_VLNCE_v0", "val_unseen_guide.json.gz", "val_unseen_guide_gt.json.gz", 1223),
}


def load(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def task_key(dataset, episode):
    instruction = episode.get("instruction", {}).get("instruction_id")
    return "|".join(
        (
            dataset,
            "val_unseen",
            "en-US" if dataset == "rxr" else "en",
            episode["scene_id"],
            str(episode["episode_id"]),
            str(instruction) if instruction is not None else "-",
        )
    )


def dataset_base(dataset):
    protocol=ROOT/'configs/annotation-protocol.json'
    if protocol.exists():
        cfg=json.loads(protocol.read_text())
        relative=cfg.get('dataset_roots',{}).get(dataset)
        if relative:return ROOT/relative/'val_unseen'
    return ROOT/'data/datasets'/SPECS[dataset][0]/'val_unseen'

def configure_dataset(config,dataset):
    if dataset=='rxr' and (ROOT/'configs/annotation-protocol.json').exists():
        base=dataset_base(dataset)
        config.TASK_CONFIG.DATASET.DATA_PATH=str(base/'val_unseen_{role}.json.gz')
        config.TASK_CONFIG.TASK.NDTW.GT_PATH=str(base/'val_unseen_{role}_gt.json.gz')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="outputs/preflight/data.json")
    a = parser.parse_args()
    if "CASE1_PROTECTION" not in os.environ:
        raise SystemExit("Use scripts/with_runtime.sh")
    result = {
        "schema_version": 1,
        "claim_scope": "offline_asset_identity",
        "datasets": {},
        "scenes": {},
        "protection": json.loads(os.environ["CASE1_PROTECTION"]),
    }
    for ds, (directory, anno, gt_name, count) in SPECS.items():
        base = dataset_base(ds)
        path = base / anno
        gtpath = base / gt_name
        episodes = load(path)["episodes"]
        if ds == "rxr":
            episodes = [e for e in episodes if e["instruction"]["language"] == "en-US"]
        gt = load(gtpath)
        rows = []
        auxiliary = []
        if ds == "rxr":
            follower_path = base / "val_unseen_follower_gt.json.gz"
            follower = load(follower_path)
            if set(gt) & set(follower):
                raise ValueError(
                    "Guide/follower GT keys overlap; audit native merge before proceeding"
                )
            auxiliary.append(
                {"path": str(follower_path.resolve()), "sha256": digest(follower_path)}
            )
        for e in episodes:
            if str(e["episode_id"]) not in gt:
                raise ValueError("Missing GT " + str(e["episode_id"]))
            rows.append(
                {
                    "task_key": task_key(ds, e),
                    "episode_id": str(e["episode_id"]),
                    "instruction_id": e.get("instruction", {}).get("instruction_id"),
                    "scene_id": e["scene_id"],
                }
            )
            scene = ROOT / "data/scene_datasets" / e["scene_id"]
            if not scene.is_file() or not scene.with_suffix(".navmesh").is_file():
                raise ValueError("Missing scene or navmesh")
            if e["scene_id"] not in result["scenes"]:
                result["scenes"][e["scene_id"]] = {
                    "glb": str(scene.resolve()),
                    "glb_sha256": digest(scene),
                    "navmesh": str(scene.with_suffix(".navmesh").resolve()),
                    "navmesh_sha256": digest(scene.with_suffix(".navmesh")),
                }
        if len(rows) != count or len({r["task_key"] for r in rows}) != count:
            raise ValueError("Wrong split identity/duplicates")
        result["datasets"][ds] = {
            "annotation": str(path.resolve()),
            "annotation_sha256": digest(path),
            "gt": str(gtpath.resolve()),
            "gt_sha256": digest(gtpath),
            "auxiliary_inputs": auxiliary,
            "tasks": rows,
            "count": count,
        }
    protocol_path=ROOT/'configs/annotation-protocol.json'
    if protocol_path.exists():
        result['annotation_protocol']=json.loads(protocol_path.read_text())
        result['annotation_protocol_sha256']=digest(protocol_path)
        derivative=ROOT/result['annotation_protocol']['dataset_roots']['rxr']/'manifest.json'
        result['derived_manifest_sha256']=digest(derivative)
    atomic_json(a.output, result)
    print(
        json.dumps(
            {
                "datasets": {d: v["count"] for d, v in result["datasets"].items()},
                "scenes": len(result["scenes"]),
                "scope": "no_model_or_navigation",
            }
        )
    )


if __name__ == "__main__":
    main()
