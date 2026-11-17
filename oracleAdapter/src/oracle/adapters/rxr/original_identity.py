"""Stable-ID comparison of Landmark and frozen original Guide references."""
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from oracle.adapters.landmark_rxr.ledger import canonical_id, digest


def text_fingerprint(text, boundary_normalization=False):
    if not isinstance(text, str):
        raise ValueError("Unexpected instruction format")
    if boundary_normalization:
        text = " ".join(text.split())
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
            text = " ".join(text[1:-1].split())
    return hashlib.sha256(text.encode()).hexdigest()


def audit(case_root, config, output):
    root, output = Path(case_root).resolve(), Path(output).resolve()
    if not output.is_relative_to(root / "outputs/oracleAdapter") or output.exists():
        raise ValueError("Fresh owned output required")
    base = root / config["identity_run"]
    baseline = json.loads((base / "validation.json").read_text())
    identities = json.loads((base / "all33954-identities.json").read_text())
    wanted = {r["instruction_id"] for r in identities}
    if len(identities) != 33954 or len(wanted) != 33954:
        raise ValueError("Unexpected Landmark identity uniqueness")
    source_receipt = root / config["raw_guide_source_receipt"]
    raw_sources = json.loads(source_receipt.read_text())
    if raw_sources["status"] != "OFFICIAL_GUIDE_BYTES_FROZEN_NOT_YET_IDENTITY_MATCHED":
        raise ValueError("Raw Guide acquisition not validated")
    raw_index = defaultdict(list)
    source_total, source_roles = 0, Counter()
    for source in raw_sources["files"]:
        path = Path(source["path"]).resolve()
        if not path.is_relative_to(root / "outputs/oracleAdapter/reference-cache") or digest(path) != source["sha256"]:
            raise ValueError("Raw reference bytes changed or escaped cache")
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                raw = json.loads(line)
                source_total += 1
                source_roles[raw["language"]] += 1
                iid = canonical_id(raw["instruction_id"])
                if iid not in wanted:
                    continue
                raw_index[iid].append({"instruction_id": iid, "path_id": canonical_id(raw["path_id"]),
                                       "scene": raw["scan"], "split": raw["split"], "language": raw["language"],
                                       "path": raw["path"], "text_sha256": text_fingerprint(raw["instruction"]),
                                       "boundary_normalized_text_sha256": text_fingerprint(raw["instruction"], True),
                                       "source_sha256": source["sha256"], "source_path": str(path),
                                       "source_line": line_number,
                                       "decoded_line_sha256": hashlib.sha256(line.encode()).hexdigest(),
                                       "source_generation": source.get("generation"),
                                       "instruction_id_source_type": type(raw["instruction_id"]).__name__})
    ce = {r["task_key"]: r for r in identities}
    rows = []
    for source in baseline["sources"]:
        path = Path(source["path"])
        if not path.name.startswith("LandmarkRxR_"):
            continue
        if digest(path) != source["sha256"]:
            raise ValueError("Original Landmark data changed")
        for raw in json.loads(path.read_text()):
            iid = canonical_id(raw["instruction_id"])
            key = raw["split"] + ":" + iid
            candidates = raw_index[iid]
            row = {"task_key": key, "instruction_id": iid, "path_id": canonical_id(raw["path_id"]),
                   "scene": raw["scan"], "language": raw["language"], "ce_status": ce[key]["status"],
                   "original_guide_candidates": candidates, "identity_inferred_from_text": False,
                   "historical_CE_exclusion_reason": "UNKNOWN_NOT_PROVIDED"}
            if len(candidates) != 1:
                row["status"] = "RAW_GUIDE_ID_ABSENT" if not candidates else "AMBIGUOUS_RAW_GUIDE_ID"
            else:
                original = candidates[0]
                compared = {"scene_equal": original["scene"] == raw["scan"],
                            "split_equal": original["split"] == raw["split"],
                            "language_equal": original["language"] == raw["language"],
                            "path_id_equal": original["path_id"] == canonical_id(raw["path_id"]),
                            "ordered_path_equal": original["path"] == raw["path"],
                            "instruction_bytes_equal": original["text_sha256"] == text_fingerprint(raw["instruction"]),
                            "instruction_boundary_normalized_equal": original["boundary_normalized_text_sha256"] == text_fingerprint(raw["instruction"], True)}
                row["comparison"] = compared
                required = ["scene_equal", "split_equal", "language_equal", "path_id_equal", "ordered_path_equal"]
                row["status"] = "EXACT_ORIGINAL_GUIDE_ID_AND_ORDERED_PATH" if all(compared[k] for k in required) else "ORIGINAL_ID_WITH_SOURCE_FIELD_DIFFERENCES"
            rows.append(row)
    if len(rows) != 33954 or {r["task_key"] for r in rows} != set(ce):
        raise RuntimeError("Raw-source comparison coverage mismatch")
    missing = [r for r in rows if r["ce_status"] == "NO_EXACT_CE_GUIDE_IDENTITY"]
    if len(missing) != 8034:
        raise RuntimeError("Original unmatched denominator changed")
    output.mkdir(parents=True)
    (output / "all33954.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    (output / "unmatched8034.json").write_text(json.dumps(missing, ensure_ascii=False, indent=2))
    comparisons = [r["comparison"] for r in rows if "comparison" in r]
    summary = {"status": "ORIGINAL_GUIDE_PROVENANCE_COMPARED_NOT_CONTINUOUS_PATH_REPAIR", "records": len(rows),
               "raw_guide_records_read": source_total, "raw_language_counts": dict(source_roles),
               "match_counts": dict(Counter(r["status"] for r in rows)),
               "field_disagreement_counts": {k: sum(not r[k] for r in comparisons) for k in comparisons[0]} if comparisons else {},
               "unmatched8034_original_status": dict(Counter(r["status"] for r in missing)),
               "raw_source_receipt_sha256": digest(source_receipt),
               "identity_baseline_sha256": digest(base / "validation.json"),
               "record_files": {n: digest(output / n) for n in ["all33954.json", "unmatched8034.json"]},
               "limits": "Original Guide presence/field agreement does not supply missing Habitat continuous trajectories or author exclusion reasons. Source text differences are recorded, never used to substitute identity. No original annotations, geometry, model or acceptance standard changed."}
    (output / "validation.json").write_text(json.dumps(summary, indent=2))
    return summary
