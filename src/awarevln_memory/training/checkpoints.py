"""Versioned memory-only checkpoints; optimizer/RNG are saved by the Accelerate-backed engine."""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from safetensors.torch import load_file, save_file
from .artifacts import digest, identity, write_json, training_path
from .models import MemoryModules, ShortMemoryConfig

SCHEMA = 'hamlet.training-checkpoint.v1'


def file_inventory(paths):
    records=[]
    for path in sorted({str(Path(p).resolve()) for p in paths}):
        p=Path(path)
        if not p.is_file():raise FileNotFoundError(p)
        records.append({'path':str(p),'sha256':digest(p)})
    return {'files':records,'sha256':identity(records)}


def check_files(inventory):
    if identity(inventory['files'])!=inventory['sha256']:raise ValueError('inventory hash mismatch')
    for record in inventory['files']:
        if digest(record['path'])!=record['sha256']:raise ValueError('input asset drift: '+record['path'])


def save_modules(directory, modules, *, stage, contract, parent_sha=None, step=0):
    """Must be called on main process. Publishes metadata LAST as commit marker."""
    root=training_path(directory);root.mkdir(parents=True,exist_ok=True)
    if stage not in ('tcl','reader','router'):raise ValueError('unsupported checkpoint stage')
    for key in ('base_identity','protocol_identity','data_identity'):
        if not isinstance(contract.get(key),str) or not contract[key]:raise ValueError('missing '+key)
    if stage!='tcl' and not parent_sha:raise ValueError('parent checkpoint identity required')
    weight=root/'memory.safetensors'
    if weight.exists() or (root/'identity.json').exists():raise FileExistsError('checkpoint is immutable: '+str(root))
    fd,tmp=tempfile.mkstemp(dir=root,prefix='.weights-');os.close(fd)
    try:
        tensors={k:v.detach().cpu().contiguous() for k,v in modules.state_dict().items()}
        save_file(tensors,tmp)
        os.link(tmp,weight)
    finally:Path(tmp).unlink(missing_ok=True)
    metadata={'schema':SCHEMA,'config':modules.config.to_dict(),'stage':stage,
              'parent_sha256':parent_sha,'step':int(step),'contract':contract,
              'weights_sha256':digest(weight),'weights_file':'memory.safetensors'}
    metadata['checkpoint_sha256']=identity(metadata)
    write_json(root/'identity.json',metadata)
    return metadata


def read_identity(directory):
    root=Path(directory).resolve()
    doc=json.loads((root/'identity.json').read_text())
    if doc.get('schema')!=SCHEMA:raise ValueError('historical/unknown checkpoint is not short-memory-v1')
    claimed=doc['checkpoint_sha256'];payload={k:v for k,v in doc.items() if k!='checkpoint_sha256'}
    if identity(payload)!=claimed:raise ValueError('checkpoint metadata hash mismatch')
    if doc.get('weights_file')!='memory.safetensors':raise ValueError('invalid checkpoint path')
    if digest(root/'memory.safetensors')!=doc['weights_sha256']:raise ValueError('checkpoint weights changed')
    return doc


def load_modules(directory, *, stage=None, expected_base=None, expected_protocol=None):
    doc=read_identity(directory)
    if stage is not None and doc['stage']!=stage:raise ValueError('wrong source stage')
    for key,expected in [('base_identity',expected_base),('protocol_identity',expected_protocol)]:
        if expected is not None and doc['contract'][key]!=expected:raise ValueError('checkpoint '+key+' mismatch')
    model=MemoryModules(ShortMemoryConfig(**doc['config']))
    model.load_state_dict(load_file(str(Path(directory)/'memory.safetensors')),strict=True)
    return model,doc


def verify_parent(stage, parent):
    required={'reader':'tcl','router':'reader'}
    if stage=='tcl':
        if parent is not None:raise ValueError('TCL initialization has no parent checkpoint')
        return None
    if parent is None:raise ValueError('missing parent checkpoint')
    doc=read_identity(parent)
    if doc['stage']!=required[stage]:raise ValueError('invalid stage transition')
    return doc


def export_bundle(checkpoint, destination, *, base_inventory, protocol, use_router=False, mode_lock=True):
    """An inference candidate, NOT a declaration of GPU/navigation acceptance."""
    import shutil
    root=training_path(destination)
    if root.exists():raise FileExistsError(root)
    # Preflight all immutable prerequisites BEFORE creating a published bundle
    # path; failure must not leave a half-populated directory that blocks retry.
    doc=read_identity(checkpoint)
    if doc['stage'] not in ('reader','router'):raise ValueError('TCL alone is not a navigation candidate')
    if use_router and doc['stage']!='router':raise ValueError('router was not trained')
    check_files(base_inventory)
    if base_inventory['sha256']!=doc['contract']['base_identity']:raise ValueError('wrong base model inventory')
    if identity(protocol)!=doc['contract']['protocol_identity']:raise ValueError('wrong protocol')
    root.mkdir(parents=True)
    for name in ('identity.json','memory.safetensors'):
        shutil.copyfile(Path(checkpoint)/name,root/name)
    config={'schema':'hamlet.inference-bundle.v1','checkpoint_sha256':doc['checkpoint_sha256'],
            'base_inventory':base_inventory,'protocol':protocol,'use_router':bool(use_router),
            'mode_lock':bool(mode_lock),'status':'CANDIDATE_PENDING_NAVIGATION_VALIDATION'}
    write_json(root/'bundle.json',config)
    return config
