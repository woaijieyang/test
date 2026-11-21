"""Prove that committed teaching and compiler inputs rebuild deterministically.

This checks file bytes, not model semantics. Generated templates, prompt outputs
and renderer smoke results must have been built once before running this check.
The build must never rewrite runtime source, tests, or unrelated assets.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def snapshot():
    return {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(ROOT.rglob('*'))
        if p.is_file() and '.git' not in p.parts and '__pycache__' not in p.parts
        and p.suffix != '.pyc'
    }


def main():
    before = snapshot()
    commands = [
        [sys.executable, '-B', str(ROOT / 'tools/build_rxr_teaching.py')],
        [sys.executable, '-B', '-m', 'host.compile'],
        [sys.executable, '-B', '-m', 'evaluation.smoke24'],
    ]
    for command in commands:
        subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    after = snapshot()
    changed = sorted(path for path in before.keys() | after.keys()
                     if before.get(path) != after.get(path))
    if changed:
        raise RuntimeError('Non-reproducible rebuild changed files: ' + ', '.join(changed))
    print(json.dumps({'deterministic_rebuild': True, 'files_compared': len(before),
                      'source_and_tests_unchanged': True}))


if __name__ == '__main__':
    main()
