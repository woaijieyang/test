"""Read-only preservation checks for the scoped RxR refinement."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = 'b69e04ddc7097b47f8d201beed2fa5e2d9ffd34e'
SOURCE_BASE = '33d66756de8d545db001f3854194bf5d5b5a8592'
PROTECTED = ['shared', 'adapter', 'renderer', 'host/protocol.py',
             'host/template_selector.py', 'host/rxr_retrieval.py', 'host/rxr_assets.py',
             'generator/prompt.md', 'generator/acceptance.md', 'generator/repair.md',
             'generator/repair_examples.json', 'generator/output.schema.json', 'generator/repair.schema.json',
             'reviewer/prompt.md', 'reviewer/checklist.md', 'reviewer/output.schema.json',
             'generator/dataset_rules/r2r_en.md', 'reviewer/dataset_rules/r2r_en.md',
             'generator/templates/R2R', 'reviewer/templates/R2R']


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def check_protected():
    changed = git('diff', '--name-only', SOURCE_BASE, '--', *PROTECTED).decode().strip()
    if changed:
        raise ValueError('Imported common/R2R source differs from requested migration source: ' + changed)
    folders = ['generator/templates/RxR', 'reviewer/templates/RxR']
    files = [p for p in git('ls-tree', '-r', '--name-only', BASE, '--', *folders).decode().splitlines()
             if p.endswith('.json')]
    present = {p.relative_to(ROOT).as_posix() for folder in folders for p in (ROOT / folder).rglob('*.json')}
    if set(files) != present:
        raise ValueError('RxR teaching inventory changed')
    changed_templates = []
    legacy_count = 0
    for path in files:
        if "/legacy/" in path:
            if (ROOT / path).read_bytes() != git("show", BASE + ":" + path):
                raise ValueError("Historical RxR provenance changed: " + path)
            legacy_count += 1
            continue
        old = json.loads(git('show', BASE + ':' + path))
        current = json.loads((ROOT / path).read_bytes())
        for key in ('template_id', 'role', 'dataset_scope', 'language', 'source', 'input',
                    'review_input', 'pair_id', 'retrieval_tags', 'decision', 'provenance'):
            if current.get(key) != old.get(key):
                raise ValueError('Protected RxR source/route/selection identity changed: ' + path + '/' + key)
        if current['role'] == 'generator':
            for key in ('status', 'subtasks', 'issues'):
                if current['output'][key] != old['output'][key]:
                    raise ValueError('Executable Generator output changed: ' + path + '/' + key)
        if current != old:
            raise ValueError('Retained RxR teaching bytes changed: ' + path)
    return dict(baseline_commit=BASE, source_baseline_commit=SOURCE_BASE, protected_assets_equal=True,
                rxr_sources_candidates_and_retrieval_fields_equal=True,
                rxr_templates_checked=len(files) - legacy_count,
                legacy_templates_checked=legacy_count, changed_template_ids=sorted(changed_templates))


if __name__ == '__main__':
    print(json.dumps(check_protected(), indent=2))
