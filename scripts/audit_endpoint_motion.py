"""CPU PathFinder diagnosis of annotated off-mesh endpoints; never move annotations."""

import argparse, math, os
from workspace import atomic_json, digest, owned, read_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--audit", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    if not os.environ.get("CASE1_PROTECTION"):
        raise RuntimeError("Use protected runtime")
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    import habitat_sim

    audit = read_json(a.audit)
    cache = {}
    records = []
    for row in audit["tasks"]:
        if row["start_navigable"] and all(row["goals_navigable"]):
            continue
        scene = row["scene_id"]
        asset = audit["assets"][scene]
        if scene not in cache:
            if digest(asset["navmesh_path"]) != asset["navmesh_sha256"]:
                raise RuntimeError("Audited mesh changed")
            pf = habitat_sim.PathFinder()
            if not pf.load_nav_mesh(asset["navmesh_path"]):
                raise RuntimeError("Cannot load audited mesh")
            cache[scene] = pf
        pf = cache[scene]
        for role, position in [("start", row["start_position"])] + [
            ("goal", g) for g in row["goal_positions"]
        ]:
            if pf.is_navigable(position):
                continue
            snap = list(pf.snap_point(position))
            delta = [float(snap[i] - position[i]) for i in range(3)]
            if not all(math.isfinite(v) for v in snap):
                raise RuntimeError("Endpoint has no finite projection")
            item = {
                "task_key": row["task_key"],
                "role": role,
                "position": position,
                "projected_point_for_diagnosis_only": snap,
                "projection_delta_m": delta,
                "directional_probes": [],
            }
            if role == "start":
                for dx, dz in ((0.25, 0), (-0.25, 0), (0, 0.25), (0, -0.25)):
                    target = [position[0] + dx, position[1], position[2] + dz]
                    actual = list(pf.try_step(position, target))
                    item["directional_probes"].append(
                        {
                            "requested": target,
                            "returned": actual,
                            "distance_m": math.dist(position, actual),
                            "horizontal_m": math.hypot(
                                actual[0] - position[0], actual[2] - position[2]
                            ),
                        }
                    )
            records.append(item)
    probes = [s for r in records for s in r["directional_probes"]]
    summary = {
        "endpoints": len(records),
        "starts": sum(r["role"] == "start" for r in records),
        "goals": sum(r["role"] == "goal" for r in records),
        "probes": len(probes),
        "horizontal_overstep": sum(s["horizontal_m"] > 0.2501 for s in probes),
        "max_displacement_m": max((s["distance_m"] for s in probes), default=0),
    }
    atomic_json(
        owned(a.output),
        {
            "claim_scope": "offline_pathfinder_only_not_environment_motion",
            "source_audit_sha256": digest(a.audit),
            "summary": summary,
            "endpoints": records,
        },
    )
    print(summary)


if __name__ == "__main__":
    main()
