"""Only measured artifacts can open the formal full-evaluation gate."""

import argparse, math
from pathlib import Path
from workspace import ROOT, read_json, atomic_json, digest, owned
from evaluate import source_identity
from result_contract import aggregate, rows, finite_metrics


def main():
    p = argparse.ArgumentParser()
    for name in (
        "clean-receipt",
        "original-audit",
        "accepted-audit",
        "motion-audit",
        "motion-replay",
        "profile",
        "cpu-receipt",
        "protection-receipt",
        "order-receipt",
        "r2r-run",
        "rxr-run",
    ):
        p.add_argument("--" + name, required=True)
    a = p.parse_args()
    sha, _ = source_identity()
    clean=read_json(a.clean_receipt)
    if clean.get('status')!='PASS' or clean.get('main_source_sha256')!=sha:
        raise ValueError('Final source clean-environment validation required')
    for item in clean['evidence']:
        if digest(item['path'])!=item['sha256']:raise ValueError('Clean verification evidence drift')
    profile = read_json(a.profile)
    profile_sha = digest(a.profile)
    if profile["agent"] != {"height": 1.5, "radius": 0.1}:
        raise ValueError("Changed body")
    original = read_json(a.original_audit)
    accepted = read_json(a.accepted_audit)
    bad = {
        r["episode_id"]
        for r in original["tasks"]
        if r["dataset"] == "rxr" and r["start_goal_distance"] is None
    }
    if len(bad) != 33:
        raise ValueError("Original33 not reproduced")
    if (
        len(accepted["tasks"]) != 3062
        or not accepted["all_distances_finite"]
        or accepted["nonfinite_tasks"]
    ):
        raise ValueError("Full static connectivity not accepted")
    if accepted["profile_sha256"] != profile_sha:
        raise ValueError("Wrong audited profile")
    if any(not r["start_navigable"] or not all(r["goals_navigable"]) for r in accepted["tasks"]):
        raise ValueError("Invalid start/goal on candidate mesh; do not silently move annotations")
    if {r["task_key"] for r in original["tasks"]} != {r["task_key"] for r in accepted["tasks"]}:
        raise ValueError("Static cohort changed")
    for scene, asset in accepted["assets"].items():
        if original["assets"][scene]["scene_sha256"] != asset["scene_sha256"]:
            raise ValueError("GLB changed")
        if (
            profile["assets"][scene]["original_navmesh_sha256"]
            != original["assets"][scene]["navmesh_sha256"]
        ):
            raise ValueError("Shared original navmesh changed")
    required_motion=bad | {r["episode_id"] for r in original["tasks"] if r["dataset"]=="rxr" and not r["start_navigable"]}
    protocol=read_json(ROOT/'configs/annotation-protocol.json')
    required_motion |= set(protocol['start_episode_ids']) | set(protocol['goal_episode_ids'])
    motion = read_json(a.motion_audit)
    replay=read_json(a.motion_replay)
    if replay['status']!='PASS' or replay['method']!='native_action_replay_same_profile_v1' or replay['profile_sha256']!=profile_sha or replay['motion_audit_sha256']!=digest(a.motion_audit):
        raise ValueError('Independent same-profile native replay not accepted')
    replay_tasks={r['episode_id']:r for r in replay['tasks']}
    if set(replay_tasks)!=required_motion:raise ValueError('Incomplete native replay coverage')
    if (
        motion["status"] != "EXECUTION_COMPLETE_PENDING_REPLAY"
        or motion["profile_sha256"] != profile_sha
        or {r["episode_id"] for r in motion["tasks"]} != required_motion
    ):
        raise ValueError("Original33 real motion not accepted")
    for r in motion["tasks"]:
        trace = Path(a.motion_audit).parent / r["episode_id"] / "motion.json"
        if not r["success"] or not r["all_distances_finite"] or r["reset_position_error_m"]>1e-4 or not replay_tasks[r["episode_id"]]["matches"] or not replay_tasks[r["episode_id"]]["no_cross_floor_jump"] or digest(trace) != r["motion_sha256"]:
            raise ValueError("Motion evidence mismatch")
    cpu = read_json(a.cpu_receipt)
    if (
        cpu["status"] != "PASS"
        or cpu["source_sha256"] != sha
        or cpu["skips"]
        or cpu["errors"]
        or cpu["failures"]
    ):
        raise ValueError("Fresh zero-skip CPU pass required")
    order = read_json(a.order_receipt)
    protection = read_json(a.protection_receipt)
    if (
        protection.get("status") != "PASS"
        or protection.get("method") != "kernel_protection_modes_v1"
        or protection.get("source_sha256") != sha
    ):
        raise ValueError("Fresh real launcher protection receipt required")
    if {r["mode"] for r in protection["modes"]} != {"runtime", "results", "configs"}:
        raise ValueError("Incomplete runtime permission-mode checks")
    if any(
        r.get("global_writes_attempted") or not r.get("global_reads_passed")
        for r in protection["modes"]
    ):
        raise ValueError("Invalid shared-asset protection check")
    if not cpu.get("test_files"):
        raise ValueError("CPU receipt lacks test-source identity")
    for test in cpu["test_files"]:
        if digest(test["path"]) != test["sha256"]:
            raise ValueError("CPU test source changed after validation")
    if (
        order["status"] != "PASS"
        or order["source_sha256"] != sha
        or order["navmesh_sha256"] != profile_sha
    ):
        raise ValueError("Real order-independence not accepted")
    for r in order["run_manifests"]:
        if digest(r["path"]) != r["sha256"]:
            raise ValueError("Order evidence changed")
    paths = [
        a.clean_receipt,
        a.original_audit,
        a.accepted_audit,
        a.motion_audit,
        a.motion_replay,
        a.profile,
        a.cpu_receipt,
        a.protection_receipt,
        a.order_receipt,
    ]
    for ds, path, minimum in [("r2r", a.r2r_run, 2), ("rxr", a.rxr_run, 35)]:
        run = owned(path)
        manifest = read_json(run / "run_manifest.json")
        results = rows(run / "results.jsonl")
        summary = aggregate(manifest, results)
        if (
            manifest["source_sha256"] != sha
            or manifest["navmesh_sha256"] != profile_sha
            or manifest["scope"] != "diagnostic"
        ):
            raise ValueError("Pilot identity mismatch")
        if not summary["complete"] or len(results) != minimum:
            raise ValueError("Pilot coverage mismatch")
        semantic = read_json(run / "semantic_audit.json")
        independent = read_json(run / "independent_metrics.json")
        if (
            semantic["status"] != "PASS"
            or semantic["errors"]
            or semantic["manifest_sha256"] != digest(run / "run_manifest.json")
        ):
            raise ValueError("Pilot semantics not accepted")
        expected = {r["task_key"]: r for r in independent["results"]}
        if independent["manifest_sha256"] != digest(run / "run_manifest.json") or set(expected) != {
            r["task_key"] for r in results
        }:
            raise ValueError("Pilot recompute identity mismatch")
        for row in results:
            finite_metrics(row)
            finite_metrics(expected[row["task_key"]])
            for name, value in row["metrics"].items():
                if not math.isclose(
                    value, expected[row["task_key"]]["metrics"][name], rel_tol=1e-6, abs_tol=1e-5
                ):
                    raise ValueError("Pilot metric mismatch")
            receipt = (run / row["trace_path"]).parents[2] / "model-receipt.json"
            loaded = read_json(receipt)
            if loaded["source_sha256"] != sha or not loaded["device"].startswith("cuda"):
                raise ValueError("Wrong loaded model identity")
            paths.append(str(receipt))
        if ds == "rxr" and not bad <= {key.split("|")[-2] for key in expected}:
            raise ValueError("Pilot omitted original33")
        paths.extend(
            str(run / n)
            for n in (
                "run_manifest.json",
                "results.jsonl",
                "semantic_audit.json",
                "independent_metrics.json",
            )
        )
    receipts = [{"path": str(Path(x).resolve()), "sha256": digest(x)} for x in sorted(set(paths))]
    atomic_json(
        ROOT / "outputs/gates/engineering.json",
        {
            "status": "PASS",
            "source_sha256": sha,
            "navmesh_sha256": profile_sha,
            "receipts": receipts,
            "scope": "Full evaluation may now start; no formal performance result yet.",
        },
    )
    print("Engineering gates passed; full evaluation remains a separate run")


if __name__ == "__main__":
    main()
