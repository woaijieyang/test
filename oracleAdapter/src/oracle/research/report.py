"""Evidence-bound paired reports; never pool unlike tasks or discard failures."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import zipfile

from oracle.common.artifacts import content_digest, digest, owned_output, package_sources, freeze_sources, write_json

PASS = "PASS_ORDERED_NATIVE_AND_RATIONAL_REPLAY"
COSTS = ("total_wall_seconds", "cpu_seconds", "actual_native_calls", "native_preview_calls",
         "source_queries", "triangle_checks", "search_expansions", "peak_rss_kib")


def comparison_limits(manifest):
    common = ["Development tasks historically exposed; not blind generalization.",
              "Rational replay shares native geometry and physical formulation; not physical-model independence.",
              "Finite failures do not prove physical unreachability. No model score or full-cohort claim."]
    if any('reference_progress_guard' in m for m in manifest.get('methods',[])):
        return common + ["Three arms separate planning-query cache from the additional reference-progress fallback; identical task goals, information, source gates and budgets.",
                         "Known Landmark train development strata only; no sealed R2R/RxR re-evaluation or full33954 coverage claim.",
                         "Cache changes computation cost; a wall-time-limited search may therefore explore more nodes without a larger budget.",
                         "Rejected unexecuted progress predictions are separately probed in replay, not counted as executed route actions.",
                         "RSS quantiles/max describe individual records; sums of RSS samples are not process-concurrent memory. Native greedy internal calls remain uninstrumented."]
    if manifest["config"].get("comparison_factor") == "search_without_official_action_information":
        return common + ["Same133 physical tasks as portfolio development, but official action payload and privilege removed; separate actual information condition.",
                         "The other59 parent source records were not attempted in this matched control; they are retained as provenance, not declared pure-search failures.",
                         "Search ceilings unchanged; greedy internal simulator probes are uninstrumented, so report wall/CPU alongside preview counters."]
    if manifest["config"].get("comparison_factor") == "guarded_prefix_fallback":
        return common + ["Same actual official-action information, initial state, targets, profile and gates; only fixed fallback availability differs.",
                         "Equal budget ceilings do not mean equal realized computation; combination costs and failures remain included.",
                         "Fallback greedy C++ internal probes remain uninstrumented; native preview counters are not total simulator work.",
                         "No claim that this conventional fixed portfolio is a novel algorithm; missing-source cases remain in the source denominator."]
    if manifest["config"]["teacher"] == "oracle.teachers.official:execute":
        return common + ["Official action privilege and historical demonstration initial-state lineage; not algorithm improvement over the different-start Oracle.",
                         "All source-unavailable records remain in the source-scope denominator; actual traces stop upon first violation or ordered target completion."]
    return common + ["Only state key differs; common cost/depth correction not attributed to this factor.",
                     "Greedy internal native probes uninstrumented; adapter call counts are not complete simulator cost."]


def source_scope_summary(tasks, nonexecuted, rows, denominator):
    keys = {r["task_key"] for r in nonexecuted}
    if len(keys) != len(nonexecuted) or keys & set(tasks) or len(keys)+len(tasks) != denominator:
        raise ValueError("Source-unavailable denominator changed")
    methods = sorted({r['method'] for r in rows})
    return {"denominator": denominator, "actually_executed_tasks_per_method": len(tasks),
            "nonexecuted_records": nonexecuted, "not_navigation_passes": len(nonexecuted),
            "pass_count_by_method_with_full_source_denominator": {
                method:sum(r['method']==method and r['status']==PASS for r in rows) for method in methods}}


def statistics(values):
    values = sorted(float(v) for v in values)
    if not values or any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("Invalid or absent cost evidence")
    def quantile(q):
        at = (len(values) - 1) * q
        low, high = math.floor(at), math.ceil(at)
        return values[low] + (values[high] - values[low]) * (at - low)
    return {"count": len(values), "sum": sum(values), "p50": quantile(.5), "p95": quantile(.95), "max": values[-1]}


def summarize_rows(rows, methods):
    if not methods or len(set(methods)) != len(methods):
        raise ValueError("Explicit unique method order required")
    indexed = {}
    for row in rows:
        key = (row["cohort"], row["task_key"], row["method"])
        if key in indexed or row["method"] not in methods:
            raise ValueError("Duplicate or unexpected method result")
        if row["status"] not in {PASS, "FAILURE_PRESERVED"}:
            raise ValueError("Unresolved infrastructure or audit disagreement")
        indexed[key] = row
    report = {"cohorts": {}, "quantile_definition": "linear interpolation at (n-1)*q; includes failures"}
    for cohort in sorted({key[0] for key in indexed}):
        tasks = sorted({key[1] for key in indexed if key[0] == cohort})
        if any((cohort, task, method) not in indexed for task in tasks for method in methods):
            raise ValueError("Incomplete paired denominator")
        table = {"tasks": len(tasks), "methods": {}, "paired": {}}
        for method in methods:
            records = [indexed[(cohort, task, method)] for task in tasks]
            table["methods"][method] = {
                "tasks": len(records), "passed": sum(r["status"] == PASS for r in records),
                "failures": dict(Counter(r["failure"] for r in records if r["status"] != PASS)),
                "cost": {k: statistics([r["cost"][k] for r in records]) for k in COSTS},
                "audit_wall_seconds": statistics([r["audit_wall_seconds"] for r in records])}
        for method in methods[1:]:
            groups = {"retained_pass": [], "recovered": [], "regressed": [], "both_failed": []}
            for task in tasks:
                old = indexed[(cohort, task, methods[0])]["status"] == PASS
                new = indexed[(cohort, task, method)]["status"] == PASS
                groups["retained_pass" if old and new else "recovered" if new else "regressed" if old else "both_failed"].append(task)
            table["paired"][method] = groups
        report["cohorts"][cohort] = table
    return report


def report(case_root, run_path, output):
    root = Path(case_root).resolve()
    run, output = owned_output(root, run_path), owned_output(root, output)
    validation_path, manifest_path = run / "validation.json", run / "manifest.json"
    validation, manifest = json.loads(validation_path.read_text()), json.loads(manifest_path.read_text())
    if not validation["complete"] or validation["manifest_sha256"] != digest(manifest_path):
        raise ValueError("Study not complete or manifest identity changed")
    rows = validation["results"]
    expected = {(t["task_key"], m["id"]) for t in manifest["tasks"] for m in manifest["methods"]}
    if len(rows) != len(expected) or {(r["task_key"], r["method"]) for r in rows} != expected:
        raise ValueError("Full frozen coverage mismatch")
    with zipfile.ZipFile(run / "source.zip") as archive:
        if set(archive.namelist()) != set(manifest["sources"]):
            raise ValueError("Source archive file set mismatch")
        for name, value in manifest["sources"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != value:
                raise ValueError("Archived executable source changed")
    tasks = {t["task_key"]: t for t in manifest["tasks"]}
    contexts, replay_max, actual_actions = {}, 0., 0
    teacher_source = {"oracle.teachers.ordered:execute": "teachers/ordered.py",
                      "oracle.teachers.official:execute": "teachers/official.py"}[manifest["config"]["teacher"]]
    for row in rows:
        result_path, audit_path = Path(row["result_path"]), Path(row["audit_path"])
        if not result_path.resolve().is_relative_to(run) or not audit_path.resolve().is_relative_to(run):
            raise ValueError("Evidence path escapes study")
        if digest(result_path) != row["result_sha256"] or digest(audit_path) != row["audit_sha256"]:
            raise ValueError("Result or audit changed")
        record, audit = json.loads(result_path.read_text()), json.loads(audit_path.read_text())
        task_entry = tasks[row["task_key"]]
        task_path = Path(task_entry["path"])
        if digest(task_path) != task_entry["sha256"]:
            raise ValueError("Task changed")
        task = json.loads(task_path.read_text())
        method = next(m for m in manifest["methods"] if m["id"] == row["method"])
        binding = json.loads(result_path.with_name("binding.json").read_text())
        if (record["task_sha256"] != content_digest(task) or audit["task_sha256"] != record["task_sha256"]
                or record["method"] != method or record["protocol"] != manifest["protocol"]
                or audit["source_result_sha256"] != row["result_sha256"]
                or binding["manifest_sha256"] != digest(manifest_path)
                or binding["task_sha256"] != task_entry["sha256"]
                or binding["result_sha256"] != row["result_sha256"]
                or record["teacher_sha256"] != manifest["sources"][teacher_source]
                or audit["auditor_sha256"] != manifest["sources"]["verification/route_replay.py"]):
            raise ValueError("Actual worker/task/protocol binding mismatch")
        if (audit["status"] != row["status"] or record["cost"] != row["cost"]
                or record["failure"] != row["failure"] or record["detail"] != row["detail"]
                or audit["wall_seconds"] != row["audit_wall_seconds"]):
            raise ValueError("Indexed result differs from underlying evidence")
        if row["status"] == PASS and (not audit["full_route_accepted"] or audit["issues"] or audit["physical_alerts"]):
            raise ValueError("Invalid acceptance claim")
        context = content_digest([record["task_sha256"], record["task_contract"], record["profile_sha256"],
                                  record["geometry_sha256"], record["protocol"], record["environment"]])
        previous = contexts.setdefault(row["task_key"], context)
        if previous != context:
            raise ValueError("Paired task/environment/privilege mismatch")
        replay_max = max(replay_max, audit["max_position_error_m"])
        actual_actions += audit["executed_actions_replayed"]
    summary = summarize_rows(rows, [m["id"] for m in manifest["methods"]])
    nonexecuted = manifest.get("nonexecuted_source_records", [])
    if nonexecuted:
        summary["source_scope"] = source_scope_summary(tasks, nonexecuted, rows, manifest['source_scope_denominator'])
    summary.update(status="COMPLETE_PAIRED_DEVELOPMENT_EVIDENCE_NOT_FULL_COHORT", records=len(rows),
        evaluation_scope=manifest.get("scope"),
        source_validation_sha256=digest(validation_path), manifest_sha256=digest(manifest_path),
        actual_actions_replayed=actual_actions, max_replay_error_m=replay_max,
        limits=comparison_limits(manifest))
    output.mkdir(parents=True, exist_ok=False)
    package, sources = package_sources()
    freeze_sources(output, sources)
    write_json(output / "summary.json", summary)
    write_json(output / "validation.json", {"status": "REPORT_IDENTITIES_COVERAGE_AND_PAIRS_CHECKED",
               "summary_sha256": digest(output / "summary.json"), "reporter_sha256": digest(__file__),
               "source_zip_sha256": digest(output / "source.zip"), "input_run": str(run), "records": len(rows)})
    lines = ["# Fixed development comparison", "", "All failed tasks are retained. Different objectives are reported separately.", ""]
    if nonexecuted:
        lines += [f"Source scope denominator: {manifest['source_scope_denominator']}; executed: {len(tasks)}; source unavailable: {len(nonexecuted)} (retained, not PASS).", ""]
    for cohort, table in summary["cohorts"].items():
        lines += ["## " + cohort, "", "|Method|Passed/tasks|Wall P50/P95 (s)|CPU total (s)|Actual actions|Search expansions|", "|---|---:|---:|---:|---:|---:|"]
        for method, values in table["methods"].items():
            cost = values["cost"]
            lines += [f"|{method}|{values['passed']}/{values['tasks']}|{cost['total_wall_seconds']['p50']:.3f}/{cost['total_wall_seconds']['p95']:.3f}|{cost['cpu_seconds']['sum']:.3f}|{int(cost['actual_native_calls']['sum'])}|{int(cost['search_expansions']['sum'])}|"]
        for method, paired in table["paired"].items():
            lines += ["", method + " vs control: " + ", ".join(f"{key}={len(value)}" for key, value in paired.items()) + "."]
        lines += [""]
    lines += ["Limits:", ""] + ["- " + value for value in summary["limits"]]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
