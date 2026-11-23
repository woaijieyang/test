"""Fail-closed provenance binding for the curated RxR training library.

This is an identity/integrity gate, not a semantic judge. Runtime performs no
network access and never reconstructs a missing or changed teaching artifact.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = 'provenance/rxr_training_sources.json'
TRAIN_DIRS = ('generator/templates/RxR/train', 'reviewer/templates/RxR/train')


def _digest(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('Invalid RxR digest: ' + label)
    return value


def _safe_path(root, name):
    if not isinstance(name, str):
        raise ValueError('RxR registry path must be a string')
    relative = Path(name)
    if (relative.is_absolute() or '..' in relative.parts or len(relative.parts) != 5
            or relative.parent.as_posix() not in TRAIN_DIRS or relative.suffix != '.json'
            or relative.as_posix() != name):
        raise ValueError('RxR registry path escapes its training directories')
    path = root / relative
    if any(p.is_symlink() for p in (path, *path.parents) if p != root and root in p.parents):
        raise ValueError('RxR training assets must not use symbolic links')
    return path


def _load_verified(root=None):
    root = (Path(root) if root is not None else ROOT).resolve()
    registry = root / REGISTRY
    if registry.is_symlink():
        raise ValueError('RxR training registry must not be a symbolic link')
    payload = json.loads(registry.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError('RxR training registry must be an object')
    records, assets = payload.get('records'), payload.get('templates')
    if not isinstance(records, list) or len(records) != 8:
        raise ValueError('RxR training registry must identify eight distinct verified source records')
    if (payload.get('source_split') != 'train' or payload.get('source_role') != 'guide'
            or payload.get('language') != 'en-US'):
        raise ValueError('RxR training registry has an unsupported source identity')
    archive = _digest(payload.get('archive_sha256'), 'archive')
    source_url = payload.get('source_url')
    if not isinstance(source_url, str) or not source_url.startswith('https://'):
        raise ValueError('RxR source URL must retain the declared HTTPS archive identity')
    if not isinstance(assets, list) or len(assets) != 24:
        raise ValueError('RxR training registry must pin exactly twenty-four authored templates')

    expected, ids = {}, set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('Invalid RxR source record')
        iid = record.get('instruction_id')
        if isinstance(iid, bool) or not isinstance(iid, (int, str)) or not str(iid).isdigit():
            raise ValueError('Invalid RxR instruction identity')
        iid = str(int(iid))
        if iid in ids:
            raise ValueError('Duplicate RxR training instruction identity')
        ids.add(iid)
        for key in ('source_sha256', 'source_record_sha256'):
            _digest(record.get(key), key)
        if not isinstance(record.get('scan'), str) or not record['scan'] or record.get('path_id') is None:
            raise ValueError('Incomplete RxR scan/path identity')
        for key, prefix, role in (('generator', 'RxR-GEN-TRAIN-', 'generator'),
                                  ('reviewer', 'RxR-REV-TRAIN-', 'reviewer'),
                                  ('diagnostic', 'RxR-DIAG-TRAIN-', 'reviewer')):
            tid = record.get(key)
            if not isinstance(tid, str) or not re.fullmatch(re.escape(prefix) + r'[a-z0-9]+(?:-[a-z0-9]+)*', tid):
                raise ValueError('Invalid RxR training template identity: ' + str(tid))
            if tid in expected:
                raise ValueError('Duplicate RxR training template identity: ' + tid)
            expected[tid] = (record, key, role)
    if len(expected) != 24:
        raise ValueError('RxR registry must bind three distinct templates to each source')

    paths, loaded = set(), {}
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError('Invalid RxR asset record')
        name = asset.get('path')
        path = _safe_path(root, name)
        if name in paths:
            raise ValueError('Duplicate RxR training asset path')
        paths.add(name)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != _digest(asset.get('sha256'), name):
            raise ValueError('RxR training asset changed: ' + name)
        row = json.loads(data)
        if not isinstance(row, dict) or row.get('template_id') not in expected:
            raise ValueError('Unregistered RxR training template: ' + name)
        tid = row['template_id']
        if tid in loaded:
            raise ValueError('Duplicate RxR template content identity: ' + tid)
        record, key, role = expected[tid]
        if name != f'{role}/templates/RxR/train/{tid}.json':
            raise ValueError('RxR asset filename/role does not match its identity: ' + tid)
        source, provenance = row.get('source', {}), row.get('provenance', {})
        body = row.get('input') if role == 'generator' else row.get('review_input')
        text = body.get('original_instruction') if isinstance(body, dict) else None
        if (row.get('role') != role or row.get('dataset_scope') != 'RxR' or row.get('language') != 'en-US'
                or not isinstance(source, dict) or not isinstance(provenance, dict)
                or source.get('split') != 'train' or source.get('role') != 'guide'
                or str(source.get('instruction_id')) != str(record['instruction_id'])
                or str(source.get('record_id')) != str(record['instruction_id'])
                or source.get('scene_id') != record['scan']
                or str(source.get('trajectory_id')) != str(record['path_id'])
                or not isinstance(text, str)
                or hashlib.sha256(text.encode('utf-8')).hexdigest() != record['source_sha256']
                or provenance.get('source_record_sha256') != record['source_record_sha256']
                or provenance.get('archive_sha256') != archive
                or provenance.get('source_url') != source_url):
            raise ValueError('Unverified training source identity: ' + tid)
        expected_pair = record['generator'] if key == 'reviewer' else None
        if row.get('pair_id') != expected_pair:
            raise ValueError('RxR training pair identity mismatch: ' + tid)
        loaded[tid] = row
    if set(loaded) != set(expected):
        raise ValueError('RxR registry does not pin every declared training template')
    actual = {p.relative_to(root).as_posix() for folder in TRAIN_DIRS
              for p in (root / folder).rglob('*.json')}
    if actual != paths:
        raise ValueError('Unregistered or missing RxR training JSON files')
    for record in records:
        gen = loaded[record['generator']]
        rev = loaded[record['reviewer']]
        if rev['review_input']['candidate']['subtasks'] != gen['output']['subtasks']:
            raise ValueError('RxR paired review does not inspect its actual Generator candidate')
    return payload, loaded


def validate_training_assets(root=None):
    return _load_verified(root)[0]


def validate_training_library(role, rows, root=None):
    if role not in ('generator', 'reviewer'):
        raise ValueError('Unsupported RxR training role')
    _, pinned = _load_verified(root)
    expected = {key: row for key, row in pinned.items() if row['role'] == role}
    train = [row for row in rows if '-TRAIN-' in row.get('template_id', '')
             or row.get('source', {}).get('split') == 'train']
    actual_ids = [row.get('template_id') for row in train]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected):
        raise ValueError('RxR training library differs from its explicit source registry')
    for row in train:
        # Checking identity fields alone would accept stale or changed teaching
        # bodies after the registry was updated. Compare the exact parsed asset.
        if row != expected[row['template_id']]:
            raise ValueError('RxR in-memory teaching differs from its pinned asset: ' + row['template_id'])
