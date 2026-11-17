"""Read-only identity accounting. Missing data never becomes a filtering claim."""
from collections import Counter, defaultdict
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path

from .occurrences import align_subpaths


def canonical_id(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a dataset ID")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not value.is_integer() or abs(value) > 2**53:
            raise ValueError("Unsafe numeric ID conversion")
        return str(int(value))
    if isinstance(value, str) and value.strip().isdecimal():
        return str(int(value.strip()))
    raise ValueError("Unsupported dataset ID representation")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(case_root, config, output):
    root = Path(case_root).resolve()
    output = Path(output).resolve()
    if not output.is_relative_to(root / "outputs" / "oracleAdapter"):
        raise ValueError("Research evidence must remain in case1 outputs/oracleAdapter")
    if output.exists():
        raise FileExistsError("Immutable research run already exists")
    legacy = root / config["legacy_identity_receipt"]
    nodes_path = root / config["legacy_node_receipt"]
    previous = json.loads(legacy.read_text())
    nodes = json.loads(nodes_path.read_text())
    sources = previous["sources"]
    guides = defaultdict(list)
    all_ids = defaultdict(list)
    guide_paths = defaultdict(list)
    landmark = []
    for source in sources:
        path = Path(source["path"]).resolve()
        allowed = path.is_relative_to(root / "data") or path.is_relative_to(root.parent / "data/raw_data")
        if not allowed or digest(path) != source["sha256"]:
            raise ValueError("Unapproved or changed source: " + str(path))
        if path.suffix == ".gz":
            split = path.parent.name
            role = "follower" if "follower" in path.name else "guide"
            with gzip.open(path, "rt") as stream:
                episodes = json.load(stream)["episodes"]
            for ep in episodes:
                instruction = ep["instruction"]
                iid = canonical_id(instruction["instruction_id"])
                item = {"split": split, "role": role,
                        "instruction_id": iid,
                        "instruction_id_source_type": type(instruction["instruction_id"]).__name__,
                        "episode_id": canonical_id(ep["episode_id"]),
                        "scene": Path(ep["scene_id"]).parent.name,
                        "language": instruction["language"],
                        "trajectory_id": canonical_id(ep["trajectory_id"]) if "trajectory_id" in ep else None,
                        "reference_points": len(ep.get("reference_path", [])),
                        "source_path": str(path), "source_sha256": source["sha256"]}
                all_ids[iid].append(item)
                if role == "guide":
                    guides[(split, iid)].append(item)
                    if item["trajectory_id"] is not None:
                        guide_paths[(item["scene"], item["trajectory_id"])].append(item)
        else:
            records = json.loads(path.read_text())
            landmark.extend((row, source) for row in records)
    if len(landmark) != config["expected_records"]:
        raise ValueError("Wrong Landmark source denominator")
    previous_missing = {(r["split"], canonical_id(r["instruction_id"]))
                        for r in previous["missing_records"]}
    report, missing_report, alignment_report = [], [], []
    trajectory_relation = Counter()
    for raw, source in landmark:
        iid, pid = canonical_id(raw["instruction_id"]), canonical_id(raw["path_id"])
        split, scene = raw["split"], raw["scan"]
        exact = [r for r in guides[(split, iid)]
                 if r["scene"] == scene and r["language"] == raw["language"]]
        status = "EXACT_INSTRUCTION_SCENE_LANGUAGE" if len(exact) == 1 else (
            "AMBIGUOUS_IDENTITY" if exact else "NO_EXACT_CE_GUIDE_IDENTITY")
        if len(exact) == 1:
            trajectory_relation["equal_path_id" if exact[0]["trajectory_id"] == pid else "different_or_absent"] += 1
        row = {"task_key": f"{split}:{iid}", "split": split,
               "scene": scene, "instruction_id": iid, "path_id": pid,
               "language": raw["language"],
               "instruction_id_source_type": type(raw["instruction_id"]).__name__,
               "path_id_source_type": type(raw["path_id"]).__name__,
               "landmark_source_sha256": source["sha256"], "status": status,
               "exact_candidates": exact}
        report.append(row)
        alignment = align_subpaths(raw["path"], raw["sub_paths"])
        alignment_report.append({"task_key": row["task_key"],
                                 "subinstructions": len(raw["sub_instructions"]),
                                 "subpaths": len(raw["sub_paths"]),
                                 "source_path_length": len(raw["path"]),
                                 **asdict(alignment)})
        if (split, iid) in previous_missing:
            missing_report.append({**row, "all_split_role_id_candidates": all_ids[iid],
                                   "same_scene_trajectory_candidates_diagnostic_only": guide_paths[(scene, pid)],
                                   "cause": "still_absent_from_all_checked_CE_roles_splits_after_numeric_normalization" if not all_ids[iid] else "identity_candidates_require_review",
                                   "historical_conversion_or_filter_reason": "UNKNOWN_NOT_PROVIDED",
                                   "raw_RxR_version_match": "NOT_YET_VERIFIED",
                                   "text_matching_used": False})
    if len(missing_report) != config["expected_unmatched"]:
        raise ValueError("Lost an originally unmatched record")
    node_index = {(r["scene"], r["node"]): r for r in nodes["nodes"]}
    viewpoints = []
    for old in previous["missing_viewpoints"]:
        node = node_index.get((old["scene"], old["node"]))
        viewpoints.append({"scene": old["scene"], "source_viewpoint_id": old["node"],
                           "published_same_id_present": False,
                           "category": "PUBLISHED_GRAPH_MISSING_CONTINUOUS_REFERENCE_EXISTS" if old["has_official_guide_reference"] else "PUBLISHED_GRAPH_MISSING_UNRESOLVED",
                           "rename_merge_substitution_evidence": "NOT_ESTABLISHED",
                           "continuous_anchor_evidence": node,
                           "source_identity_not_spatial_nearest": True,
                           "native_reachability": "NOT_ESTABLISHED_BY_IDENTITY_LEDGER"})
    if len(viewpoints) != config["expected_missing_viewpoints"]:
        raise ValueError("Missing viewpoint denominator changed")
    output.mkdir(parents=True)
    for filename, records in [("all33954-identities.json", report),
                              ("unmatched8034.json", missing_report),
                              ("viewpoints461.json", viewpoints),
                              ("source-subpath-occurrences.json", alignment_report)]:
        (output / filename).write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    summary = {"status": "IDENTITY_ACCOUNTING_COMPLETE_NOT_ADAPTATION_OR_MOTION_ACCEPTANCE",
               "records": len(report), "unmatched_ledger": len(missing_report),
               "viewpoints_ledger": len(viewpoints),
               "identity_counts": dict(Counter(r["status"] for r in report)),
               "source_occurrence_counts": dict(Counter(r["status"] for r in alignment_report)),
               "matched_trajectory_id_relation": dict(trajectory_relation),
               "unmatched_with_any_role_or_split_id_candidate": sum(bool(r["all_split_role_id_candidates"]) for r in missing_report),
               "unmatched_with_scene_trajectory_candidate": sum(bool(r["same_scene_trajectory_candidates_diagnostic_only"]) for r in missing_report),
               "viewpoint_categories": dict(Counter(r["category"] for r in viewpoints)),
               "sources": sources,
               "legacy_receipts": {str(legacy): digest(legacy), str(nodes_path): digest(nodes_path)},
               "outputs": {p.name: digest(p) for p in output.glob("*.json")},
               "limits": "No new identity is inferred from nearest position or text. No annotation, geometry, official mapping or historical receipt changed. Raw RxR version/pose assets still require separate provenance review. All original records remain in the denominator."}
    (output / "validation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary
