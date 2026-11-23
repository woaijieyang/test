"""Guarded offline publication of one complete RxR training teaching bundle.

All validation precedes writes. Replacements are atomic per file; the registry
is published last. An ordinary write failure rolls back only our own writes.
A process crash or an external concurrent edit fails closed through registry
hashes; this is not a multi-file filesystem transaction or a hot-reload API.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tempfile

REGISTRY = 'provenance/rxr_training_sources.json'
FOLDERS = ('generator/templates/RxR/train', 'reviewer/templates/RxR/train')


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _path(root, name):
    p = Path(name)
    if name != REGISTRY and (p.is_absolute() or len(p.parts) != 5 or '..' in p.parts
            or p.parent.as_posix() not in FOLDERS or p.suffix != '.json' or p.as_posix() != name):
        raise ValueError('Refuse output outside the RxR training bundle: ' + str(name))
    path = root / p
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError('Refuse symbolic-link output: ' + name)
    return path


def _read(path):
    return path.read_bytes() if path.is_file() else None


def _replace(source, target):
    os.replace(source, target)


def publish(root, outputs, registry, *, check=False):
    root = Path(root).resolve()
    if len(outputs) != 24 or any(not isinstance(x, bytes) for x in outputs.values()):
        raise ValueError('A complete authored bundle requires twenty-four byte artifacts')
    pins = registry.get('templates', [])
    names = [row['path'] for row in pins]
    if len(names) != len(set(names)) or set(names) != set(outputs):
        raise ValueError('Registry/output inventory differs')
    if any(row['sha256'] != sha(outputs[row['path']]) for row in pins):
        raise ValueError('Registry/output bytes differ')
    for name in outputs:
        _path(root, name)
    registry_path = _path(root, REGISTRY)
    observed = {name: _read(_path(root, name)) for name in outputs}
    observed[REGISTRY] = _read(registry_path)
    actual = {p.relative_to(root).as_posix() for folder in FOLDERS
              for p in (root / folder).rglob('*.json')}
    if actual - set(outputs):
        raise ValueError('Refuse to absorb unregistered training files: ' + ', '.join(sorted(actual - set(outputs))))
    old_pins = {}
    if observed[REGISTRY] is not None:
        old = json.loads(observed[REGISTRY])
        if not isinstance(old, dict):
            raise ValueError('Invalid previous training registry')
        prior = old.get('templates', [])
        old_pins = {row['path']: row['sha256'] for row in prior}
        if len(prior) != len(old_pins) or set(old_pins) != set(outputs):
            raise ValueError('Refuse an unreviewed training inventory change')
        for field in ('source_url', 'archive_sha256', 'source_split', 'source_role', 'language', 'records'):
            if old.get(field) != registry.get(field):
                raise ValueError('Refuse an unreviewed source registry change: ' + field)
    desired = dict(outputs)
    desired[REGISTRY] = encode(registry)
    changed = [name for name in [*sorted(outputs), REGISTRY] if observed[name] != desired[name]]
    for name in outputs:
        current = observed[name]
        if name in old_pins and current is None:
            raise ValueError('Refuse to recreate an independently removed teaching file: ' + name)
        if current is not None and current != desired[name] and sha(current) != old_pins.get(name):
            raise ValueError('Refuse to overwrite independently changed teaching: ' + name)
    if check:
        if changed:
            raise ValueError('Committed training bundle differs from authored specification: ' + ', '.join(changed))
        return []
    if not changed:
        return []
    root.mkdir(parents=True, exist_ok=True)
    committed = []
    with tempfile.TemporaryDirectory(prefix='.rxr-authoring-', dir=root) as temporary:
        scratch = Path(temporary)
        staged, backups = {}, {}
        for number, name in enumerate(changed):
            staged[name] = scratch / ('new-' + str(number))
            staged[name].write_bytes(desired[name])
            if observed[name] is not None:
                backups[name] = scratch / ('old-' + str(number))
                backups[name].write_bytes(observed[name])
        # Validate the complete read set again, not only outputs that changed.
        if any(_read(_path(root, name)) != data for name, data in observed.items()):
            raise ValueError('Training bundle changed concurrently before publication')
        try:
            for name in changed:
                target = _path(root, name)
                if _read(target) != observed[name]:
                    raise ValueError('Training file changed concurrently: ' + name)
                target.parent.mkdir(parents=True, exist_ok=True)
                _replace(staged[name], target)
                committed.append(name)
        except BaseException:
            conflicts = []
            for name in reversed(committed):
                target = _path(root, name)
                if _read(target) != desired[name]:
                    conflicts.append(name)
                    continue
                if name in backups:
                    _replace(backups[name], target)
                else:
                    target.unlink()
            if conflicts:
                raise RuntimeError('Concurrent changes preserved; manually reconcile: ' + ', '.join(conflicts))
            raise
    return changed
