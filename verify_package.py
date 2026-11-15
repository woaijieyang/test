"""Verify the final-best-v1 source tree against FILE_HASHES.json."""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "FILE_HASHES.json"
REQUIRED = [
    "README.md", "WORKFLOW.md", "IMPLEMENTATION.md", "CODEX_START_HERE.md",
    "generator/prompt.md", "generator/repair.md", "generator/output.schema.json",
    "reviewer/prompt.md", "reviewer/checklist.md", "reviewer/output.schema.json",
    "adapter/source.py", "adapter/profiles.json", "renderer/freeze.py",
    "host/run.py", "host/protocol.py", "host/README.md", "shared/semantic_contract.md",
    "generator/repair.schema.json", "tests/test_runtime_contract_v2.py",
    "templates/01.json", "templates/15.json", "tests/test_patch.py",
    "tests/test_final_best_contract.py", "validation.json",
]

def main() -> int:
    if not MANIFEST.is_file():
        print(json.dumps({"ok": False, "error": "FILE_HASHES.json is missing"}, indent=2))
        return 1
    hashes = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(hashes, dict):
        print(json.dumps({"ok": False, "error": "hash manifest must be a JSON object"}, indent=2))
        return 1
    actual = {
        p.relative_to(ROOT).as_posix()
        for p in ROOT.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        and p.relative_to(ROOT).as_posix() != "FILE_HASHES.json"
    }
    expected = set(hashes)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    mismatched = []
    algorithms = {"sha256": 0, "gitblob-sha1": 0}
    for rel in sorted(expected & actual):
        data = (ROOT / rel).read_bytes()
        recorded = hashes[rel]
        if isinstance(recorded, str) and recorded.startswith("gitblob-sha1:"):
            algorithms["gitblob-sha1"] += 1
            git_header = f"blob {len(data)}\0".encode("ascii")
            got = hashlib.sha1(git_header + data).hexdigest()
            wanted = recorded.split(":", 1)[1]
        else:
            algorithms["sha256"] += 1
            wanted = recorded.split(":", 1)[1] if isinstance(recorded, str) and recorded.startswith("sha256:") else recorded
            got = hashlib.sha256(data).hexdigest()
        if got != wanted:
            mismatched.append(rel)
    required_missing = [rel for rel in REQUIRED if not (ROOT / rel).is_file()]
    ok = not (missing or extra or mismatched or required_missing)
    print(json.dumps({
        "ok": ok,
        "algorithm": "sha256 + Git blob SHA-1",
        "manifest_entries": len(expected),
        "actual_files": len(actual),
        "hash_algorithms": algorithms,
        "missing": missing,
        "extra": extra,
        "hash_mismatches": mismatched,
        "required_missing": required_missing,
    }, ensure_ascii=False, indent=2))
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
