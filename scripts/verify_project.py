"""Check publication boundaries and local documentation references; no staging/push."""

import argparse, json, re, shutil, subprocess, tempfile
from pathlib import Path
from workspace import ROOT, atomic_json, read_json, digest

IGNORED = [
    "backup/old.md",
    "upstream/vendor.py",
    "runtime/env/bin/python",
    "data/datasets/x.json",
    "models/weights.bin",
    "outputs/run/result.jsonl",
    "logs/a.log",
    ".cache/tmp.bin",
    ".codegraph/graph.db",
    ".rebuild/private.py",
    ".env",
    "configs/local/machine.json",
    "credentials-test.json",
    "model.safetensors",
]
TRACKED = [
    "src/example.py",
    "configs/evaluation.yaml",
    "configs/locks/python-freeze.txt",
    "scripts/evaluate.py",
    "tests/test_results.py",
    "docs/results/records.json",
    "docs/results/model_results.md",
    "docs/zx/AGENTS.md",
    ".env.example",
    "LICENSE",
]


def check_ignore():
    (ROOT / ".cache").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / ".cache", prefix="gitignore-check-") as temp:
        p = Path(temp)
        shutil.copy2(ROOT / ".gitignore", p / ".gitignore")
        subprocess.run(["git", "init", "--quiet", str(p)], check=True)
        result = subprocess.run(
            ["git", "-C", str(p), "check-ignore", "--stdin"],
            input="\n".join(IGNORED + TRACKED) + "\n",
            text=True,
            capture_output=True,
        )
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr)
        ignored = set(result.stdout.splitlines())
        if not set(IGNORED) <= ignored or set(TRACKED) & ignored:
            raise ValueError("Incorrect .gitignore boundary")
    return {"ignored_cases": len(IGNORED), "tracked_cases": len(TRACKED)}


def doc_links():
    errors = []
    checked = 0
    for p in [ROOT / "README.md", *list((ROOT / "docs").rglob("*.md"))]:
        content = p.read_text(encoding="utf-8")
        for raw in re.findall(r"\]\(([^\n)]+)\)", content):
            value = raw.strip("<>").split("#", 1)[0]
            if not value or re.match(r"^[a-z]+:", value):
                continue
            target = (p.parent / value).resolve()
            if ROOT not in target.parents or not target.exists():
                errors.append({"document": str(p.relative_to(ROOT)), "target": value})
            checked += 1
    if errors:
        raise ValueError("Broken or escaping doc links: " + json.dumps(errors))
    return checked


def source_provenance(required=False):
    path = ROOT / "configs/source-import.json"
    if not path.exists():
        if required:
            raise ValueError("Source import ledger is missing")
        return {"status": "NOT_IMPORTED"}
    source = read_json(path)
    patch_path = ROOT / "configs/source-patches.json"
    patches = (
        {r["path"]: r["after_sha256"] for r in read_json(patch_path)} if patch_path.exists() else {}
    )
    for item in source["files"]:
        target = ROOT / item["target"]
        expected = patches.get(item["target"], item["installed_sha256"])
        if not target.is_file() or digest(target) != expected:
            raise ValueError("Unrecorded source import/patch drift: " + item["target"])
    if digest(ROOT / "pyproject.toml") != source["pyproject_installed_sha256"]:
        raise ValueError("Unrecorded dependency-declaration drift")
    return {
        "status": "PASS",
        "imported_files": len(source["files"]),
        "patched_files": len(patches),
        "upstream_commit": source["commit"],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="outputs/verification/project.json")
    p.add_argument("--require-source", action="store_true")
    a = p.parse_args()
    result = {
        "gitignore": check_ignore(),
        "local_doc_links": doc_links(),
        "source_provenance": source_provenance(a.require_source),
        "status": "PASS",
        "scope": "Source provenance, ignore rules and document references; not navigation or publication approval",
    }
    atomic_json(a.output, result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
