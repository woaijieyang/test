#!/usr/bin/env python3
"""Read-only source audit and explicit case1 partition sealing (stdlib only).

No automatic field guessing. Production counts are fixed by the user's case1
registration. Output includes identities, not annotation goals/reference paths.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

PARTS = ('A1', 'A2', 'A3', 'B1', 'B2', 'B3', 'Remaining')
COUNTS = {
    'r2r': dict(zip(PARTS, (123, 183, 306, 123, 183, 306, 615))),
    'rxr_us': dict(zip(PARTS, (81, 122, 204, 81, 122, 204, 409))),
}

class AuditError(ValueError):
    pass

def _pairs(pairs):
    out = {}
    for key, val in pairs:
        if key in out:
            raise AuditError(f'duplicate JSON object key: {key!r}')
        out[key] = val
    return out

def _invalid_constant(value):
    raise AuditError(f'non-finite JSON constant: {value}')

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def load(path: Path):
    path = Path(path)
    if not path.is_file():
        raise AuditError(f'source file not found: {path}')
    opener = gzip.open if path.suffix == '.gz' else open
    try:
        with opener(path, 'rt', encoding='utf-8') as f:
            return json.load(f, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as e:
        raise AuditError(f'cannot read JSON source {path}: {e}') from e

def verify_frozen_json_copy(source: Path, copied: Path, expected_sha256: str) -> dict:
    source,copied=Path(source),Path(copied)
    if sha(source)!=expected_sha256:raise AuditError("frozen_json_source_hash_mismatch")
    original,replica=load(source),load(copied)
    if original!=replica:raise AuditError("frozen_json_content_drift")
    if sha(copied)!=expected_sha256:raise AuditError("frozen_json_copy_byte_mismatch")
    return dict(status="VERIFIED_EXACT_BYTES",sha256=expected_sha256,bytes=source.stat().st_size)

def copy_frozen_json(source: Path, target: Path, expected_sha256: str) -> dict:
    source,target=Path(source),Path(target)
    if sha(source)!=expected_sha256:raise AuditError("frozen_json_source_hash_mismatch")
    load(source) # Strict JSON, including duplicate keys and non-finite constants.
    with target.open("xb")as stream:
        stream.write(source.read_bytes());stream.flush();os.fsync(stream.fileno())
    return verify_frozen_json_copy(source,target,expected_sha256)

def pointer(doc: Any, ptr: str):
    if not isinstance(ptr, str) or 'UNBOUND' in ptr:
        raise AuditError('JSON pointer is UNBOUND or is not a string')
    if ptr == '':
        return doc
    if not ptr.startswith('/'):
        raise AuditError(f'not an RFC6901 pointer: {ptr!r}')
    value = doc
    try:
        for token in ptr.split('/')[1:]:
            # Reject invalid escaping instead of silently treating it as literal.
            for i, ch in enumerate(token):
                if ch == '~' and (i+1 == len(token) or token[i+1] not in '01'):
                    raise AuditError(f'invalid pointer escape: {ptr!r}')
            key = token.replace('~1', '/').replace('~0', '~')
            if isinstance(value, dict):
                value = value[key]
            elif isinstance(value, list):
                if not key.isdigit() or (len(key) > 1 and key.startswith('0')):
                    raise AuditError(f'invalid array pointer index: {ptr!r}')
                value = value[int(key)]
            else:
                raise AuditError(f'pointer traverses a scalar: {ptr!r}')
    except (KeyError, IndexError) as e:
        raise AuditError(f'pointer not present: {ptr!r}') from e
    return value

def identity(row, selectors) -> tuple[str, ...]:
    if not isinstance(selectors, list) or not selectors:
        raise AuditError('identity_pointers must be an explicit nonempty list; use [""] for scalar IDs')
    values = []
    for selector in selectors:
        value = pointer(row, selector)
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise AuditError('identity values must be strings or non-bool integers')
        text = str(value)
        if not text or text != text.strip():
            raise AuditError('empty or whitespace-padded identity is not allowed')
        values.append(text)
    return tuple(values)

def _source_path(name, base: Path) -> Path:
    if not isinstance(name, str) or not name or 'UNBOUND' in name:
        raise AuditError('source path is not explicitly bound')
    p = Path(name).expanduser()
    return (p if p.is_absolute() else base/p).resolve()

def audit(binding: dict, base: Path) -> dict:
    if binding.get('schema_version') != 1:
        raise AuditError('unsupported binding schema_version')
    datasets = binding.get('datasets')
    if not isinstance(datasets, dict) or set(datasets) != set(COUNTS):
        raise AuditError('bind exactly r2r and rxr_us; no inferred datasets')
    file_cache = {}
    inputs = {}
    def read_spec(spec):
        if not isinstance(spec, dict):
            raise AuditError('source spec must be an object')
        p = _source_path(spec.get('file'), base)
        if p not in file_cache:
            file_cache[p] = load(p)
            inputs[str(p)] = {'sha256': sha(p), 'bytes': p.stat().st_size}
        rows = pointer(file_cache[p], spec.get('rows_pointer'))
        if not isinstance(rows, list):
            raise AuditError(f'rows_pointer is not an array in {p}')
        return rows, p
    result = {}
    for name, expected in COUNTS.items():
        cfg = datasets[name]
        evidence = cfg.get('namespace_evidence')
        if not isinstance(evidence, str) or not evidence.strip() or 'UNBOUND' in evidence:
            raise AuditError(f'{name}: record source-qualified language/role/namespace evidence')
        ann = cfg.get('annotations')
        rows, ann_path = read_spec(ann)
        selectors = ann.get('identity_pointers')
        filters = ann.get('filters', [])
        if not isinstance(filters, list):
            raise AuditError('annotation filters must be a list')
        eligible = []
        for row in rows:
            accepted = True
            for filt in filters:
                if not isinstance(filt, dict) or set(filt) != {'pointer', 'equals'}:
                    raise AuditError('filter requires exactly pointer and equals')
                if pointer(row, filt['pointer']) != filt['equals']:
                    accepted = False
            if accepted:
                eligible.append(identity(row, selectors))
        if len(eligible) != len(set(eligible)):
            raise AuditError(f'{name}: annotation identities are not unique; bind composite keys')
        expected_total = sum(expected.values())
        if len(eligible) != expected_total:
            raise AuditError(f'{name}: eligible annotations={len(eligible)}, expected={expected_total}; do not truncate')
        universe = set(eligible)
        specs = cfg.get('partitions')
        if not isinstance(specs, dict) or set(specs) != set(PARTS):
            raise AuditError(f'{name}: exactly seven leaf partitions must be bound')
        sets = {}
        used = set()
        for part in PARTS:
            members, path = read_spec(specs[part])
            ids = [identity(row, specs[part].get('identity_pointers')) for row in members]
            if any(len(i) != len(selectors) for i in ids):
                raise AuditError(f'{name}/{part}: annotation and membership identity arity differs')
            if len(ids) != expected[part]:
                raise AuditError(f'{name}/{part}: {len(ids)} members, expected {expected[part]}')
            if len(ids) != len(set(ids)):
                raise AuditError(f'{name}/{part}: duplicate identity')
            if used.intersection(ids):
                raise AuditError(f'{name}/{part}: overlap with previous leaf partition')
            if set(ids) - universe:
                raise AuditError(f'{name}/{part}: foreign annotation identity')
            used.update(ids)
            sets[part] = ids
        if used != universe:
            raise AuditError(f'{name}: partition union differs from eligible annotation universe')
        sets['A'] = sets['A1'] + sets['A2'] + sets['A3']
        sets['B'] = sets['B1'] + sets['B2'] + sets['B3']
        sets['ALL'] = sets['A'] + sets['B'] + sets['Remaining']
        result[name] = {
            'annotation_source': str(ann_path),
            'namespace_evidence': evidence,
            'identity_pointers': selectors,
            'sets': sets,
            'counts': {k: len(v) for k, v in sets.items()},
        }
    return {'schema_version': 1, 'status': 'VERIFIED_PARTITIONS_ONLY',
            'scope': 'manifest identity/count/coverage; not navigation evaluation',
            'inputs': inputs, 'datasets': result}

def _write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())

def seal(binding_path: Path, out: Path):
    binding_path, out = Path(binding_path).resolve(), Path(out).absolute()
    if out.exists():
        raise AuditError(f'refusing to overwrite existing output: {out}')
    binding = load(binding_path)
    report = audit(binding, binding_path.parent)
    report['binding'] = {'path': str(binding_path), 'sha256': sha(binding_path)}
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.'+out.name+'-pending-', dir=str(out.parent)))
    lock = out.parent / ('.'+out.name+'.seal.lock')
    lock_fd = None
    try:
        lock_fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        if out.exists():
            raise AuditError(f'output appeared while preparing: {out}')
        manifests = {}
        for name, dataset in report['datasets'].items():
            manifests[name] = {}
            for part, keys in dataset.pop('sets').items():
                relative = Path(name)/(part+'.json')
                _write_json(temp/relative, {'schema_version': 1, 'dataset': name,
                    'partition': part, 'count': len(keys),
                    'identity_pointers': dataset['identity_pointers'],
                    'identities': [list(key) for key in keys],
                    'order': 'registry_order; A=A1+A2+A3; B=B1+B2+B3; ALL=A+B+Remaining'})
                manifests[name][part] = {'file': relative.as_posix(), 'sha256': sha(temp/relative)}
        report['manifests'] = manifests
        _write_json(temp/'seal.json', report)
        os.rename(temp, out)
    except FileExistsError as e:
        raise AuditError(f'concurrent seal or existing lock/output: {e}') from e
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
            lock.unlink(missing_ok=True)
        if temp.exists():
            shutil.rmtree(temp)
    return report

def inspect(path: Path, limit=60) -> dict:
    doc = load(path)
    entries = []
    def escape(s): return str(s).replace('~', '~0').replace('/', '~1')
    def walk(value, ptr, depth):
        if len(entries) >= limit or depth > 8:
            return
        if isinstance(value, dict):
            entries.append({'pointer': ptr, 'type': 'object', 'keys': list(value)[:30]})
            for key, val in value.items():
                if isinstance(val, (dict, list)):
                    walk(val, ptr+'/'+escape(key), depth+1)
        elif isinstance(value, list):
            item = {'pointer': ptr, 'type': 'array', 'length': len(value)}
            if value:
                item['first_type'] = type(value[0]).__name__
                if isinstance(value[0], dict):
                    item['first_keys'] = list(value[0])[:30]
            entries.append(item)
            if value and isinstance(value[0], (dict, list)):
                walk(value[0], ptr+'/0', depth+1)
    walk(doc, '', 0)
    return {'file': str(Path(path).resolve()), 'sha256': sha(Path(path)),
            'structure_only': True, 'entries': entries,
            'note': 'Pointers are observations, not an inferred binding. Membership order is never guessed.'}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('inspect'); a.add_argument('--file', type=Path, required=True)
    b = sub.add_parser('seal'); b.add_argument('--binding', type=Path, required=True); b.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    try:
        res = inspect(args.file) if args.cmd == 'inspect' else seal(args.binding, args.out)
        print(json.dumps(res, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (AuditError, OSError, TypeError, KeyError) as e:
        print(json.dumps({'status': 'FAILED_OR_UNBOUND', 'error': str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())


def source_snapshot(root,*,map_stage):
    """One source identity algorithm shared by evaluator and storage preparation."""
    import hashlib
    root=Path(root);frozen=[]
    for folder in('src','scripts','configs'):
        for path in sorted((root/folder).rglob('*')):
            if path.is_file()and'__pycache__'not in path.parts and not any(x.endswith('.egg-info')for x in path.parts):
                frozen.append(dict(path=str(path),sha256=sha(path)))
    if map_stage:
        for folder in('vendor_sources/EvoMemNav','models/graph001'):
            for path in sorted((root/folder).rglob('*')):
                if not path.is_file()or'.git'in path.parts:continue
                if folder=='models/graph001'and path.name!='model_lock.json':continue
                frozen.append(dict(path=str(path),sha256=sha(path)))
    return frozen,hashlib.sha256(json.dumps(frozen,sort_keys=True).encode()).hexdigest()
