"""Configuration adapter for staged training; no implicit downloads or GPU jobs."""
from __future__ import annotations
import json
from pathlib import Path
import torch
from .artifacts import read_records,training_path,identity,write_json,budget,digest,require_clean_encoding_dtype
from .cache import FeatureStore
from .checkpoints import check_files,load_modules,verify_parent
from .datasets import StageDataset,validate_partitions
from .models import ShortMemoryConfig,MemoryModules,StageModel
from .engine import train_stage,optimizer_groups


def load_config(path):
    import yaml
    value=yaml.safe_load(Path(path).read_text())
    if not isinstance(value,dict):raise ValueError('configuration must be a mapping')
    allowed={'stage','rows','prompt_cache','moment_cache','router_cache','base_model','base_inventory',
             'protocol','parent','output','model','train','smoke_gate'}
    if set(value)-allowed:raise ValueError('unknown configuration keys: '+str(set(value)-allowed))
    return value


def open_store(path):
    root=training_path(path)
    record=json.loads((root/'contract.json').read_text())
    return FeatureStore(root,record['contract'])


def stage_datasets(config):
    stage=config['stage'];path=training_path(config['rows']);rows=read_records(path)
    validate_partitions(rows)
    if stage=='router':store=open_store(config['router_cache']);moments=None
    else:
        store=open_store(config['prompt_cache'])
        moments=open_store(config['moment_cache']) if stage=='reader' else None
    train=StageDataset(rows,store,stage,'train',moment_store=moments)
    dev=StageDataset(rows,store,stage,'memory-dev',moment_store=moments)
    # Full preflight rather than letting a bad window fail on a late training step.
    for dataset in (train,dev):
        for i in range(len(dataset)):dataset[i]
    sources=[str(path),str(store.root/'contract.json')]
    if moments:sources.append(str(moments.root/'contract.json'))
    # Bind to the exact feature payloads consumed by this stage, not just a
    # cache schema.  A separately modified payload+metadata must invalidate
    # both the next training run and resume from the old checkpoint.
    readsets = {}
    for partition in ('train', 'memory-dev'):
        selected = [r for r in rows if r['partition'] == partition]
        if stage == 'tcl':
            keys = [r[role] for r in selected for role in ('anchor', 'positive', 'negative')]
            readsets[partition] = {'prompt': store.readset_identity(keys, partition=partition)}
        elif stage == 'reader':
            prompts = [r['current'] for r in selected]
            moment_keys = prompts + [key for r in selected for key in r['past'] if key is not None]
            readsets[partition] = {
                'prompt': store.readset_identity(prompts, partition=partition),
                'moment': moments.readset_identity(moment_keys, partition=partition),
            }
        else:
            keys = [r['feature_key'] for r in selected]
            readsets[partition] = {'router': store.readset_identity(keys, partition=partition)}
    data_identity=identity({'files':[(p,digest(p)) for p in sources],
                            'rows':rows,'cache_contract':store.contract,
                            'moment_contract':moments.contract if moments else None,
                            'readsets':readsets})
    return train,dev,data_identity,store,moments


def load_llm(config,cpu=False,*,clean_encoding=False):
    from transformers import AutoModelForCausalLM
    root=Path(config['base_model']).resolve();path=root/'llm' if (root/'llm').is_dir() else root
    if not path.is_dir():raise FileNotFoundError(path)
    # Trust the existing local checkpoint/config, never fetch remote code or weights.
    if clean_encoding:
        protocol=json.loads(Path(config['protocol']).read_text())
        name=protocol.get('clean_encoding_dtype')
        if name not in ('float16','bfloat16','float32'):raise ValueError('explicit clean encoding dtype required')
        dtype=getattr(torch,name)
    else:
        dtype=torch.float32 if cpu else torch.bfloat16
    model=AutoModelForCausalLM.from_pretrained(str(path),local_files_only=True,torch_dtype=dtype)
    model.requires_grad_(False);model.eval()
    return model


def run(config,*,dry_run=False,diagnostic=False,resume=None,cpu=False):
    stage=config['stage']
    if stage not in ('tcl','reader','router'):raise ValueError('unknown stage')
    inventory=json.loads(Path(config['base_inventory']).read_text());check_files(inventory)
    protocol=json.loads(Path(config['protocol']).read_text());protocol_id=identity(protocol)
    if protocol.get('visual_frames')!=8 or protocol.get('temporal_total_slots')!=4 or protocol.get('history_past_calls')!=3:
        raise ValueError('base visual/temporal input contract changed')
    if protocol.get('data_allowlist')!=['r2r/train','rxr/train/en-US']:raise ValueError('training allowlist changed')
    for source in protocol.get('source_files',[]):
        if digest(source['path'])!=source['sha256']:raise ValueError('inference/preprocessing source changed after protocol lock')
    from accelerate.utils import set_seed
    set_seed(int(config.get('train',{}).get('seed',42)))
    parent=verify_parent(stage,config.get('parent'))
    if parent:
        modules,doc=load_modules(config['parent'],expected_base=inventory['sha256'],expected_protocol=protocol_id)
        if config.get('model') and modules.config.to_dict()!=ShortMemoryConfig(**config['model']).to_dict():raise ValueError('parent/model architecture mismatch')
    else:modules=MemoryModules(ShortMemoryConfig(**config['model']))
    train,dev,data_id,store,moment_store=stage_datasets(config)
    for cache in [store]+([moment_store] if moment_store else []):
        if cache.contract['base_identity']!=inventory['sha256'] or cache.contract['protocol_identity']!=protocol_id:
            raise ValueError('cache base/protocol does not match run')
    if stage=='reader' and moment_store.contract.get('moment_checkpoint_sha256')!=parent['checkpoint_sha256']:
        raise ValueError('Reader cache not generated by selected Moment')
    if stage=='router' and store.contract.get('reader_checkpoint_sha256')!=parent['checkpoint_sha256']:
        raise ValueError('Router data not generated by fixed Reader')
    contract={'base_identity':inventory['sha256'],'protocol_identity':protocol_id,'data_identity':data_id}
    train_cfg=dict(config.get('train',{}))
    allowed={'epochs','step_cap','micro_batch','accumulation','lr','gate_lr','weight_decay',
             'warmup_ratio','eval_steps','seed','mixed_precision','patience','gradient_checkpointing','expected_world_size'}
    if set(train_cfg)-allowed:raise ValueError('unknown training options')
    grad_checkpoint=train_cfg.pop('gradient_checkpointing',True)
    expected_world=train_cfg.pop('expected_world_size',2 if stage!='router' else 1)
    # Autocast can silently change the frozen decoder's computation precision.
    # Native prompt/Moment caches and deployed runtime are bound to the exact
    # clean-encoding dtype; require the same dtype throughout first-pass SFT.
    # If a BF16 study is wanted, re-bootstrap/re-encode under a BF16 protocol
    # as a separate experiment rather than silently mixing FP16 with BF16.
    if stage != 'router':
        expected_dtype = protocol.get('clean_encoding_dtype')
        if expected_dtype not in ('float16', 'bfloat16', 'float32'):
            raise ValueError('explicit supported clean encoding dtype required')
        if train_cfg.get('mixed_precision', 'no') == 'bf16' and expected_dtype != 'bfloat16':
            raise ValueError('BF16 autocast cannot be mixed with a non-BF16 clean moment protocol')
    # List exact trainables without loading the 8B model for a dry run.
    model=StageModel(None,modules,stage)
    _,names=optimizer_groups(model,train_cfg.get('lr',5e-5),train_cfg.get('gate_lr',2e-5),train_cfg.get('weight_decay',.01))
    from collections import Counter
    coverage={name:{'windows':len(ds),
                    'route_instructions':len({r.get('route_key') for r in ds.rows if r.get('route_key')}),
                    'families':len({r['family'] for r in ds.rows}),
                    'scenes':len({r['scene'] for r in ds.rows}),
                    'source_windows':dict(Counter(r['dataset'] for r in ds.rows))}
              for name,ds in [('train',train),('memory-dev',dev)]}
    result={'stage':stage,'contract':contract,'train_samples':len(train),'dev_samples':len(dev),
            'data_coverage':coverage,
            'trainable':names,'parent':parent['checkpoint_sha256'] if parent else None,
            'status':'PREFLIGHT_ONLY','gpu_validated':False}
    result['planned_budget']=budget(len(train),train_cfg.get('epochs',4),train_cfg.get('micro_batch',1),
                                   expected_world,train_cfg.get('accumulation',8),train_cfg.get('step_cap',5000))
    if dry_run:return result
    import os
    if int(os.environ.get('WORLD_SIZE','1'))!=expected_world:
        raise ValueError('launch world size differs from configuration; use torchrun or a separate diagnostic config')
    if not diagnostic:
        if stage!='router' and coverage['train']['route_instructions']<1000:
            raise ValueError('fewer than 1000 distinct train route-instructions remain after stage-specific auditing; repair data or use a diagnostic run')
        if sum(x['route_instructions'] for x in coverage.values())>2000:
            raise ValueError('route budget exceeds the agreed 2000-example ceiling')
        gate=json.loads(Path(config['smoke_gate']).read_text())
        if gate.get('status')!='PASSED' or gate.get('contract')!=contract:raise ValueError('production training requires matching real smoke gate')
        for item in gate.get('evidence',[]):
            if digest(item['path'])!=item['sha256']:raise ValueError('smoke evidence changed')
        if not gate.get('evidence'):raise ValueError('empty smoke evidence is not acceptance')
    if stage!='router':
        llm=load_llm(config,cpu=cpu,clean_encoding=True)
        require_clean_encoding_dtype(protocol['clean_encoding_dtype'],next(llm.parameters()).dtype)
        if getattr(llm.config,'hidden_size',None)!=modules.config.hidden_size:raise ValueError('model dimension mismatch')
        if grad_checkpoint:
            llm.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        model=StageModel(llm,modules,stage)
    return train_stage(model,train,dev,config['output'],contract,parent_sha=result['parent'],
                       resume=resume,cpu=cpu,diagnostic=diagnostic,**train_cfg)
