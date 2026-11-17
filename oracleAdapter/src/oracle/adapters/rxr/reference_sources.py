"""Acquire absent public Guide references once, without touching shared assets."""
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request
from urllib.parse import urlparse


def fetch(case_root, config, output):
    root, output = Path(case_root).resolve(), Path(output).resolve()
    if not output.is_relative_to(root / "outputs/oracleAdapter") or output.exists():
        raise ValueError("Immutable owned acquisition run required")
    output.mkdir(parents=True)
    cache = (root / config["cache_relative_path"]).resolve()
    if not cache.is_relative_to(root / "outputs/oracleAdapter/reference-cache"):
        raise ValueError("Reference cache escaped owned output area")
    cache.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    records, total = [], 0
    for item in config["files"]:
        url = item["url"]
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "storage.googleapis.com" or not parsed.path.startswith("/rxr-data/"):
            raise ValueError("Unexpected public source host")
        path = cache / Path(parsed.path).name
        metadata = path.with_suffix(path.suffix + ".receipt.json")
        reused = False
        if metadata.exists():
            row = json.loads(metadata.read_text())
            if row["url"] != url or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                raise RuntimeError("Existing immutable source identity mismatch")
            if item.get("expected_sha256") and row["sha256"] != item["expected_sha256"]:
                raise RuntimeError("Cached source differs from public source lock")
            reused = True
        else:
            if path.exists():
                raise RuntimeError("Unreceipted source file; preserve and investigate")
            partial = cache / (path.name + ".partial-" + output.name)
            sha, md5, count = hashlib.sha256(), hashlib.md5(), 0
            request_url = url + "?generation=" + str(item["generation"]) if item.get("generation") else url
            request = urllib.request.Request(request_url, headers={"User-Agent": "Case1-OracleAdapter-SourceAudit", "Accept-Encoding": "identity"})
            with urllib.request.urlopen(request, timeout=config["socket_timeout_seconds"]) as response, partial.open("xb") as stream:
                headers = response.headers
                expected = int(headers["Content-Length"])
                if expected > config["maximum_file_bytes"]:
                    raise RuntimeError("Source exceeds declared byte budget")
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > config["maximum_file_bytes"] or total + count > config["maximum_total_bytes"] or time.perf_counter() - started > config["wall_seconds"]:
                        raise RuntimeError("Predeclared acquisition budget exhausted")
                    stream.write(chunk)
                    sha.update(chunk)
                    md5.update(chunk)
                if count != expected:
                    raise RuntimeError("Incomplete public source transfer")
                if item.get("expected_bytes") is not None and count != item["expected_bytes"]:
                    raise RuntimeError("Source size differs from public source lock")
                if item.get("expected_sha256") and sha.hexdigest() != item["expected_sha256"]:
                    raise RuntimeError("Source content differs from public source lock")
                etag = headers.get("ETag", "").strip('"')
                if re.fullmatch(r"[0-9a-fA-F]{32}", etag) and md5.hexdigest().lower() != etag.lower():
                    raise RuntimeError("Provider ETag/MD5 mismatch")
                row = {"split": item["split"], "role": "guide", "url": url, "request_url": request_url,
                       "bytes": count, "sha256": sha.hexdigest(), "md5": md5.hexdigest(),
                       "etag": etag, "last_modified": headers.get("Last-Modified"),
                       "generation": headers.get("x-goog-generation"), "path": str(path)}
            with partial.open("rb") as stream:
                if stream.read(2) != b"\x1f\x8b":
                    raise RuntimeError("Expected original gzip data, not an HTML/auth response")
            partial.rename(path)
            metadata.write_text(json.dumps(row, indent=2))
            path.chmod(0o444)
        total += row["bytes"]
        records.append({**row, "reused": reused})
        (output / "state.json").write_text(json.dumps({"status": "ACQUIRING_OFFICIAL_REFERENCES", "completed_files": len(records), "total_bytes": total}, indent=2))
    result = {"status": "OFFICIAL_GUIDE_BYTES_FROZEN_NOT_YET_IDENTITY_MATCHED", "files": records,
              "bytes": total, "wall_seconds": time.perf_counter() - started,
              "downloaded_bytes": sum(r["bytes"] for r in records if not r["reused"]),
              "reused_files": sum(r["reused"] for r in records),
              "shared_data_modified": False, "dataset_semantic_version": "NOT_INFERRED_FROM_DOWNLOAD_DATE",
              "limits": "Canonical shared annotation directories lacked these raw Guide jsonl files. Existing CE/scene assets are reused unchanged. HTTP generation, ETag and content SHA are source identity; no assertion of historical conversion/filter reasons."}
    (output / "validation.json").write_text(json.dumps(result, indent=2))
    (output / "state.json").write_text(json.dumps({"status": result["status"], "completed_files": len(records), "total_bytes": total}, indent=2))
    return result
