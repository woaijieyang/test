"""Frozen policy/checkpoint binding; this module deliberately does not import torch."""
import hashlib,json,os
from pathlib import Path

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()

def load_policy(root):
    root=Path(root).resolve();path=root/'configs/hamlet/aw4-seed10.json'
    config=json.loads(path.read_text())
    for name in ['base_model','adapter','router','base_attestation']:
        value=Path(config[name])
        if value.is_absolute() or '..' in value.parts:raise ValueError('Policy path must be workspace-relative')
        config[name]=str(root/value)
    return config

def policy_identity(root):
    root=Path(root).resolve();folder=root/'models/hamlet-v2'
    files=[root/'configs/hamlet/aw4-seed10.json']
    for p in sorted(folder.rglob('*')):
        if p.is_symlink():raise ValueError('HAMLET artifacts must be independently owned regular files')
        if p.is_file():files.append(p)
    if len(files)<10:raise ValueError('Incomplete HAMLET artifact closure')
    records=[{'path':str(p),'sha256':digest(p)} for p in files]
    return {'method':'hamlet-v2-aw4-seed10','sha256':hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest(),'files':records}

def bind_worker(root,run):
    root=Path(root).resolve();manifest=json.loads((Path(run)/'run_manifest.json').read_text())
    os.environ.pop('CASE2_HAMLET_CONFIG',None)
    identity=manifest.get('policy_identity')
    if identity is None:
        if manifest.get('method','baseline')!='baseline':raise ValueError('Missing candidate policy binding')
        return
    current=policy_identity(root)
    if identity!=current or manifest.get('method')!='hamlet':raise ValueError('Worker policy differs from frozen run')
    frozen={x['path']:x['sha256'] for x in manifest['frozen_files']}
    if any(frozen.get(x['path'])!=x['sha256'] for x in current['files']):raise ValueError('Candidate assets not frozen')
    os.environ['CASE2_HAMLET_CONFIG']=str(root/'configs/hamlet/aw4-seed10.json')
