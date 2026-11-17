"""Independent trajectory metrics, no call to the native AwareVLN evaluator."""

import argparse, math, os
from workspace import read_json, atomic_json, digest, owned
from result_contract import rows
from preflight import load, task_key
from navmesh_audit import distance


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True)
    a = p.parse_args()
    if not os.environ.get("CASE1_PROTECTION"):
        raise SystemExit("Use protected runtime")
    import habitat_sim
    import numpy as np
    from fastdtw import fastdtw

    run = owned(a.run)
    manifest = read_json(run / "run_manifest.json")
    output = []
    episodes = {}
    references = {}
    profile = read_json(manifest["navmesh_profile"])
    finders = {}
    for ds, spec in manifest["datasets"].items():
        for ep in load(spec["annotation"])["episodes"]:
            if ds == "rxr" and ep["instruction"]["language"] != "en-US":
                continue
            episodes[task_key(ds, ep)] = ep
        references[ds] = load(spec["gt"])
    for row in rows(run / "results.jsonl"):
        ep = episodes[row["task_key"]]
        events = rows(run / row["trace_path"])
        scene = ep["scene_id"]
        asset = profile["assets"][scene]
        if scene not in finders:
            if digest(asset["navmesh_path"]) != asset["navmesh_sha256"]:
                raise ValueError("Navmesh drift")
            pf = habitat_sim.PathFinder()
            if not pf.load_nav_mesh(asset["navmesh_path"]):
                raise RuntimeError("Load navmesh failed")
            finders[scene] = pf
        positions = [events[0]["state_evaluator_only"]["position"]] + [
            e["after_evaluator_only"]["position"] for e in events if e["kind"] == "primitive_action"
        ]
        goals = [g["position"] for g in ep["goals"]]
        distances = [distance(finders[scene], x, goals) for x in positions]
        if any(d is None for d in distances):
            raise ValueError("Nonfinite trajectory geodesic " + row["task_key"])
        travelled = sum(math.dist(a, b) for a, b in zip(positions, positions[1:]))
        stopped = events[-1]["termination_reason"] == "stop"
        success = float(stopped and distances[-1] < 3.0)
        shortest = distances[0]
        spl = (
            success * (shortest / max(shortest, travelled))
            if max(shortest, travelled) > 0
            else success
        )
        unique = [positions[0]]
        for pos in positions[1:]:
            if pos != unique[-1]:
                unique.append(pos)
        gt = references[row["dataset"]][str(ep["episode_id"])]["locations"]
        dtw_value = fastdtw(
            unique, gt, dist=lambda a, b: float(np.linalg.norm(np.asarray(a) - np.asarray(b)))
        )[0]
        output.append(
            {
                "task_key": row["task_key"],
                "metrics": {
                    "sr": success,
                    "spl": spl,
                    "ndtw": math.exp(-dtw_value / (len(gt) * 3.0)),
                    "ne": distances[-1],
                    "oracle_sr": float(min(distances) < 3.0),
                },
                "path_length": travelled,
                "trace_sha256": digest(run / row["trace_path"]),
            }
        )
    atomic_json(
        run / "independent_metrics.json",
        {
            "method": "trajectory_recompute_v1",
            "manifest_sha256": digest(run / "run_manifest.json"),
            "results": output,
        },
    )
    print({"recomputed": len(output)})


if __name__ == "__main__":
    main()
