"""Save actual unittest counts and source identity; skips cannot satisfy release gate."""

import argparse, unittest
from workspace import ROOT, owned, atomic_json, digest
from evaluate import source_identity

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="outputs/verification/cpu.json")
    a = p.parse_args()
    target = owned(a.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.with_suffix(".log").exists():
        raise SystemExit("Choose a new check receipt path; prior attempts are immutable")
    with target.with_suffix(".log").open("w") as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(
            unittest.defaultTestLoader.discover(str(ROOT / "tests"))
        )
    sha, _ = source_identity()
    passed = result.wasSuccessful() and not result.skipped
    atomic_json(
        target,
        {
            "status": "PASS" if passed else "FAIL",
            "source_sha256": sha,
            "tests": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skips": len(result.skipped),
            "claim_scope": "CPU tests only",
            "test_files": [
                {"path": str(p), "sha256": digest(p)} for p in sorted((ROOT / "tests").glob("*.py"))
            ],
        },
    )
    if not passed:
        raise SystemExit("CPU checks failed or skipped")
    print({"status": "PASS", "tests": result.testsRun})
