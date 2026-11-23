"""Create concrete run-local paths from the existing workspace/preflight, read-only."""
from __future__ import annotations
import json
from pathlib import Path
from .artifacts import digest,identity,new_run_dir,write_json,write_bytes,training_path
from .checkpoints import file_inventory


def initialize(workspace,output):
    import yaml
    # Validate immutable prerequisites before claiming the exclusive output
    # directory.  An absent/stale model preflight must not strand a partial
    # workspace which would then require manual deletion before retrying.
    workspace=Path(workspace).resolve();root=training_path(output)
    native=json.loads((workspace/'outputs/preflight/model.json').read_text())
    for record in native['files']:
        if digest(record['path'])!=record['sha256']:raise ValueError('official model preflight is stale')
    inventory=file_inventory([r['path'] for r in native['files']])
    base=workspace/'models/awarevln'
    config_path=base/'llm/config.json'
    if not config_path.is_file():raise FileNotFoundError('expected native LLM config '+str(config_path))
    config=json.loads(config_path.read_text());hidden=int(config['hidden_size'])
    source_paths=['src/vlnce_baselines/awarevln_trainer.py','src/llava/conversation.py',
                  'src/llava/mm_utils.py','src/awarevln_memory/training/models.py',
                  'src/awarevln_memory/memory/adapter.py','src/hamlet_v2/trained_runtime.py']
    protocol={'schema':'hamlet.protocol.v1','visual_frames':8,'temporal_total_slots':4,
              'history_past_calls':3,'moment_tokens_per_slot':4,'data_allowlist':['r2r/train','rxr/train/en-US'],
              'reason_token':'<BEGIN_OF_REASONING>','act_token':'<BEGIN_OF_ACTION>',
              'mode_lock':True,'conversation':'llama_3','clean_encoding_dtype':'float16',
              'source_files':[{'path':str(workspace/p),'sha256':digest(workspace/p)} for p in source_paths]}
    plan=yaml.safe_load((workspace/'configs/hamlet/training/plan.yaml').read_text())
    if not isinstance(plan,dict) or any(stage not in plan for stage in ('tcl','reader','router')):
        raise ValueError('missing staged training budget')
    root=new_run_dir(root)
    write_json(root/'contracts/base_inventory.json',inventory);write_json(root/'contracts/protocol.json',protocol)
    for stage in ('tcl','reader','router'):
        rows={'tcl':'tcl','reader':'windows','router':'router'}[stage]
        cfg={'stage':stage,'rows':str(root/f'datasets/{rows}.accepted.jsonl'),
             'prompt_cache':str(root/'cache/prompts'),'moment_cache':str(root/'cache/moments'),
             'router_cache':str(root/'cache/router'),'base_model':str(base),
             'base_inventory':str(root/'contracts/base_inventory.json'),'protocol':str(root/'contracts/protocol.json'),
             'parent':None if stage=='tcl' else str(root/('selected/moment' if stage=='reader' else 'selected/reader')),
             'output':str(root/f'checkpoints/{stage}'),'smoke_gate':str(root/f'contracts/{stage}-smoke.json'),
             'model':{'hidden_size':hidden},'train':plan[stage]}
        write_bytes(root/f'configs/{stage}.yaml',yaml.safe_dump(cfg,sort_keys=False).encode())
    report={'schema':'hamlet.workspace.v1','workspace':str(workspace),'run_root':str(root),
            'base_identity':inventory['sha256'],'protocol_identity':identity(protocol),
            'status':'PATHS_MATERIALIZED_NOT_TRAINING_READY',
            'required_next':'Audit actual train sources/rollouts, build accepted stage datasets and smoke evidence.'}
    write_json(root/'contracts/paths.lock.json',report)
    return report


def select_checkpoint(source,destination):
    """Copy only a validated, immutable memory checkpoint, never optimizer/base weights."""
    import shutil
    from .checkpoints import read_identity
    doc=read_identity(source);dest=training_path(destination)
    dest.mkdir(parents=True,exist_ok=False)
    for name in ('identity.json','memory.safetensors'):shutil.copyfile(Path(source)/name,dest/name)
    if read_identity(dest)!=doc:raise ValueError('selected checkpoint copy mismatch')
    return {'checkpoint_sha256':doc['checkpoint_sha256'],'stage':doc['stage'],'destination':str(dest),
            'note':'Selection evidence must separately identify the dev/B rule used; copying is not acceptance.'}
