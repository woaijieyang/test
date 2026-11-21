"""Fail-closed provenance checks for the additional RxR training demonstrations."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = 'provenance/rxr_training_sources.json'


def validate_training_assets(root=None):
    root = Path(root) if root is not None else ROOT
    payload = json.loads((root/REGISTRY).read_text(encoding='utf-8'))
    records = payload.get('records', [])
    if len(records) != 8 or len({row['instruction_id'] for row in records}) != 8:
        raise ValueError('RxR training registry must identify eight distinct verified source records')
    if (payload.get('source_split') != 'train' or payload.get('source_role') != 'guide'
            or payload.get('language') != 'en-US'):
        raise ValueError('RxR training registry has an unsupported source identity')
    assets = payload.get('templates', [])
    if len(assets) != 24 or len({row['path'] for row in assets}) != 24:
        raise ValueError('RxR training registry must pin exactly twenty-four authored templates')
    for row in assets:
        relative = Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[:4] not in (
                ('generator','templates','RxR','train'), ('reviewer','templates','RxR','train')):
            raise ValueError('RxR registry path escapes its training directories')
        data = (root/relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError(f'RxR training asset changed: {relative}')
    return payload


def validate_training_library(role, rows):
    payload = validate_training_assets()
    by_id = {}
    for record in payload['records']:
        keys = ('generator',) if role == 'generator' else ('reviewer','diagnostic')
        for key in keys:
            by_id[record[key]] = record
    train = [row for row in rows if '-TRAIN-' in row['template_id']]
    if {row['template_id'] for row in train} != set(by_id):
        raise ValueError('RxR training library differs from its explicit source registry')
    for row in train:
        record = by_id[row['template_id']]
        source = row['source']
        text = (row.get('input') or row['review_input'])['original_instruction']
        if (source.get('split') != 'train' or source.get('role') != 'guide'
                or str(source.get('instruction_id')) != str(record['instruction_id'])
                or source.get('scene_id') != record['scan']
                or str(source.get('trajectory_id')) != str(record['path_id'])
                or hashlib.sha256(text.encode()).hexdigest() != record['source_sha256']
                or row['provenance'].get('source_record_sha256') != record['source_record_sha256']):
            raise ValueError(f'Unverified training source identity: {row["template_id"]}')
