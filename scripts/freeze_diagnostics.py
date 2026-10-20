"""Predeclare diagnostics from original mesh errors, never from candidate navigation scores."""

import argparse, math, json, os
from workspace import ROOT, atomic_json, read_json, digest

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--original-audit", required=True)
    a = p.parse_args()
    if not json.loads(os.environ.get("CASE1_PROTECTION", "{}")).get("prepare_configs"):
        raise SystemExit("Use with_runtime.sh --prepare-configs")
    audit = read_json(a.original_audit)
    bad = [r for r in audit["tasks"] if r["dataset"] == "rxr" and r["start_goal_distance"] is None]
    if len(bad) != 33 or any("oLBMNvg9in8" not in r["scene_id"] for r in bad):
        raise ValueError("Original33 cohort not reproduced")
    order = lambda r: (r["scene_id"], int(r["episode_id"]))
    r2r = [r for r in audit["tasks"] if r["dataset"] == "r2r"]
    chunk_size = math.ceil(len(r2r) / 8)
    pair = None
    for index, candidate in enumerate(r2r):
        if "oLBMNvg9in8" not in candidate["scene_id"]:
            continue
        prior = [
            r
            for r in r2r[(index // chunk_size) * chunk_size : index]
            if r["scene_id"] < candidate["scene_id"] and "oLBMNvg9in8" not in r["scene_id"]
        ]
        if prior:
            pair = (prior[0], candidate)
            break
    if pair is None:
        raise ValueError("No deterministic normal-to-affected pair in one logical shard")
    normal, affected = pair
    rxr_normal = sorted(
        [r for r in audit["tasks"] if r["dataset"] == "rxr" and "oLBMNvg9in8" not in r["scene_id"]],
        key=order,
    )[:2]
    specs = {
        "rxr33": [r["episode_id"] for r in sorted(bad, key=order)],
        "rxr-motion": sorted({r["episode_id"] for r in bad} | {r["episode_id"] for r in audit["tasks"] if r["dataset"]=="rxr" and not r["start_navigable"]},key=int),
        "r2r-pilot": [normal["episode_id"], affected["episode_id"]],
        "rxr-pilot": [r["episode_id"] for r in sorted(bad + rxr_normal, key=order)],
        "r2r-order-single": [affected["episode_id"]],
    }
    protocol=ROOT/'configs/annotation-protocol.json'
    if protocol.exists():
        cfg=read_json(protocol)
        specs['rxr-motion']=sorted(set(specs['rxr-motion'])|set(cfg['start_episode_ids'])|set(cfg['goal_episode_ids']),key=int)
    for name, ids in specs.items():
        atomic_json(ROOT / "configs/diagnostics" / (name + ".json"), ids)
    atomic_json(
        ROOT / "configs/diagnostics/selection.json",
        {
            "original_audit_sha256": digest(a.original_audit),
            "rule": "R2R normal A before affected B in the same raw logical shard, with A.scene < B.scene; repeat B alone on the same GPU and verify its observed episode sequence changes from >1 to 1. RxR original33 plus first two other-scene tasks. No navigation-score selection.",
            "groups": specs,
        },
    )
    print({k: len(v) for k, v in specs.items()})
