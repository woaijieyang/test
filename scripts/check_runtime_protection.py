"""Exercise real launcher permissions in an owned fixture; never write to global assets."""

import argparse, json, shutil, subprocess
from workspace import ROOT, owned, atomic_json
from evaluate import source_identity

PROBE = r"""
import json,os,sys
from pathlib import Path
root=Path.cwd();mode=sys.argv[1]
assert (root/'models/awarevln/config.json').read_bytes()
with (root/'data/datasets/R2R_VLNCE_v1-3_preprocessed/val_unseen/val_unseen.json.gz').open('rb') as f:assert f.read(16)
checks=[('outputs',True),('src',False),('results-show',mode=='results'),('configs/locks',mode=='configs'),('configs/diagnostics',mode=='configs')]
rows=[]
for directory,expected in checks:
 p=root/directory/(mode+'-probe.txt')
 try:p.write_text('owned protection fixture');actual=True
 except PermissionError:actual=False
 assert actual==expected,(directory,expected,actual)
 rows.append({'directory':directory,'write_allowed':actual})
print(json.dumps({'mode':mode,'protection':json.loads(os.environ['CASE1_PROTECTION']),'checks':rows,'global_reads_passed':True,'global_writes_attempted':False}))
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    a = p.parse_args()
    output = owned(a.output)
    fixture = output.parent / (output.stem + "-fixture")
    if output.exists() or fixture.exists():
        raise ValueError("Choose a new immutable protection test location")
    for name in (
        "scripts",
        "src",
        "outputs",
        "results-show",
        "configs/locks",
        "configs/diagnostics",
    ):
        (fixture / name).mkdir(parents=True, exist_ok=True)
    for name in (
        "workspace.py",
        "setup_data_links.py",
        "landlock.py",
        "runtime_exec.py",
        "with_runtime.sh",
    ):
        shutil.copy2(ROOT / "scripts" / name, fixture / "scripts" / name)
    subprocess.run(
        ["/usr/bin/python3", "-B", str(fixture / "scripts/setup_data_links.py")],
        check=True,
        capture_output=True,
        text=True,
    )
    records = []
    for mode, flag in [
        ("runtime", []),
        ("results", ["--results-write"]),
        ("configs", ["--prepare-configs"]),
    ]:
        r = subprocess.run(
            [
                "bash",
                str(fixture / "scripts/with_runtime.sh"),
                *flag,
                "/usr/bin/python3",
                "-B",
                "-c",
                PROBE,
                mode,
            ],
            capture_output=True,
            text=True,
        )
        (fixture / (mode + ".log")).write_text(r.stdout + r.stderr)
        if r.returncode:
            raise RuntimeError(
                "Protection mode failed: " + mode + "; see " + str(fixture / (mode + ".log"))
            )
        records.append(json.loads(r.stdout))
    sha, _ = source_identity()
    atomic_json(
        output,
        {
            "status": "PASS",
            "method": "kernel_protection_modes_v1",
            "source_sha256": sha,
            "modes": records,
            "scope": "Real kernel/launcher permission checks in an owned fixture; no model or navigation",
        },
    )
    print({"status": "PASS", "modes": len(records)})


if __name__ == "__main__":
    main()
