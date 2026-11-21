"""Refresh approved asset pins only after immutable-baseline isolation proof."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def gitblob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def refresh_shared_runtime_pins():
    baseline = os.environ.get('R2R_BASELINE_DIR')
    if not baseline or not Path(baseline).is_dir():
        raise ValueError('R2R_BASELINE_DIR must name the immutable baseline checkout')
    subprocess.run([sys.executable, '-B', str(ROOT / 'tools/check_r2r_isolation.py'),
                    '--baseline', baseline, '--current', str(ROOT)], check=True)
    head = subprocess.check_output(['git', '-C', baseline, 'rev-parse', 'HEAD'], text=True).strip()
    if head != os.environ.get('BASE_COMMIT'):
        raise ValueError('The isolation checkout does not match BASE_COMMIT')
    path = ROOT / 'provenance/r2r_profile_integrity.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    approved = {'host/run.py', 'host/template_selector.py'}
    changes = []
    for row in value['files']:
        actual = gitblob((ROOT / row['path']).read_bytes())
        if actual == row['git_blob_sha1']:
            continue
        if row['path'] not in approved:
            raise ValueError('Unexpected protected asset drift: ' + row['path'])
        changes.append(dict(path=row['path'], previous_git_blob_sha1=row['git_blob_sha1'],
                            current_git_blob_sha1=actual))
        row['git_blob_sha1'] = actual
    if changes:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        audit = dict(baseline_commit=head, reason='RxR-only shared-runtime dispatch and source validation',
                     r2r_model_messages_and_schemas_equal=True, r2r_selections_equal=True,
                     protected_common_and_r2r_assets_equal=True, shared_runtime_changes=changes)
        (ROOT / 'provenance/r2r_shared_runtime_audit.json').write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    refresh_shared_runtime_pins()
    profile = ROOT / 'provenance/rxr_profile_integrity.json'
    value = json.loads(profile.read_text(encoding='utf-8'))
    paths = {row['path'] for row in value['files']}
    paths.update({'host/rxr_retrieval.py', 'host/rxr_assets.py', 'provenance/rxr_training_sources.json'})
    for role in ('generator', 'reviewer'):
        paths.update(p.relative_to(ROOT).as_posix()
                     for p in (ROOT / role / 'templates' / 'RxR' / 'train').glob('*.json'))
    value['files'] = [dict(path=p, git_blob_sha1=gitblob((ROOT / p).read_bytes())) for p in sorted(paths)]
    value['file_count'] = len(value['files'])
    profile.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    files = {}
    for path in sorted(ROOT.rglob('*')):
        if (not path.is_file() or '.git' in path.parts or '__pycache__' in path.parts
                or path.suffix == '.pyc' or path == ROOT / 'FILE_HASHES.json'):
            continue
        files[path.relative_to(ROOT).as_posix()] = 'gitblob-sha1:' + gitblob(path.read_bytes())
    (ROOT / 'FILE_HASHES.json').write_text(json.dumps(files, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'source_files': len(files), 'rxr_pinned_assets': len(paths)}))


if __name__ == '__main__':
    main()
