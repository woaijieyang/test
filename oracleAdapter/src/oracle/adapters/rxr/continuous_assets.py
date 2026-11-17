"""Official continuous demonstration provenance and action/location semantics.

This is an asset audit, not replay and not a replacement of task targets.
"""
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path

from oracle.adapters.landmark_rxr.ledger import canonical_id
from oracle.common.artifacts import content_digest, digest, write_json


def source_identity(value):
    """Preserve source NaN tokens for fingerprinting; never accept them as poses."""
    fields = []
    def walk(item, path):
        if isinstance(item, float) and not math.isfinite(item):
            fields.append({"path": path, "value": repr(item)})
        elif isinstance(item, dict):
            for key, child in sorted(item.items()): walk(child, path + "." + key)
        elif isinstance(item, list):
            for index, child in enumerate(item): walk(child, path + f"[{index}]")
    walk(value, "")
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=True).encode()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "nonfinite_fields": fields,
            "encoding": "sorted compact Python JSON with source NaN/Infinity tokens; source fingerprint only"}


def inspect_demonstration(gt, start_position):
    actions, locations = gt["actions"], gt["locations"]
    errors = []
    if any(type(a) is not int for a in actions):
        errors.append("non_integer_action")
    if not actions or actions[-1] != 0 or sum(type(a) is int and a == 0 for a in actions) != 1:
        errors.append("not_single_terminal_stop")
    unsupported = sorted({a for a in actions if type(a) is int and a not in (0, 1, 2, 3)})
    if unsupported:
        errors.append("unsupported_current_native_actions")
    forward = sum(type(a) is int and a == 1 for a in actions)
    if gt.get("forward_steps") != forward:
        errors.append("forward_steps_mismatch")
    if len(locations) != forward + 1:
        errors.append("location_count_not_forward_plus_initial")
    if any(len(p) != 3 or any(not math.isfinite(x) for x in p) for p in locations):
        errors.append("invalid_location")
    initial_error = math.dist(locations[0], start_position) if locations and "invalid_location" not in errors else None
    expansion = None if unsupported or "non_integer_action" in errors else sum(2 if a in (2, 3) else 1 if a == 1 else 0 for a in actions)
    return {"errors": errors, "official_actions": len(actions), "forward_actions": forward,
            "locations": len(locations), "action_histogram": dict(Counter(str(a) for a in actions)),
            "unsupported_current_actions": unsupported, "expanded_navigation_actions": expansion,
            "location_action_indices": [0] + [i + 1 for i, a in enumerate(actions) if type(a) is int and a == 1],
            "initial_location_error_m": initial_error,
            "position_trace_scope": "initial_plus_forward_actions_not_full_pose_trace",
            "turn_height_response_observable_in_gt_locations": False,
            "conversion_scope": "integer angle expansion candidate only; not current native equivalence or physical acceptance"}


def audit(case_root, config, output):
    root, output = Path(case_root).resolve(), Path(output).resolve()
    old_receipt = root / config["source_identity_receipt"]
    legacy = json.loads(old_receipt.read_text())
    raw_sources = [s for s in legacy["sources"] if not s["path"].endswith(".gz")]
    if len(raw_sources) != 3:
        raise ValueError("Expected exactly three frozen Landmark source files")
    ce = root / config["continuous_dataset"]
    source_rows, records, distributions = [], [], Counter()
    historical = json.loads((root / config["historical_action_replay_summary"]).read_text())
    historical_index = {r["task_key"]: r for r in historical["records"]}
    for source in raw_sources:
        raw_path = Path(source["path"])
        if digest(raw_path) != source["sha256"]:
            raise ValueError("Original Landmark source changed")
        raw = json.loads(raw_path.read_text())
        split = raw[0]["split"]
        ep_path, gt_path = ce / split / f"{split}_guide.json.gz", ce / split / f"{split}_guide_gt.json.gz"
        before = {str(p): digest(p) for p in [raw_path, ep_path, gt_path]}
        with gzip.open(ep_path, "rt") as stream:
            episodes = json.load(stream)["episodes"]
        lookup = {}
        for ep in episodes:
            key = canonical_id(ep["instruction"]["instruction_id"])
            if key in lookup:
                raise ValueError("Ambiguous instruction ID in split")
            lookup[key] = ep
        del episodes
        with gzip.open(gt_path, "rt") as stream:
            gt = json.load(stream)
        for item in raw:
            key = f"{split}:{canonical_id(item['instruction_id'])}"
            row = {"task_key": key, "split": split, "scene": item["scan"], "path_id": canonical_id(item["path_id"]),
                   "source_record_sha256": content_digest(item), "source_path_occurrences": len(item["path"]),
                   "landmark_subinstructions": len(item["sub_instructions"]),
                   "historical_replay_status": historical_index.get(key, {}).get("status", "NOT_IN_HISTORICAL_192"),
                   "current_motion_acceptance": "NOT_TESTED_BY_ASSET_AUDIT"}
            ep = lookup.get(canonical_id(item["instruction_id"]))
            if ep is None:
                row.update(status="NO_MATCHED_CONTINUOUS_EPISODE", cause="absent_in_checked_CE_identity_not_physical_unreachability")
            else:
                if (Path(ep["scene_id"]).parent.name != item["scan"]
                        or canonical_id(ep["trajectory_id"]) != canonical_id(item["path_id"])
                        or ep["instruction"]["language"] != item["language"]
                        or len(ep["reference_path"]) != len(item["path"])):
                    raise ValueError("Official reference/source identity mismatch")
                eid = canonical_id(ep["episode_id"])
                demonstration = gt.get(eid)
                ep_identity = source_identity(ep)
                row.update(ce_episode_id=eid, episode_sha256=ep_identity["sha256"],
                           episode_fingerprint_encoding=ep_identity["encoding"],
                           source_nonfinite_fields=ep_identity["nonfinite_fields"],
                           reference_sha256=content_digest(ep["reference_path"]),
                           reference_occurrences=len(ep["reference_path"]),
                           source_viewpoint_reference_binding="same_source_path_id_and_preserved_sequence_index_not_spatial_nearest",
                           start_rotation_xyzw=ep["start_rotation"],
                           initial_equals_first_reference=ep["start_position"] == ep["reference_path"][0])
                if demonstration is None:
                    row["status"] = "MATCHED_EPISODE_MISSING_GT"
                else:
                    inspected = inspect_demonstration(demonstration, ep["start_position"])
                    gt_identity = source_identity(demonstration)
                    row.update(inspected, gt_sha256=gt_identity["sha256"], gt_nonfinite_fields=gt_identity["nonfinite_fields"],
                               status="OFFICIAL_ASSET_SCHEMA_READY_NOT_MOTION" if not inspected["errors"] else "OFFICIAL_ASSET_SCHEMA_UNRESOLVED")
            distributions[row["status"]] += 1
            records.append(row)
        for path, sha in before.items():
            if digest(path) != sha:
                raise ValueError("Source changed during read-only audit")
            source_rows.append({"path": path, "sha256": sha})
        del gt, lookup, raw
    if len(records) != config["expected_records"] or len({r["task_key"] for r in records}) != len(records):
        raise ValueError("Denominator mismatch")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "all33954-continuous-assets.json", records)
    errors = Counter(e for row in records for e in row.get("errors", []))
    summary = {"status": "FULL_ASSET_ACCOUNTING_NOT_MOTION_ACCEPTANCE", "records": len(records),
               "counts": dict(distributions), "schema_errors": dict(errors),
               "records_with_source_nonfinite_fields": sum(bool(r.get("source_nonfinite_fields")) for r in records),
               "records_with_nonfinite_fields_outside_timing_metadata": sum(any(not f["path"].startswith(".instruction.timed_instruction[") for f in r.get("source_nonfinite_fields", [])) for r in records),
               "max_initial_location_error_m": max((r["initial_location_error_m"] for r in records if r.get("initial_location_error_m") is not None), default=None),
               "historical_replay_counts": dict(Counter(r["historical_replay_status"] for r in records)),
               "sources": source_rows, "source_identity_receipt_sha256": digest(old_receipt),
               "historical_replay_summary_sha256": digest(root / config["historical_action_replay_summary"]),
               "ledger_sha256": digest(output / "all33954-continuous-assets.json"),
               "limits": "GT location indices follow forward actions only; turning intermediate poses are absent. Official RxR body/sliding differ from current research. No action equivalence, collision clearance, source ID rename or missing-CE reason inferred."}
    write_json(output / "validation.json", summary)
    return summary
