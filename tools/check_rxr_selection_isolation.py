"""Prove teaching corrections do not alter source-based RxR selection.

Runs old and current modules in independent processes. The measured grid covers
all active source texts and explicit/default per-task counts, not unseen texts or
navigation behavior. No evaluation outcomes enter the selector or model inputs.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = 'da277a0f9a6ee7d8eebb78dafa852e469cd1a50e'
PROGRAM = r'''
import hashlib, json
from host.compile import core_library
from host.template_selector import library, source, select_examples
inventory = {}
texts = {'', 'If the door is closed, turn left.', 'Stand beside the news stand, then turn right.',
         'Return through the same door. Do not move once you are outside.'}
for role in ('generator', 'reviewer'):
    for kind, rows in [('core', core_library(role, 'rxr-en-us')), ('dynamic', library(role, 'rxr-en-us'))]:
        inventory[role + '/' + kind] = [dict(
            template_id=r['template_id'], source=source(r), source_identity=r.get('source'),
            retrieval_tags=r.get('retrieval_tags', []), pair_id=r.get('pair_id')) for r in rows]
        texts.update(source(r) for r in rows)
selected = {}
for text in sorted(texts):
    choices = {}
    for count in (None, 2, 3, 4):
        for role in ('generator', 'reviewer'):
            choices[role + '/' + str(count)] = select_examples(role, 'rxr-en-us', text, count=count)
    selected[hashlib.sha256(text.encode()).hexdigest()] = choices
print(json.dumps(dict(inventory=inventory, selected=selected), sort_keys=True))
'''


def snapshot(root):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONHASHSEED='0')
    proc = subprocess.run([sys.executable, '-B', '-c', PROGRAM], cwd=root, env=env,
                          check=True, capture_output=True, text=True, timeout=240)
    return json.loads(proc.stdout)


@contextmanager
def frozen_checkout():
    existing = os.environ.get('R2R_BASELINE_DIR')
    if existing:
        path = Path(existing)
        sha = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        if sha != BASE:
            raise ValueError('Baseline environment points to a different source commit')
        yield path
        return
    # A local test run needs the immutable source object, not a network fetch.
    archive = subprocess.check_output(['git', 'archive', '--format=tar', BASE], cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix='rxr-source-') as temp:
        path = Path(temp)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for item in tar:
                rel = PurePosixPath(item.name)
                if rel.is_absolute() or '..' in rel.parts or item.issym() or item.islnk():
                    raise ValueError('Unsafe archive member')
                target = path.joinpath(*rel.parts)
                if item.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif item.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    stream = tar.extractfile(item)
                    if stream is None:
                        raise ValueError('Unreadable archive member')
                    target.write_bytes(stream.read())
                else:
                    raise ValueError('Unsupported archive member')
        yield path


def compare(baseline, current=ROOT):
    before, after = snapshot(baseline), snapshot(current)
    if before['inventory'] != after['inventory']:
        raise ValueError('Source text, order, identity, tags or pair mapping changed')
    if before['selected'] != after['selected']:
        changes = [k for k in sorted(set(before['selected']) | set(after['selected']))
                   if before['selected'].get(k) != after['selected'].get(k)]
        raise ValueError('Unapproved RxR selection drift: ' + json.dumps(changes))
    return dict(inputs_compared=len(before['selected']), count_configurations=4,
                roles_per_configuration=2, source_identity_and_order_equal=True,
                exact_selection_equal=True, navigation_evaluated=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--current', type=Path, default=ROOT)
    args = parser.parse_args()
    if args.baseline:
        report = compare(args.baseline, args.current)
    else:
        with frozen_checkout() as baseline:
            report = compare(baseline, args.current)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
