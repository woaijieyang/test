"""Mapping-only counterfactual; original data and route objectives unchanged."""
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from .occurrences import align_subpaths, align_with_source_connectors
from .ledger import canonical_id, digest


def audit(case_root, config, output):
    root, output = Path(case_root).resolve(), Path(output).resolve()
    if not output.is_relative_to(root / "outputs/oracleAdapter") or output.exists():
        raise ValueError("New owned immutable output required")
    baseline = root / config["identity_run"]
    receipt = json.loads((baseline / "validation.json").read_text())
    if receipt["records"] != 33954:
        raise ValueError("Wrong baseline denominator")
    baseline_order = json.loads((baseline / "source-subpath-occurrences.json").read_text())
    expected = {r["task_key"]: r for r in baseline_order}
    records, changes = [], []
    for item in receipt["sources"]:
        if not Path(item["path"]).name.startswith("LandmarkRxR_"):
            continue
        source = Path(item["path"]).resolve()
        if not source.is_relative_to(root.parent / "data/raw_data/landmark-rxr") or digest(source) != item["sha256"]:
            raise ValueError("Original Landmark source changed")
        for raw in json.loads(source.read_text()):
            key = raw["split"] + ":" + canonical_id(raw["instruction_id"])
            before = align_subpaths(raw["path"], raw["sub_paths"])
            after = align_with_source_connectors(raw["path"], raw["sub_paths"])
            if before.status != expected[key]["status"]:
                raise RuntimeError("Original mapping control changed")
            if len(raw["sub_paths"]) != len(raw["sub_instructions"]):
                raise ValueError("Subinstruction boundaries cannot disappear")
            if before.status == "EXACT_ORDERED_OCCURRENCES" and after != before:
                raise RuntimeError("Previously exact occurrence assignment regressed")
            row = {"task_key": key, "scene": raw["scan"], "source_sha256": item["sha256"],
                   "before_status": before.status, "after": asdict(after),
                   "source_record_sha256": hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                   "subinstruction_count": len(raw["sub_instructions"])}
            records.append(row)
            if after != before:
                changes.append({**row, "full_source_path": raw["path"],
                                "source_subpaths": raw["sub_paths"],
                                "connector_node_sequences": [raw["path"][a:b + 1] for a, b in after.connectors],
                                "new_coordinates_or_identities_invented": False,
                                "native_execution_proved": False})
    if len(records) != 33954 or len({r["task_key"] for r in records}) != 33954 or {r["task_key"] for r in records} != set(expected):
        raise ValueError("Coverage mismatch")
    output.mkdir(parents=True)
    (output / "records33954.json").write_text(json.dumps(records, ensure_ascii=False, indent=2))
    (output / "changes.json").write_text(json.dumps(changes, ensure_ascii=False, indent=2))
    result = {"status": "SOURCE_ORDER_MAPPING_ACCOUNTED_NOT_MOTION_ACCEPTED", "records": len(records),
              "after_counts": dict(Counter(r["after"]["status"] for r in records)),
              "changed_records": len(changes), "original_exact_records_regressed": 0,
              "identity_baseline_sha256": digest(baseline / "validation.json"),
              "records_sha256": digest(output / "records33954.json"),
              "changes_sha256": digest(output / "changes.json"),
              "limits": "Explicit connectors follow existing full source path. They require actual continuous execution, preserve all subinstructions and do not authorize a reset, shortcut, original annotation edit, or route PASS."}
    (output / "validation.json").write_text(json.dumps(result, indent=2))
    return result
