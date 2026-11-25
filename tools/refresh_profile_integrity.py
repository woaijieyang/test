"""Refresh derived combined-profile fingerprints after independent asset checks.

This is an explicit authoring command, not a runtime patcher. It never updates
prompt expectations, source rules or teaching assets. Normal target CI is read-only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_profile_integration import SOURCE, RXR_BASE, blob, check_static, tree

CHANGES = 'provenance/profile_integration_changes.json'
DERIVED = {'FILE_HASHES.json', CHANGES, 'provenance/profile_integration_validation.json',
           'provenance/profile_integration_checks.json'}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def package_paths():
    return {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*')
            if p.is_file() and '.git' not in p.parts and '__pycache__' not in p.parts
            and p.suffix != '.pyc' and p.relative_to(ROOT).as_posix() != 'FILE_HASHES.json'}


def desired_outputs():
    check_static()  # A hash refresh cannot authorize changed protected assets.
    pending = {}
    for profile in ('r2r', 'rxr'):
        name = f'provenance/{profile}_profile_integrity.json'
        data = json.loads((ROOT / name).read_bytes())
        for row in data['files']:
            path = ROOT / row['path']
            if not path.is_file():
                raise ValueError('Manifest asset absent: ' + row['path'])
            row['git_blob_sha1'] = blob(path.read_bytes())
        pending[name] = encoded(data)
    source, target = tree(SOURCE), tree(RXR_BASE)
    current = {name: blob(pending.get(name, (ROOT / name).read_bytes())) for name in package_paths()}
    changes = []
    for name in sorted((set(source) | set(target) | set(current)) - DERIVED):
        s, t, c = source.get(name), target.get(name), current.get(name)
        if s == t == c:
            continue
        disposition = ('removed_in_integrated_layout' if c is None else
                       'matches_requested_source' if c == s else
                       'retains_rxr_target' if c == t else
                       'new_integration_support' if s is None and t is None else
                       'explicit_profile_reconciliation')
        changes.append(dict(path=name, source_blob=s, previous_target_blob=t,
                            integrated_blob=c, disposition=disposition))
    pending[CHANGES] = encoded(dict(source_commit=SOURCE, retained_rxr_commit=RXR_BASE,
        basis='Complete current file comparison. Exact imported/retained protected assets and behavior are checked independently; these fingerprints do not certify semantic correctness.',
        excluded_derived_records=sorted(DERIVED), changes=changes))
    names = package_paths() | set(pending)
    pending['FILE_HASHES.json'] = encoded({name: 'gitblob-sha1:' + blob(
        pending[name] if name in pending else (ROOT / name).read_bytes()) for name in sorted(names)})
    return pending


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true', help='explicitly materialize derived fingerprints')
    args = parser.parse_args()
    tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0'))
    untracked = package_paths() - tracked - DERIVED
    if untracked:
        raise ValueError('Review/add source files before refreshing package hashes: ' + repr(sorted(untracked)))
    outputs = desired_outputs()
    changed = [name for name, data in outputs.items()
               if not (ROOT / name).is_file() or (ROOT / name).read_bytes() != data]
    if args.write:
        for name in changed:
            (ROOT / name).write_bytes(outputs[name])
    elif changed:
        raise ValueError('Derived profile fingerprints differ: ' + ', '.join(changed))
    print(json.dumps({'derived_files_changed': changed, 'write': args.write,
                      'prompt_expectations_rewritten': False, 'protected_assets_checked': True}))

if __name__ == '__main__':
    main()
