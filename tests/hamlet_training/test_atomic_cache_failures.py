"""Check failure cleanup for immutable cache artifacts and export preflight."""
import json
import pytest
import torch
from awarevln_memory.training import cache as cache_module
from awarevln_memory.training.artifacts import identity, write_json
from awarevln_memory.training.cache import FeatureStore
from awarevln_memory.training.checkpoints import (file_inventory,save_modules,export_bundle)
from awarevln_memory.training.models import MemoryModules,ShortMemoryConfig
from awarevln_memory.training.datasets import validate_events


def test_failed_metadata_publish_removes_own_tensor(tmp_path,monkeypatch):
    c={'base_identity':'base','protocol_identity':'p','source_identity':'s'}
    store=FeatureStore(tmp_path/'features',c,create=True)
    meta={'source_split':'train','dataset':'r2r','partition':'train'}
    original=cache_module.write_json
    def fail(*_args,**_kwargs):raise RuntimeError('simulated disk I/O failure')
    monkeypatch.setattr(cache_module,'write_json',fail)
    with pytest.raises(RuntimeError,match='disk'):
        store.put('a',{'prompt':torch.ones(1,8)},meta)
    assert not store._stem('a').with_suffix('.safetensors').exists()
    assert not store._stem('a').with_suffix('.json').exists()
    monkeypatch.setattr(cache_module,'write_json',original)
    store.put('a',{'prompt':torch.ones(1,8)},meta)
    assert store.get('a',partition='train')[0]['prompt'].shape == (1,8)


def test_failed_export_does_not_leave_partial_bundle(tmp_path):
    modules=MemoryModules(ShortMemoryConfig(hidden_size=8,memory_size=12,heads=3,layers=1))
    asset=tmp_path/'base.model';asset.write_bytes(b'base')
    inventory=file_inventory([asset])
    protocol={'data_allowlist':['r2r/train','rxr/train/en-US']}
    contract={'base_identity':inventory['sha256'],'protocol_identity':identity(protocol),'data_identity':'d'}
    ckpt=tmp_path/'checkpoint'
    save_modules(ckpt,modules,stage='reader',contract=contract,parent_sha='moment')
    target=tmp_path/'bundle'
    with pytest.raises(ValueError,match='wrong base model inventory'):
        export_bundle(ckpt,target,base_inventory={'files':[],'sha256':identity([])},protocol=protocol)
    assert not target.exists()
    with pytest.raises(ValueError,match='wrong protocol'):
        export_bundle(ckpt,target,base_inventory=inventory,protocol={'wrong':'p'})
    assert not target.exists()
    export_bundle(ckpt,target,base_inventory=inventory,protocol=protocol)
    assert (target/'identity.json').is_file()


def test_explicit_target_in_prompt_is_never_allowed():
    route={'dataset':'r2r','source_split':'train','scene':'s','instruction_id':'1','family':'f',
           'path':['a','b'],'instruction':'go','source_sha256':'f'*64,'partition':'train'}
    event={'event_id':'e','route_key':'r2r:s:1','source_split':'train','rollout_id':'r',
           'call_id':1,'prompt':'<BEGIN_OF_ACTION>turn left', 'target_text':'<BEGIN_OF_ACTION>turn left',
           'image_paths':['x']*8,'image_call_ids':[1]*8,'protocol_identity':'p'}
    with pytest.raises(ValueError,match='leaked'):
        validate_events([route],[event])
