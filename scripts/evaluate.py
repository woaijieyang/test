"""Frozen, fixed logical shards, idle-GPU dispatch, immutable attempts and exact merge."""

import argparse, hashlib, json, math, os, subprocess, time, datetime
from pathlib import Path
from workspace import ROOT, owned, atomic_json, digest, read_json
from preflight import SPECS, load, task_key
from result_contract import rows, aggregate


def source_identity():
    files = []
    for name in ("src", "scripts", "configs"):
        for p in sorted((ROOT / name).rglob("*")):
            if (
                p.is_file()
                and "__pycache__" not in p.parts
                and "local" not in p.relative_to(ROOT).parts
                and not any(part.endswith(".egg-info") for part in p.parts)
            ):
                files.append({"path": str(p), "sha256": digest(p)})
    sha = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return sha, files


def free_gpus():
    policy_path=ROOT/'configs/local/resource-policy.json'
    if policy_path.exists():
        policy=read_json(policy_path)
        if policy.get('mode')!='shared_capacity' or policy.get('gpu_ids')!=[7]:
            raise RuntimeError('Unknown shared resource policy')
        rows=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.total,memory.used','--format=csv,noheader,nounits'],text=True)
        for line in rows.splitlines():
            index,total,used=[int(x.strip()) for x in line.split(',')]
            if index==7 and total-used>=policy['minimum_free_mib']:
                return [7]
        return []
    text = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    )
    active = subprocess.check_output(
        ["nvidia-smi", "--query-compute-apps=gpu_uuid", "--format=csv,noheader"], text=True
    )
    result = []
    for line in text.splitlines():
        index, uuid, memory, util = [s.strip() for s in line.split(",")]
        if uuid not in active and int(memory) < 1024 and int(util) < 10:
            result.append(int(index))
    return result[:8]


def scene_view(profile):
    root = owned(
        ROOT
        / "data/derived/evaluation-scenes"
        / hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()[:16]
    )
    root.mkdir(parents=True, exist_ok=True)
    for scene, asset in profile["assets"].items():
        if (
            digest(asset["scene_path"]) != asset["scene_sha256"]
            or digest(asset["navmesh_path"]) != asset["navmesh_sha256"]
        ):
            raise ValueError("Scene/profile asset changed")
        path = root / scene
        path.parent.mkdir(parents=True, exist_ok=True)
        for dst, src in [
            (path, Path(asset["scene_path"]).resolve()),
            (path.with_suffix(".navmesh"), Path(asset["navmesh_path"]).resolve()),
        ]:
            if dst.is_symlink():
                if dst.resolve() != src:
                    raise ValueError("Scene view link collision")
            elif dst.exists():
                raise ValueError("Scene view entity collision")
            else:
                dst.symlink_to(src)
    return root


def merge(run):
    merged = []
    seen = set()
    for file in sorted((run / "shards").glob("shard-*/attempt-*/episodes/*/result.json")):
        row = read_json(file)
        if row["task_key"] in seen:
            raise ValueError("Duplicate completed task across attempts")
        seen.add(row["task_key"])
        row["trace_path"] = str(file.parents[2].relative_to(run) / row["trace_path"])
        row["effective_config_path"] = str(
            file.parents[2].relative_to(run) / row["effective_config_path"]
        )
        merged.append(row)
    # Each worker file remains immutable; only this derived union is regenerated.

    target = run / "results.jsonl"
    tmp = run / "results.jsonl.new"
    tmp.write_text("".join(json.dumps(r, allow_nan=False) + "\n" for r in merged))
    tmp.replace(target)
    configs = {r["effective_config_path"]: r["effective_config_sha256"] for r in merged}
    atomic_json(
        run / "effective-configs.json",
        {"files": [{"path": path, "sha256": sha} for path, sha in sorted(configs.items())]},
    )
    return merged


def recover_closed_traces(run):
    for trace in (run / "shards").glob("shard-*/attempt-*/episodes/*/trace.jsonl"):
        result = trace.parent / "result.json"
        if result.exists():
            continue
        try:
            events = rows(trace)
        except (ValueError, OSError):
            continue  # Preserve interrupted partial traces; no result is manufactured.
        if not events or events[0]["kind"] != "reset" or events[-1]["kind"] != "terminal":
            continue
        from audit_model_trace import inspect

        if inspect(events)[0]:
            raise ValueError("Closed uncommitted trace failed action audit; diagnose without retry")
        terminal = events[-1]
        key = events[0]["task_key"]
        info = terminal["native_metrics"]
        result_row = {
            "task_key": key,
            "dataset": key.split("|")[0],
            "status": "completed",
            "episode_sequence": events[0]["episode_sequence"],
            "metrics": {
                dst: float(info[src])
                for src, dst in [
                    ("success", "sr"),
                    ("spl", "spl"),
                    ("ndtw", "ndtw"),
                    ("distance_to_goal", "ne"),
                    ("oracle_success", "oracle_sr"),
                ]
            },
            "trace_path": str(trace.relative_to(trace.parents[2])),
            "effective_config_path": "effective-config.yaml",
            "effective_config_sha256": digest(trace.parents[2] / "effective-config.yaml"),
            "trace_sha256": digest(trace),
            "termination_reason": terminal["termination_reason"],
            "primitive_steps": terminal["steps"],
            "model_calls": terminal["model_calls"],
            "stop_source": terminal.get("stop_source"),
            "recovered_from_closed_trace": True,
        }
        atomic_json(result, result_row)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", choices=["r2r", "rxr"], required=True)
    p.add_argument("--method", choices=["baseline", "hamlet", "hamlet-trained"], default="baseline")
    p.add_argument(
        "--gpu-ids",
        help="Optional fixed physical GPU allowlist, e.g. 7 for same-device diagnostics",
    )
    p.add_argument("--trained-bundle", help="Workspace-local immutable learned-memory bundle")
    p.add_argument("--run-id", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--scope", choices=["diagnostic", "full"], required=True)
    p.add_argument("--episode-ids")
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    if not os.environ.get("CASE1_PROTECTION"):
        raise SystemExit("Use scripts/with_runtime.sh")
    protection = json.loads(os.environ["CASE1_PROTECTION"])
    if protection.get("results_write") or protection.get("prepare_configs"):
        raise SystemExit("Administrative write permissions cannot be used for navigation")
    permitted_gpus = [int(x) for x in a.gpu_ids.split(",")] if a.gpu_ids else list(range(8))
    if (
        not permitted_gpus
        or len(set(permitted_gpus)) != len(permitted_gpus)
        or not set(permitted_gpus) <= set(range(8))
    ):
        raise ValueError("GPU allowlist must contain unique physical IDs from 0 to 7")
    if any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for c in a.run_id
    ):
        raise ValueError("Unsafe run ID")
    if a.scope == "diagnostic" and not a.episode_ids:
        raise ValueError("Explicit diagnostic identities required")
    if a.scope == "full" and a.episode_ids:
        raise ValueError("Full cannot filter identities")
    source_sha, sources = source_identity()
    candidate_policy = None
    if a.method == "hamlet":
        from hamlet_v2.policy import policy_identity
        candidate_policy = policy_identity(ROOT)
    if a.method == "hamlet-trained":
        if not a.trained_bundle:
            raise ValueError("--trained-bundle is required")
        from hamlet_v2.trained_runtime import bundle_identity
        candidate_policy = bundle_identity(ROOT, a.trained_bundle)
    elif a.trained_bundle:
        raise ValueError("--trained-bundle is only valid with hamlet-trained")
    profile_path = Path(a.profile).resolve()
    profile = read_json(profile_path)
    if profile["agent"] != {"height": 1.5, "radius": 0.1}:
        raise ValueError("Robot dimensions changed")
    if a.scope == "full":
        gate = read_json(ROOT / "outputs/gates/engineering.json")
        if (
            gate.get("status") != "PASS"
            or gate["source_sha256"] != source_sha
            or gate["navmesh_sha256"] != digest(profile_path)
        ):
            raise ValueError("Fresh engineering gate required")
        for receipt in gate["receipts"]:
            if digest(receipt["path"]) != receipt["sha256"]:
                raise ValueError("Engineering evidence changed")
    model = read_json(ROOT / "outputs/preflight/model.json")
    environment = read_json(ROOT / "outputs/setup/runtime-files.json")
    for f in environment["files"]:
        if digest(f["path"]) != f["sha256"]:
            raise ValueError("Independent environment changed")
    for f in model["files"]:
        if digest(f["path"]) != f["sha256"]:
            raise ValueError("Model changed")
    data = read_json(ROOT / "outputs/preflight/data.json")["datasets"][a.dataset]
    if (
        digest(data["annotation"]) != data["annotation_sha256"]
        or digest(data["gt"]) != data["gt_sha256"]
    ):
        raise ValueError("Dataset changed")
    for extra in data.get("auxiliary_inputs", []):
        if digest(extra["path"]) != extra["sha256"]:
            raise ValueError("Auxiliary GT changed")
    selected = set(str(x) for x in read_json(a.episode_ids)) if a.episode_ids else None
    episodes = load(data["annotation"])["episodes"]
    chunk_size = math.ceil(len(episodes) / 8)
    jobs = []
    expected = []
    for chunk in range(8):
        subset = episodes[chunk * chunk_size : (chunk + 1) * chunk_size]
        subset = [
            e
            for e in subset
            if (a.dataset != "rxr" or e["instruction"]["language"] == "en-US")
            and (selected is None or str(e["episode_id"]) in selected)
        ]
        if subset:
            jobs.append({"chunk": chunk, "ids": [str(e["episode_id"]) for e in subset]})
        expected.extend({"task_key": task_key(a.dataset, e), "dataset": a.dataset} for e in subset)
    if selected and len(expected) != len(selected):
        raise ValueError("Diagnostic selection missing or ambiguous")
    if a.scope == "full" and len(expected) != SPECS[a.dataset][3]:
        raise ValueError("Wrong full cohort")
    run = owned(ROOT / "outputs" / a.run_id)
    if a.resume:
        if not run.is_dir():
            raise ValueError("Cannot resume an absent run")
    else:
        run.mkdir(parents=True, exist_ok=False)
    import fcntl

    lease = (run / ".controller.lock").open("a")
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for record in (run / "shards").glob("shard-*/process-*.json"):
        identity = read_json(record)
        stat = Path("/proc") / str(identity["pid"]) / "stat"
        if (
            stat.exists()
            and stat.read_text().rsplit(")", 1)[1].split()[19] == identity["start_ticks"]
        ):
            raise RuntimeError("Existing owned worker is live; wait before resume")
    if a.resume:
        manifest = read_json(run / "run_manifest.json")
        if manifest.get("method", "baseline") != a.method or manifest.get("policy_identity") != candidate_policy:
            raise ValueError("Resume candidate policy changed")
        if not set(permitted_gpus) <= set(manifest["allowed_gpu_ids"]):
            raise ValueError("Resume would expand the frozen GPU allowlist")
        if (
            manifest["source_sha256"] != source_sha
            or manifest["navmesh_sha256"] != digest(profile_path)
            or manifest["expected_tasks"] != expected
        ):
            raise ValueError("Cannot resume changed identity")
    else:
        manifest = {
            "schema_version": 1,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "record_id": a.run_id,
            "run_id": a.run_id,
            "claim_scope": "online_navigation" if a.scope == "full" else "diagnostic_navigation",
            "scope": a.scope,
            "split": "val_unseen",
            "language": "en-US" if a.dataset == "rxr" else "en",
            "method": a.method,
            "policy_identity": candidate_policy,
            "model": ("HAMLET trained Recent-4" if a.method == "hamlet-trained" else "HAMLET-Z V2 / CBEM aw4 seed10") if candidate_policy else model["model"],
            "base_model_sha256": model["model_sha256"],
            "model_sha256": hashlib.sha256((model["model_sha256"] + candidate_policy["sha256"]).encode()).hexdigest() if candidate_policy else model["model_sha256"],
            "source_sha256": source_sha,
            "config_sha256": digest(
                ROOT / "configs/vlnce_baselines/config" / f"{a.dataset}_baselines/awarevln.yaml"
            ),
            "navmesh_profile": str(profile_path),
            "navmesh_sha256": digest(profile_path),
            "benchmark_sha256": hashlib.sha256(
                json.dumps(expected, sort_keys=True).encode()
            ).hexdigest(),
            "expected_tasks": expected,
            "datasets": {a.dataset: data},
            "frozen_files": sources
            + model["files"]
            + [
                {"path": data["annotation"], "sha256": data["annotation_sha256"]},
                {"path": data["gt"], "sha256": data["gt_sha256"]},
                {"path": str(profile_path), "sha256": digest(profile_path)},
            ],
            "logical_chunks": 8,
            "max_gpus": 8,
            "allowed_gpu_ids": permitted_gpus,
            "max_logical_cpus": 64,
        }
        if candidate_policy:
            manifest["frozen_files"].extend(candidate_policy["files"])
        manifest["frozen_files"].extend(data.get("auxiliary_inputs", []))
        protocol_path=ROOT/'configs/annotation-protocol.json'
        if protocol_path.exists():
            protocol=read_json(protocol_path)
            derivative=ROOT/protocol['dataset_roots']['rxr']/'manifest.json'
            ledger=read_json(derivative)
            manifest['annotation_protocol']=protocol
            manifest['annotation_derivative_sha256']=digest(derivative)
            manifest['frozen_files'].append({'path':str(derivative),'sha256':digest(derivative)})
            manifest['frozen_files'].extend(ledger['source_files'])
        manifest["environment_sha256"] = environment["environment_sha256"]
        manifest["frozen_files"].extend(environment["files"])
        for asset in profile["assets"].values():
            manifest["frozen_files"].extend(
                [
                    {
                        "path": str(Path(asset["scene_path"]).resolve()),
                        "sha256": asset["scene_sha256"],
                    },
                    {
                        "path": str(Path(asset["navmesh_path"]).resolve()),
                        "sha256": asset["navmesh_sha256"],
                    },
                    {
                        "path": str(Path(asset["scene_path"]).with_suffix(".navmesh").resolve()),
                        "sha256": asset["original_navmesh_sha256"],
                    },
                ]
            )
        policy=ROOT/'configs/local/resource-policy.json'
        if policy.exists():
            manifest['resource_policy']=read_json(policy)
            manifest['frozen_files'].append({'path':str(policy),'sha256':digest(policy)})
        atomic_json(run / "run_manifest.json", manifest)
    scenes = scene_view(profile)
    (run / "shards").mkdir(exist_ok=True)
    if a.resume:
        recover_closed_traces(run)
    completed = {r["task_key"] for r in merge(run)}
    if not completed <= {r["task_key"] for r in expected}:
        raise ValueError("Unexpected committed task identity; do not dispatch more work")
    pending = []
    for job in jobs:
        ids = [x for x in job["ids"] if not any(k.split("|")[-2] == x for k in completed)]
        if ids:
            pending.append({**job, "ids": ids})
    allowed = sorted(os.sched_getaffinity(0))[:64]
    os.sched_setaffinity(0, allowed)
    active = {}
    failed = []
    while pending or active:
        idle = [g for g in free_gpus() if g not in active and g in permitted_gpus]
        for gpu in idle if not failed else []:
            if not pending:
                break
            job = pending.pop(0)
            base = run / "shards" / ("shard-" + str(job["chunk"]).zfill(2))
            base.mkdir(exist_ok=True)
            number = len(list(base.glob("attempt-*"))) + 1
            out = base / ("attempt-" + str(number).zfill(2))
            ids = base / ("ids-" + str(number) + ".json")
            atomic_json(ids, job["ids"])
            log = (base / ("attempt-" + str(number).zfill(2) + ".log")).open("x")
            env = dict(
                os.environ,
                CUDA_VISIBLE_DEVICES=str(gpu),
                CASE1_RUN_ROOT=str(run),
                CASE1_SOURCE_SHA256=source_sha,
                OMP_NUM_THREADS="1",
                MKL_NUM_THREADS="1",
            )
            command = [
                str(ROOT / "runtime/awarevln/bin/python"),
                "-B",
                str(ROOT / "scripts/evaluate_worker.py"),
                "--dataset",
                a.dataset,
                "--output",
                str(out),
                "--scenes",
                str(scenes),
                "--chunk",
                str(job["chunk"]),
                "--chunks",
                "8",
                "--ids",
                str(ids),
            ]
            proc = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
            active[gpu] = (proc, log, job)
            atomic_json(
                base / ("process-" + str(number) + ".json"),
                {
                    "pid": proc.pid,
                    "launch_observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "cpu_affinity": sorted(os.sched_getaffinity(proc.pid)),
                    "gpu": gpu,
                    "command": command,
                    "start_ticks": Path("/proc/" + str(proc.pid) + "/stat")
                    .read_text()
                    .rsplit(")", 1)[1]
                    .split()[19],
                },
            )
        for gpu, (proc, log, job) in list(active.items()):
            if proc.poll() is None:
                continue
            log.close()
            if proc.returncode != 0:
                failed.append({"chunk": job["chunk"], "returncode": proc.returncode})
            del active[gpu]
        merged = merge(run)
        atomic_json(
            run / "progress.json",
            {
                "completed": len(merged),
                "expected": len(expected),
                "active": len(active),
                "pending": len(pending),
                "failed": failed,
            },
        )
        if failed and not active:
            break
        if active or pending:
            time.sleep(30)
    merged = merge(run)
    atomic_json(run / "summary.json", aggregate(manifest, merged))
    if failed or len(merged) != len(expected):
        raise SystemExit("Incomplete run; preserve attempts and diagnose before resume")
    print(
        json.dumps({"status": "EXECUTION_COMPLETE_PENDING_INDEPENDENT_AUDIT", "tasks": len(merged)})
    )


if __name__ == "__main__":
    main()
