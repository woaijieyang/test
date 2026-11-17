"""Freeze all historical official demonstration candidates and missing-source rows."""
import gzip
import hashlib
import json
import math
from pathlib import Path

from oracle.adapters.rxr.continuous_assets import source_identity, inspect_demonstration
from oracle.common.artifacts import content_digest, digest, freeze_sources, owned_output, package_sources, timestamp, write_json
from oracle.teachers.official import expand_actions


def prepare(case_root, output):
    root, output = Path(case_root).resolve(), owned_output(case_root, output)
    output.mkdir(parents=True, exist_ok=False)
    package, sources = package_sources()
    config = json.loads((package / "configs/experiments/official_reexecution.json").read_text())
    protocol = json.loads((package / config["protocol_config"]).read_text())
    summary_path, validation_path, parent_path = [root / config[k] for k in ["historical_summary", "historical_validation", "historical_parent"]]
    summary, validation, parent = [json.loads(p.read_text()) for p in [summary_path, validation_path, parent_path]]
    old = {t["task_key"]: t for t in parent["tasks"]}
    verified = {t["task_key"]: t for t in validation["results"]}
    if len(summary["records"]) != config["expected_source_scope"] or len({r["task_key"] for r in summary["records"]}) != config["expected_source_scope"]:
        raise ValueError("Historical scope identity mismatch")
    asset_validation = json.loads((root / config["asset_validation"]).read_text())
    source_locks = {str(Path(r["path"]).resolve()): r["sha256"] for r in asset_validation["sources"]}
    catalog = root / "outputs/landmark-connectivity/native-source-catalog-v1/catalog.json"
    catalog_sha = digest(catalog)
    available, unavailable = [], []
    ce = root / "data/datasets/RxR_VLNCE_v0"
    for split in ["train", "val_seen", "val_unseen"]:
        ep_path, gt_path = ce / split / f"{split}_guide.json.gz", ce / split / f"{split}_guide_gt.json.gz"
        for p in [ep_path, gt_path]:
            if digest(p) != source_locks[str(p.resolve())]: raise ValueError("Frozen official source changed")
        with gzip.open(ep_path, "rt") as stream: eps = {str(e["instruction"]["instruction_id"]): e for e in json.load(stream)["episodes"]}
        with gzip.open(gt_path, "rt") as stream: gt = json.load(stream)
        for row in sorted(summary["records"], key=lambda r:r["task_key"]):
            task = old[row["task_key"]]
            if task["split"] != split: continue
            ep = eps.get(str(task["instruction_id"]))
            if ep is None:
                if row["status"] != "NO_OFFICIAL_GT": raise ValueError("Historical source availability changed")
                unavailable.append({"task_key": task["task_key"], "status": "NOT_EXECUTED_SOURCE_IDENTITY_UNAVAILABLE",
                    "failure": "identity_or_adaptation_missing", "historical_record": row,
                    "source_record_sha256": task["source_record_sha256"], "retained_in_source_scope_denominator": True})
                continue
            if row["status"] == "NO_OFFICIAL_GT" or Path(ep["scene_id"]).parent.name != task["scene"]:
                raise ValueError("Official scene/identity mismatch")
            demonstration = gt[str(ep["episode_id"])]
            checked = inspect_demonstration(demonstration, ep["start_position"])
            if checked["errors"]: raise ValueError("Frozen asset contract differs")
            actions, _ = expand_actions(demonstration["actions"])
            trace_path = summary_path.parent / row["trace"]
            if row["task_key"] in verified and digest(trace_path) != verified[row["task_key"]]["trace_sha256"]:
                raise ValueError("Previously verified source trace changed")
            with gzip.open(trace_path, "rt") as stream: trace = json.load(stream)
            if (trace["start_rotation"] != ep["start_rotation"] or trace["actions"] != actions[:len(trace["actions"])]
                    or math.dist(trace["positions"][0], task["targets"][0]) > 1e-5):
                raise ValueError("Historical action/initial-state binding mismatch")
            prepared = {"task_key": task["task_key"], "cohort": "official_landmark_demonstration_strict_reexecution",
                "scene": task["scene"], "targets": task["targets"], "start_rotation": ep["start_rotation"],
                "purpose": "landmark_order_execution", "objective": "visit_landmark_occurrences_in_order",
                "privileges": ["true_pose", "navigation_mesh", "goal", "reference_path", "source_geometry", "landmark_annotations", "official_actions"],
                "profile_path": parent["profile_path"], "profile_sha256": parent["profile_sha256"],
                "geometry_catalog_sha256": catalog_sha, "module_source_sha256": content_digest(sources),
                "source_record_sha256": task["source_record_sha256"], "historical_replay_status": row["status"],
                "historical_trace_sha256": digest(trace_path), "historical_parent_sha256": digest(parent_path),
                "official_demonstration": {"episode_id": str(ep["episode_id"]), "instruction_id": str(task["instruction_id"]),
                    "episode_sha256": source_identity(ep)["sha256"], "gt_sha256": source_identity(demonstration)["sha256"],
                    "start_position": ep["start_position"], "actions": demonstration["actions"],
                    "actions_sha256": content_digest(demonstration["actions"]), "source_paths": [str(ep_path), str(gt_path)],
                    "source_file_sha256": [source_locks[str(ep_path.resolve())], source_locks[str(gt_path.resolve())]]}}
            path = output / "inputs" / (hashlib.sha256(task["task_key"].encode()).hexdigest()[:24]+".json")
            write_json(path, prepared)
            available.append({"task_key": task["task_key"], "path": str(path), "sha256": digest(path),
                              "cohort": prepared["cohort"], "selection_role": row["status"]})
        del eps, gt
    if len(available)!=config["expected_available"] or len(unavailable)!=config["expected_no_official_episode"]:
        raise ValueError("Available and unavailable scope mismatch")
    manifest = {"status": "FROZEN_BEFORE_STRICT_OFFICIAL_REEXECUTION", "created_at": timestamp(),
        "config": config, "protocol": protocol, "methods": config["methods"], "tasks": available,
        "expected_tasks":len(available), "expected_executions":len(available),
        "source_scope_denominator":len(available)+len(unavailable), "nonexecuted_source_records":unavailable,
        "sources":sources, "historical_summary_sha256":digest(summary_path),
        "historical_validation_sha256":digest(validation_path), "parent_manifest_sha256":digest(parent_path),
        "official_asset_validation_sha256":digest(root/config["asset_validation"]),
        "launchers":{str(root/"oracleAdapter/run.py"):digest(root/"oracleAdapter/run.py"), str(root/"scripts/with_runtime.sh"):digest(root/"scripts/with_runtime.sh")},
        "scope":config["scope"], "experimental_factor":"Stricter validation of existing official plans under same historical demonstration initial state; not algorithm comparison"}
    write_json(output/"manifest.json",manifest);freeze_sources(output,sources)
    write_json(output/"state.json",{"status":"PREPARED","executable_candidates":len(available),"source_scope_denominator":192,"source_unavailable":len(unavailable)})
    return manifest
