"""CPU PathFinder audit of exact start/goal and dense GT positions. No navigation policy."""

import argparse, json, math, os
from pathlib import Path
from workspace import ROOT, read_json, atomic_json, digest
from preflight import dataset_base, SPECS, load, task_key


def distance(pf, start, goals):
    import habitat_sim

    values = []
    for goal in goals:
        query = habitat_sim.ShortestPath()
        query.requested_start = start
        query.requested_end = goal
        if pf.find_path(query) and math.isfinite(query.geodesic_distance):
            values.append(float(query.geodesic_distance))
    return min(values) if values else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--profile")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    if not os.environ.get("CASE1_PROTECTION"):
        raise SystemExit("Use protected runtime")
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    import habitat_sim

    profile = read_json(a.profile) if a.profile else None
    if profile and (
        profile["agent"] != {"height": 1.5, "radius": 0.1}
        or profile["simulator_version"] != habitat_sim.__version__
    ):
        raise ValueError("Profile identity mismatch")
    finders = {}
    assets = {}
    components = {}
    rows = []
    for ds, (directory, anno, gt_name, count) in SPECS.items():
        base = dataset_base(ds)
        episodes = load(base / anno)["episodes"]
        gt = load(base / gt_name)
        if ds == "rxr":
            episodes = [e for e in episodes if e["instruction"]["language"] == "en-US"]
        if len(episodes) != count:
            raise ValueError("Unexpected full split")
        for e in episodes:
            scene = e["scene_id"]
            glb = ROOT / "data/scene_datasets" / scene
            if scene not in finders:
                mesh = glb.with_suffix(".navmesh")
                if profile:
                    asset = profile["assets"][scene]
                    mesh = Path(asset["navmesh_path"])
                    if (
                        digest(glb) != asset["scene_sha256"]
                        or digest(mesh) != asset["navmesh_sha256"]
                    ):
                        raise ValueError("Asset drift")
                pf = habitat_sim.PathFinder()
                if not pf.load_nav_mesh(str(mesh)):
                    raise RuntimeError("Cannot load navmesh " + str(mesh))
                finders[scene] = pf
                components[scene] = []
                assets[scene] = {
                    "scene_sha256": digest(glb),
                    "navmesh_path": str(mesh),
                    "navmesh_sha256": digest(mesh),
                }
            pf = finders[scene]
            goals = [g["position"] for g in e["goals"]]
            def component(point):
                # Classify observed endpoints by the actual pathfinder; these are
                # sampled reachable components, not a count of every mesh island.
                for index, representative in enumerate(components[scene]):
                    if distance(pf, point, [representative]) is not None:
                        return index
                if distance(pf, point, [point]) is None:
                    return None
                components[scene].append(list(point))
                return len(components[scene])-1

            refs = gt[str(e["episode_id"])]["locations"]
            bad = []
            off = []
            for i, pos in enumerate(refs):
                if distance(pf, pos, goals) is None:
                    bad.append(i)
                if not pf.is_navigable(pos):
                    snap = list(pf.snap_point(pos))
                    delta = [float(snap[k] - pos[k]) for k in range(3)]
                    off.append(
                        {
                            "index": i,
                            "snap_delta_m": [v if math.isfinite(v) else None for v in delta],
                        }
                    )
            rows.append(
                {
                    "task_key": task_key(ds, e),
                    "dataset": ds,
                    "scene_id": scene,
                    "episode_id": str(e["episode_id"]),
                    "instruction_id": e.get("instruction", {}).get("instruction_id"),
                    "start_position": list(e["start_position"]),
                    "goal_positions": goals,
                    "start_observed_component": component(e["start_position"]),
                    "goal_observed_components": [component(g) for g in goals],
                    "start_island_radius": float(pf.island_radius(e["start_position"])),
                    "start_goal_distance": distance(pf, e["start_position"], goals),
                    "start_navigable": bool(pf.is_navigable(e["start_position"])),
                    "goals_navigable": [bool(pf.is_navigable(g)) for g in goals],
                    "reference_count": len(refs),
                    "reference_nonfinite_indices": bad,
                    "reference_offmesh": off,
                }
            )
    nonfinite = [
        r["task_key"]
        for r in rows
        if r["start_goal_distance"] is None or r["reference_nonfinite_indices"]
    ]
    result = {
        "schema_version": 1,
        "claim_scope": "offline_navmesh_connectivity",
        "simulator_version": habitat_sim.__version__,
        "simulator_module": habitat_sim.__file__,
        "profile_sha256": digest(a.profile) if a.profile else None,
        "assets": assets,
        "observed_endpoint_component_representatives": components,
        "tasks": rows,
        "nonfinite_tasks": nonfinite,
        "all_distances_finite": not nonfinite,
        "tasks_with_offmesh_reference": sum(bool(r["reference_offmesh"]) for r in rows),
        "note": "Static connectivity is not model navigation or physical motion validation.",
    }
    atomic_json(a.output, result)
    print(
        json.dumps(
            {
                "tasks": len(rows),
                "nonfinite_tasks": len(nonfinite),
                "offmesh_reference_tasks": result["tasks_with_offmesh_reference"],
            }
        )
    )


if __name__ == "__main__":
    main()
