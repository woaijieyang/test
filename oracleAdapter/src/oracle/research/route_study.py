"""Predeclared mapping-fixed state-key comparison and independent route audit."""
import concurrent.futures
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from oracle.common.artifacts import content_digest, digest, freeze_sources, owned_output, package_sources, require_sources, timestamp, write_json
from oracle.verification.binding import bind_callable


def prepare(case_root, output):
    root = Path(case_root).resolve()
    output = owned_output(root, output)
    output.mkdir(parents=True, exist_ok=False)
    package, sources = package_sources()
    config = json.loads((package / "configs/experiments/route_development_v1.json").read_text())
    protocol = json.loads((package / config["protocol_config"]).read_text())
    catalog = root / "outputs/landmark-connectivity/native-source-catalog-v1/catalog.json"
    catalog_sha = digest(catalog)
    old = root / "outputs/connectivity/endpoint115-full-motion-v3"
    old_manifest = json.loads((old / "manifest.json").read_text())
    old_validation = json.loads((old / "validation.json").read_text())
    if old_validation["manifest_sha256"] != digest(old / "manifest.json") or not old_validation["coverage_complete"]:
        raise RuntimeError("Historical endpoint coverage/identity unavailable")
    rows = old_validation["results"]
    selected = []
    for dataset in ("r2r", "rxr"):
        candidates = sorted([r for r in rows if r["task_key"].split("|")[0] == dataset and r["status"] == "PASS_STRICT_MOTION_REPLAY"],
                            key=lambda r: int(r["task_key"].split("|")[-2]))
        seen, taken = set(), 0
        for row in candidates:
            task_path = old / "inputs" / (hashlib.sha256(row["task_key"].encode()).hexdigest()[:24] + ".json")
            task = json.loads(task_path.read_text())
            identity = content_digest([task["scene"], task["targets"], task["start_rotation"]])
            if identity in seen:
                continue
            seen.add(identity)
            selected.append((row, task_path, task, "historical_strict_success_control"))
            taken += 1
            if taken == config["selection"]["endpoint_success_controls_per_dataset"]:
                break
        if taken != config["selection"]["endpoint_success_controls_per_dataset"]:
            raise RuntimeError("Insufficient distinct route controls")
    for dataset, episode in config["selection"]["endpoint_failures"]:
        found = [r for r in rows if r["task_key"].split("|")[0] == dataset and r["task_key"].split("|")[-2] == episode]
        if len(found) != 1 or found[0]["status"] != "FAILURE_PRESERVED":
            raise RuntimeError("Predeclared historical failure identity differs")
        row = found[0]
        path = old / "inputs" / (hashlib.sha256(row["task_key"].encode()).hexdigest()[:24] + ".json")
        selected.append((row, path, json.loads(path.read_text()), "historical_failure"))
    tasks = []
    for row, path, task, role in selected:
        if digest(row["result_path"]) != row["result_sha256"] or digest(row["audit_path"]) != row["audit_sha256"]:
            raise RuntimeError("Historical endpoint evidence changed")
        tasks.append({**task, "cohort": "endpoint115_ordered_reference", "purpose": "reference_execution",
                      "objective": "visit_reference_in_order", "privileges": ["true_pose", "navigation_mesh", "goal", "reference_path", "source_geometry"],
                      "profile_path": old_manifest["profile_path"], "profile_sha256": old_manifest["profile_sha256"],
                      "selection_role": role, "historical_status": row["status"], "historical_error": row.get("error"),
                      "source_task_path": str(path), "source_task_sha256": digest(path)})
    lm = root / "outputs/landmark-connectivity"
    parent_path = lm / "full-native-v11/manifest.json"
    parent = json.loads(parent_path.read_text())
    lookup = {t["task_key"]: t for t in parent["tasks"]}
    alias = json.loads((lm / "source-guard-key-alias-v1/validation.json").read_text())
    prefixes = {r["task_key"]: r for r in alias["records"]}
    proof_path = lm / "mJX-exact-continuous-proof-index-v1.json"
    proof = json.loads(proof_path.read_text())
    control_key = config["selection"]["landmark_source_clear_control"]
    control = next(r for r in proof["records"] if r["task_key"] == control_key)
    if control["status"] != "LINEAR_CONTINUOUS_SOURCE_CLEAR_DIAGNOSTIC" or digest(root / control["evidence_path"]) != control["evidence_sha256"]:
        raise RuntimeError("Declared Landmark source-clear control changed")
    for key in config["selection"]["landmark_alias_tasks"] + [control_key]:
        task = lookup[key]
        if key in prefixes:
            reference = prefixes[key]
            path = Path(reference["prefix_path"])
            if digest(path) != reference["prefix_sha256"]:
                raise RuntimeError("Archived alias prefix changed")
            record = json.loads(path.read_text())
            if record["targets"] != task["targets"]:
                raise RuntimeError("Mapping difference cannot be called an Oracle change")
            rotation = record["rotation"]
        else:
            task_hash = hashlib.sha256(key.encode()).hexdigest()
            path = lm / "full-native-v11" / f"shard-{int(task_hash, 16) % 8:02}" / (task_hash[:24] + ".result.json")
            native = json.loads(path.read_text())
            trace_path = lm / "full-native-v11" / native["trace_path"]
            if digest(trace_path) != native["trace_sha256"]:
                raise RuntimeError("Historical native trace changed")
            with gzip.open(trace_path, "rt") as stream:
                trace = json.load(stream)
            if trace["targets"] != task["targets"]:
                raise RuntimeError("Control target identity mismatch")
            rotation = trace["rotation"]
        tasks.append({"task_key": key, "cohort": "landmark_historical_v11_mapping", "scene": task["scene"],
                      "targets": task["targets"], "start_rotation": rotation,
                      "source_record_sha256": task["source_record_sha256"],
                      "purpose": "landmark_order_execution", "objective": "visit_landmark_occurrences_in_order",
                      "privileges": ["true_pose", "navigation_mesh", "goal", "reference_path", "source_geometry", "landmark_annotations"],
                      "profile_path": parent["profile_path"], "profile_sha256": parent["profile_sha256"],
                      "selection_role": "historical_exact_success_control" if key == control_key else "archived_state_alias_failure",
                      "source_task_path": str(path), "source_task_sha256": digest(path),
                      "historical_parent_manifest_sha256": digest(parent_path)})
    if len(tasks) != config["expected_tasks"] or len({t["task_key"] for t in tasks}) != len(tasks):
        raise RuntimeError("Development cohort mismatch")
    methods = [{**config["common_method"], **arm} for arm in config["methods"]]
    inputs = []
    for task in tasks:
        task["geometry_catalog_sha256"] = catalog_sha
        task["module_source_sha256"] = content_digest(sources)
        path = output / "inputs" / (hashlib.sha256(task["task_key"].encode()).hexdigest()[:24] + ".json")
        write_json(path, task)
        inputs.append({"task_key": task["task_key"], "path": str(path), "sha256": digest(path),
                       "cohort": task["cohort"], "selection_role": task["selection_role"]})
    manifest = {"status": "FROZEN_BEFORE_NEW_ROUTE_RESULTS", "created_at": timestamp(), "config": config,
                "protocol": protocol, "methods": methods, "tasks": inputs, "sources": sources,
                "expected_tasks": len(tasks), "expected_executions": len(tasks) * len(methods),
                "historical_endpoint_validation_sha256": digest(old / "validation.json"),
                "historical_landmark_proof_sha256": digest(proof_path),
                "launchers": {str(root / "oracleAdapter/run.py"): digest(root / "oracleAdapter/run.py"),
                              str(root / "scripts/with_runtime.sh"): digest(root / "scripts/with_runtime.sh")},
                "experimental_factor": "state-key strategy only; mapping and common controller held fixed",
                "scope": "Known development tasks; no blind generalization or model-score claim"}
    write_json(output / "manifest.json", manifest)
    freeze_sources(output, sources)
    write_json(output / "state.json", {"status": "PREPARED", "tasks": len(tasks), "executions": manifest["expected_executions"]})
    return manifest


def worker(case_root, manifest_path, task_path, method_id, output, audit_input=None):
    root = Path(case_root).resolve()
    manifest_path, task_path = Path(manifest_path).resolve(), Path(task_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    if any(digest(path) != value for path, value in manifest["launchers"].items()):
        raise RuntimeError("Actual launcher changed after freeze")
    package = require_sources(manifest["sources"])
    entry = next(t for t in manifest["tasks"] if Path(t["path"]).resolve() == task_path)
    if digest(task_path) != entry["sha256"]:
        raise RuntimeError("Frozen task file changed")
    task = json.loads(task_path.read_text())
    method = next(m for m in manifest["methods"] if m["id"] == method_id)
    output = owned_output(root, output)
    if audit_input is None:
        if manifest["config"]["teacher"] == "oracle.teachers.ordered:execute":
            from oracle.teachers.ordered import execute
        elif manifest["config"]["teacher"] == "oracle.teachers.official:execute":
            from oracle.teachers.official import execute
        else:
            raise ValueError("Unregistered teacher implementation")
        bound = bind_callable(execute, manifest["config"]["teacher"], package)
        result = execute(root, task, method, manifest["protocol"], output)
        write_json(output / "binding.json", {"actual_implementation": bound,
                   "manifest_sha256": digest(manifest_path), "task_sha256": digest(task_path),
                   "method_sha256": content_digest(method), "result_sha256": digest(output / "result.json")})
    else:
        from oracle.verification.route_replay import audit
        audit_input = owned_output(root, audit_input)
        binding = json.loads(audit_input.with_name("binding.json").read_text())
        record = json.loads(audit_input.read_text())
        if binding["manifest_sha256"] != digest(manifest_path) or binding["result_sha256"] != digest(audit_input) or record["method"] != method:
            raise RuntimeError("Execution binding or method mismatch")
        actual = binding["actual_implementation"]
        if record["teacher_sha256"] != actual["sha256"] or Path(record["actual_teacher_path"]).resolve() != Path(actual["actual_path"]).resolve() or record["protocol"] != manifest["protocol"]:
            raise RuntimeError("Actual worker/protocol differs from intended binding")
        bind_callable(audit, manifest["config"]["auditor"], package)
        result = audit(root, task, audit_input, output)
    require_sources(manifest["sources"])
    return result


def run_study(case_root, manifest_path):
    root, manifest_path = Path(case_root).resolve(), Path(manifest_path).resolve()
    study = owned_output(root, manifest_path.parent)
    manifest = json.loads(manifest_path.read_text())
    require_sources(manifest["sources"])
    import fcntl
    lease = (study / "controller.lock").open("a")
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (study / "controller-process.json").exists():
        raise RuntimeError("Existing study attempt; do not restart blindly")
    write_json(study / "controller-process.json", {"pid": os.getpid(), "start_ticks": Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19]})
    import psutil
    usage = psutil.cpu_percent(interval=1, percpu=True)
    idle = [i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i] < 15]
    if len(idle) < manifest["config"]["max_workers"] or psutil.virtual_memory().available < 8 * 2**30:
        raise RuntimeError("Insufficient idle CPU/memory for declared study")
    cpus = sorted(idle, key=lambda i: usage[i])[:manifest["config"]["max_workers"]]
    write_json(study / "resource-allocation.json", {"cpu_ids": cpus, "gpus": [], "time": timestamp()})
    mutex, free, stop = threading.Lock(), list(cpus), threading.Event()
    rows = []
    start = time.monotonic()

    def note(status, **extra):
        write_json(study / "state.json", {"status": status, "time": timestamp(), "completed": len(rows),
                   "expected": manifest["expected_executions"], **extra}, immutable=False)

    def job(item):
        task, method = item
        if stop.is_set():
            return None
        with mutex:
            cpu = free.pop()
        identifier = hashlib.sha256(task["task_key"].encode()).hexdigest()[:24]
        directory = study / method["id"] / identifier
        logdir = study / "logs" / method["id"]
        logdir.mkdir(parents=True, exist_ok=True)
        try:
            require_sources(manifest["sources"])
            if time.monotonic() - start > manifest["config"]["study_wall_seconds_cap"]:
                raise RuntimeError("Study wall cap exhausted")
            for operation, output, record in [("route-worker", directory, None), ("route-audit", directory / "independent-audit.json", directory / "result.json")]:
                command = [sys.executable, "-B", str(root / "oracleAdapter/run.py"), operation,
                           "--case-root", str(root), "--manifest", str(manifest_path), "--task-file", task["path"],
                           "--method", method["id"], "--output", str(output), "--cpu", str(cpu)]
                if record is not None:
                    command += ["--input", str(record)]
                log_path = logdir / (identifier + "." + operation + ".log")
                with log_path.open("xb") as log:
                    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                               env={**os.environ, "CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "PYTHONHASHSEED": "0"})
                    ticks = Path(f"/proc/{process.pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
                    write_json(log_path.with_suffix(".process.json"), {"pid": process.pid, "start_ticks": ticks, "cpu": cpu, "command": command})
                    try:
                        code = process.wait(timeout=manifest["config"]["per_worker_process_wall_seconds_cap"])
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        try:
                            process.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        raise RuntimeError("Owned worker exceeded predeclared wall cap")
                if code != 0:
                    raise RuntimeError(f"{operation} exited {code}")
            audit = json.loads((directory / "independent-audit.json").read_text())
            result = json.loads((directory / "result.json").read_text())
            if audit["status"] == "AUDIT_DISAGREEMENT":
                stop.set()
            return {"task_key": task["task_key"], "cohort": task["cohort"], "method": method["id"],
                    "status": audit["status"], "failure": result["failure"], "detail": result["detail"],
                    "cost": result["cost"], "audit_wall_seconds": audit["wall_seconds"],
                    "result_path": str(directory / "result.json"), "result_sha256": digest(directory / "result.json"),
                    "audit_path": str(directory / "independent-audit.json"), "audit_sha256": digest(directory / "independent-audit.json")}
        except Exception as error:
            stop.set()
            return {"task_key": task["task_key"], "method": method["id"], "status": "INFRASTRUCTURE_FAILURE", "error": repr(error)}
        finally:
            with mutex:
                free.append(cpu)

    items = [(task, method) for task in manifest["tasks"] for method in manifest["methods"]]
    # Real execution and its independent audit are checked before filling the pool.
    first = job(items[0])
    rows.append(first)
    write_json(study / "results-index.json", rows, immutable=False)
    note("RUNNING" if not stop.is_set() else "STOPPED_FOR_EVIDENCE_REVIEW", cpu_ids=cpus)
    if not stop.is_set():
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(cpus)) as pool:
            futures = [pool.submit(job, item) for item in items[1:]]
            for future in concurrent.futures.as_completed(futures):
                row = future.result()
                if row is not None:
                    rows.append(row)
                    write_json(study / "results-index.json", rows, immutable=False)
                    note("STOPPED_FOR_EVIDENCE_REVIEW" if stop.is_set() else "RUNNING", cpu_ids=cpus)
    complete = len(rows) == len(items) and not stop.is_set()
    write_json(study / "validation.json", {"status": "DEVELOPMENT_COMPLETE_NOT_FULL_COHORT_ACCEPTANCE" if complete else "INCOMPLETE_STOPPED_FOR_EVIDENCE_REVIEW",
               "complete": complete, "expected_executions": len(items), "observed_records": len(rows),
               "manifest_sha256": digest(manifest_path), "results": rows,
               "limits": "Fixed mapping, known development cohort, all failures retained. No baseline model metric or global coverage claim."})
    note("DEVELOPMENT_COMPLETE_NOT_FULL_COHORT_ACCEPTANCE" if complete else "INCOMPLETE_STOPPED_FOR_EVIDENCE_REVIEW")
    return complete


def dispatch(args):
    if not os.environ.get("CASE1_PROTECTION") or not args.case_root:
        raise RuntimeError("Protected runtime and case root required")
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.nice(10)
    if args.command in {"route-worker", "route-audit"}:
        if args.cpu is None or args.cpu not in sorted(os.sched_getaffinity(0))[:64]:
            raise ValueError("Explicit allowed CPU required")
        os.sched_setaffinity(0, [args.cpu])
        worker(args.case_root, args.manifest, args.task_file, args.method, args.output,
               audit_input=args.input if args.command == "route-audit" else None)
    elif args.command == "prepare-route-study":
        manifest = prepare(args.case_root, args.output)
        print({"tasks": manifest["expected_tasks"], "executions": manifest["expected_executions"]})
    elif args.command == "prepare-official-study":
        from oracle.research.official_study import prepare as prepare_official
        manifest = prepare_official(args.case_root, args.output)
        print({"source_scope": manifest["source_scope_denominator"], "executions": manifest["expected_executions"],
               "source_unavailable": len(manifest["nonexecuted_source_records"])})
    elif args.command == "prepare-portfolio-study":
        from oracle.research.portfolio_study import prepare as prepare_portfolio
        manifest = prepare_portfolio(args.case_root, args.output)
        print({"tasks": manifest["expected_tasks"], "executions": manifest["expected_executions"],
               "source_scope": manifest["source_scope_denominator"]})
    elif args.command == "prepare-search-ablation":
        from oracle.research.search_ablation import prepare as prepare_ablation
        manifest = prepare_ablation(args.case_root, args.output)
        print({"tasks": manifest["expected_tasks"], "executions": manifest["expected_executions"],
               "parent_scope": manifest["parent_source_scope_denominator"]})
    elif args.command == "prepare-execution-gate":
        from oracle.research.verification_gate import prepare as prepare_gate
        manifest=prepare_gate(args.case_root,args.output)
        print({'tasks':manifest['expected_tasks'],'scope':manifest['scope']})
    elif args.command == "run-route-study":
        run_study(args.case_root, args.manifest)
