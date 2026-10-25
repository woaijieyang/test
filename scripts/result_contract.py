"""Strict result aggregation and registration. Raw evidence is never edited here."""

import collections, datetime, json, math
from pathlib import Path
from workspace import ROOT, atomic_json, digest, owned, read_json

METRICS = ("sr", "spl", "ndtw", "ne", "oracle_sr")
COUNTS = {"r2r": 1839, "rxr": 1223}


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def finite_metrics(row):
    for name in METRICS:
        value = row.get("metrics", {}).get(name)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("Nonfinite or missing " + name)
        if value < 0 or (name != "ne" and value > 1):
            raise ValueError("Invalid metric scale: " + name)


def aggregate(manifest, results):
    expected = manifest["expected_tasks"]
    expected_by_key = {r["task_key"]: r for r in expected}
    if len(expected_by_key) != len(expected):
        raise ValueError("Duplicate expected identity")
    keys = [r["task_key"] for r in results]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate result identity")
    if not set(keys) <= set(expected_by_key):
        raise ValueError("Unexpected task identity")
    grouped = collections.defaultdict(list)
    errors = []
    for row in results:
        spec = expected_by_key[row["task_key"]]
        if row["dataset"] != spec["dataset"]:
            raise ValueError("Dataset mismatch")
        if row.get("status") != "completed":
            errors.append(row["task_key"])
            continue
        finite_metrics(row)
        grouped[row["dataset"]].append(row)
    summaries = {}
    for ds in sorted({r["dataset"] for r in expected}):
        completed = grouped[ds]
        count = sum(r["dataset"] == ds for r in expected)
        summaries[ds] = {
            "expected": count,
            "completed": len(completed),
            "navigation_failures": sum(r["metrics"]["sr"] == 0 for r in completed),
            "valid": {k: len(completed) for k in METRICS},
            "nonfinite": {k: 0 for k in METRICS},
            "metrics": {
                k: sum(r["metrics"][k] for r in completed) / len(completed) if completed else None
                for k in METRICS
            },
        }
    protocol=manifest.get('annotation_protocol',{})
    corrected=set(protocol.get('start_episode_ids',[]))|set(protocol.get('goal_episode_ids',[]))
    if corrected and 'rxr' in summaries:
        subsets={}
        for label,selected in [('corrected_9',True),('unchanged_1214',False)]:
            group=[r for r in grouped['rxr'] if (r['task_key'].split('|')[-2] in corrected)==selected]
            subsets[label]={'completed':len(group),'metrics':{k:sum(r['metrics'][k] for r in group)/len(group) if group else None for k in METRICS}}
        summaries['rxr']['annotation_subgroups']=subsets
    return {
        "schema_version": 1,
        "run_id": manifest["run_id"],
        "claim_scope": manifest["claim_scope"],
        "complete": set(keys) == set(expected_by_key) and not errors,
        "missing": sorted(set(expected_by_key) - set(keys)),
        "runtime_errors": errors,
        "datasets": summaries,
    }


def audit(run):
    run = owned(run).resolve()
    manifest = read_json(run / "run_manifest.json")
    results = rows(run / "results.jsonl")
    summary = aggregate(manifest, results)
    if not summary["complete"]:
        raise ValueError("Incomplete run or runtime errors")
    if manifest["claim_scope"] != "online_navigation" or manifest["scope"] != "full":
        raise ValueError("Not a formal full navigation run")
    from preflight import load, task_key

    authoritative = set()
    for ds, spec in manifest["datasets"].items():
        source = load(spec["annotation"])["episodes"]
        authoritative.update(
            task_key(ds, e)
            for e in source
            if ds != "rxr" or e["instruction"]["language"] == "en-US"
        )
    if authoritative != {r["task_key"] for r in manifest["expected_tasks"]}:
        raise ValueError("Expected identities do not match original full annotations")
    for ds, record in summary["datasets"].items():
        if ds not in COUNTS or record["expected"] != COUNTS[ds]:
            raise ValueError("Not the full authorized split")
    if not manifest.get("frozen_files"):
        raise ValueError("Missing frozen input/source identity")
    for item in manifest["frozen_files"]:
        if digest(item["path"]) != item["sha256"]:
            raise ValueError("Frozen input changed: " + item["path"])
    # Recompute receipt is a distinct artifact generated from raw trajectories, not aggregate.

    independent = read_json(run / "independent_metrics.json")
    if independent.get("method") != "trajectory_recompute_v1" or independent.get(
        "manifest_sha256"
    ) != digest(run / "run_manifest.json"):
        raise ValueError("Wrong independent metric provenance")
    recomputed = {r["task_key"]: r for r in independent["results"]}
    if len(recomputed) != len(independent["results"]) or set(recomputed) != {
        r["task_key"] for r in results
    }:
        raise ValueError("Independent coverage mismatch")
    evidence = []
    for row in results:
        finite_metrics(recomputed[row["task_key"]])
        if recomputed[row["task_key"]].get("trace_sha256") != row["trace_sha256"]:
            raise ValueError("Independent metrics refer to a different trace")
        for k in METRICS:
            if not math.isclose(
                row["metrics"][k],
                recomputed[row["task_key"]]["metrics"][k],
                rel_tol=1e-6,
                abs_tol=1e-5,
            ):
                raise ValueError("Metric mismatch: " + row["task_key"] + " " + k)
        trace = owned(run / row["trace_path"]).resolve()
        config_path = owned(run / row["effective_config_path"]).resolve()
        if run not in config_path.parents or digest(config_path) != row["effective_config_sha256"]:
            raise ValueError("Effective configuration changed or escaped the run")
        if run not in trace.parents or digest(trace) != row["trace_sha256"]:
            raise ValueError("Trace identity mismatch")
        trace_rows = rows(trace)
        if (
            not trace_rows
            or trace_rows[0]["kind"] != "reset"
            or trace_rows[-1]["kind"] != "terminal"
        ):
            raise ValueError("Unclosed episode trace")
        if any(e["task_key"] != row["task_key"] for e in trace_rows):
            raise ValueError("Cross-episode trace")
        evidence.append({"task_key": row["task_key"], "trace_sha256": row["trace_sha256"]})
    semantic = read_json(run / "semantic_audit.json")
    traces = {r["task_key"]: (r["trace_path"], r["trace_sha256"]) for r in results}
    audited_traces = {
        r["task_key"]: (r["path"], r["sha256"]) for r in semantic.get("trace_files", [])
    }
    if audited_traces != traces or len(semantic.get("trace_files", [])) != len(results):
        raise ValueError("Semantic audit does not bind every current trace")
    if not semantic.get("image_files"):
        raise ValueError("Semantic audit lacks model-image integrity records")
    for image in semantic["image_files"]:
        image_path = owned(run / image["path"]).resolve()
        if run not in image_path.parents or digest(image_path) != image["sha256"]:
            raise ValueError("Recorded model image changed after semantic audit")
    expected_configs = {r["effective_config_path"]: r["effective_config_sha256"] for r in results}
    if read_json(run / "effective-configs.json") != {
        "files": [{"path": path, "sha256": sha} for path, sha in sorted(expected_configs.items())]
    }:
        raise ValueError("Effective configuration bundle is incomplete or inconsistent")
    if semantic.get("method") != "model_action_trace_audit_v1" or semantic.get(
        "manifest_sha256"
    ) != digest(run / "run_manifest.json"):
        raise ValueError("Wrong semantic audit provenance")
    if (
        semantic.get("status") != "PASS"
        or semantic.get("errors") != []
        or set(semantic.get("task_keys", [])) != set(recomputed)
    ):
        raise ValueError("Semantic audit not accepted")
    receipts = {
        name: digest(run / name)
        for name in (
            "run_manifest.json",
            "results.jsonl",
            "independent_metrics.json",
            "semantic_audit.json",
            "effective-configs.json",
        )
    }
    return summary, {
        "schema_version": 1,
        "status": "PASS",
        "run_id": manifest["run_id"],
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "receipts": receipts,
        "episode_evidence": evidence,
        "metric_tolerance": {"abs": 1e-5, "rel": 1e-6},
    }


def _register_locked(run, registry=None):
    run = owned(run).resolve()
    registry = Path(registry) if registry else ROOT / "results-show/records.json"
    summary, validation = audit(run)
    stored = read_json(run / "validation.json")
    if stored.get("status") != "PASS" or stored["receipts"] != validation["receipts"]:
        raise ValueError("Validation receipt is absent or stale")
    if read_json(run / "summary.json") != summary:
        raise ValueError("Stale summary")
    index = read_json(registry)
    manifest = read_json(run / "run_manifest.json")
    record_id = manifest["record_id"]
    if not record_id or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for c in record_id
    ):
        raise ValueError("Unsafe record ID")
    if any(
        r["record_id"] == record_id or r["run_id"] == manifest["run_id"] for r in index["records"]
    ):
        raise ValueError("Duplicate record or run")
    identity = {
        k: manifest[k]
        for k in (
            "model",
            "model_sha256",
            "source_sha256",
            "config_sha256",
            "navmesh_sha256",
            "benchmark_sha256",
            "split",
            "language",
        )
    }
    identity.update(
        {
            "base_config_sha256": manifest["config_sha256"],
            "config_sha256": digest(run / "effective-configs.json"),
            "model_code_path": str(ROOT / "src"),
            "dataset_paths": {ds: spec["annotation"] for ds, spec in manifest["datasets"].items()},
            "dataset_manifest_path": str(run / "run_manifest.json"),
            "navmesh_profile": manifest["navmesh_profile"],
            "annotation_protocol": manifest.get('annotation_protocol',{'protocol_id':'original-annotations'}),
            "annotation_derivative_sha256": manifest.get('annotation_derivative_sha256'),
        }
    )
    index["records"].append(
        {
            "record_id": record_id,
            "run_id": manifest["run_id"],
            "status": "complete",
            "artifact_path": str(run),
            "registered_at": validation["checked_at"],
            "identity": identity,
            "summary": summary,
            "receipts": {
                **validation["receipts"],
                "summary.json": digest(run / "summary.json"),
                "validation.json": digest(run / "validation.json"),
            },
        }
    )
    atomic_json(registry, index)


def register(run, registry=None):
    import fcntl

    lock = ROOT / ".cache/results-register.lock"
    lock.parent.mkdir(exist_ok=True)
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            _register_locked(run, registry)
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def render(index):
    output = [
        "# AwareVLN Case1 统一测评结果",
        "",
        "本表由已验收逐任务结果生成；原始证据保留在各运行目录。",
        "",
    ]
    reports = {}
    if not index["records"]:
        output += ["当前无通过全部验收门槛的正式结果。环境、诊断、部分运行不进入正式表。", ""]
    for ds, title in [("r2r", "R2R"), ("rxr", "RxR-US")]:
        records = [r for r in index["records"] if ds in r["summary"]["datasets"]]
        if not records:
            continue
        output += [
            "## " + title + " 正式导航评测",
            "",
            "| Record ID | Scope | Episodes | Case | Model | Version | Status | SR (%) | SPL (%) | nDTW (%) | NE (m) | Oracle SR (%) | Benchmark SHA | Model code path | Dataset/manifest path |",
            "|---|---|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|",
        ]
        for r in records:
            m = r["summary"]["datasets"][ds]
            v = m["metrics"]
            ident = r["identity"]
            version = ident["source_sha256"][:12] + " / mesh " + ident["navmesh_sha256"][:12] + " / " + ident.get("annotation_protocol",{}).get("protocol_id","original")
            output.append(
                f"| [{r['record_id']}]({r['record_id']}.md) | Full | {m['completed']}/{m['expected']} | case1 | {ident['model']} | {version} | {r['status']} | {v['sr']*100:.3f} | {v['spl']*100:.3f} | {v['ndtw']*100:.3f} | {v['ne']:.4f} | {v['oracle_sr']*100:.3f} | `{ident['benchmark_sha256']}` | `{ident['model_code_path']}` | `{ident['dataset_manifest_path']}` |"
            )
        output.append("")
        output += [
            "### 有限值与失败统计",
            "",
            "| Record ID | SPL valid/nonfinite | NE valid/nonfinite | nDTW valid/nonfinite | 普通导航失败 | 运行异常 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for r in records:
            m = r["summary"]["datasets"][ds]
            counts = [
                str(m["valid"][k]) + "/" + str(m["nonfinite"][k]) for k in ("spl", "ne", "ndtw")
            ]
            output.append(
                "| "
                + r["record_id"]
                + " | "
                + " | ".join(counts)
                + f" | {m['navigation_failures']} | {len(r['summary']['runtime_errors'])} |"
            )
        output.append("")
    for r in index["records"]:
        displayed_time = (
            datetime.datetime.fromisoformat(r["registered_at"])
            .astimezone(datetime.timezone(datetime.timedelta(hours=8)))
            .isoformat()
        )
        report = [
            "# " + r["record_id"],
            "",
            f"状态：{r['status']}。核验并登记时间：{displayed_time}（Asia/Singapore）。",
            "",
            "## 实验身份",
            "",
            "| 字段 | 实际身份 |",
            "|---|---|",
            f"| run_id | `{r['run_id']}` |",
            f"| 原始证据 | `{r['artifact_path']}` |",
        ]
        if 'rxr' in r['summary']['datasets'] and 'annotation_subgroups' in r['summary']['datasets']['rxr']:
            report.extend(['','派生标注协议：9条修正任务与1214条未修改标注任务分别统计；两组仅用于解释同一次完整测评，不作为独立的正式全量结果。',''])
            for label,group in r['summary']['datasets']['rxr']['annotation_subgroups'].items():
                report.append(label+': '+json.dumps(group,ensure_ascii=False))
        for k, v in r["identity"].items():
            report.append(
                "| "
                + k
                + " | `"
                + (json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else str(v))
                + "` |"
            )
        report += [
            "",
            "## 正式指标与覆盖",
            "",
            "| Dataset | 完成/计划 | SR (%) | SPL (%) | nDTW (%) | NE (m) | Oracle SR (%) | 普通失败 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for ds, m in r["summary"]["datasets"].items():
            v = m["metrics"]
            report.append(
                f"| {ds} | {m['completed']}/{m['expected']} | {v['sr']*100:.3f} | {v['spl']*100:.3f} | {v['ndtw']*100:.3f} | {v['ne']:.4f} | {v['oracle_sr']*100:.3f} | {m['navigation_failures']} |"
            )
        report += [
            "",
            "## 验证与可追溯证据",
            "",
            "登记前核对了原始标注的完整身份集合、缺失/重复、输入与源码哈希、原生指标和轨迹独立复算，以及模型输出解析到实际primitive动作的一致性。普通导航失败仍计入分母。",
            "",
            "| 运行目录内文件 | SHA-256 |",
            "|---|---|",
        ]
        report += ["| " + name + " | `" + sha + "` |" for name, sha in r["receipts"].items()]
        report += [
            "",
            "## 协议与结论边界",
            "",
            "修复网格使用独立版本，不与旧网格历史成绩直接计算收益。模型到动作的一致性验证不等于每条导航语义正确；实际导航失败如实保留。33条修复过程、所有尝试和限制见[本阶段结论](../docs/zx/2026-10-14-2-conclusion-基线重建与全量测评.md)。",
            "",
        ]
        reports[r["record_id"] + ".md"] = "\n".join(report)
    return "\n".join(output), reports
