"""Read-set fingerprint regressions; synthetic fixtures only, no navigation data."""
import json
import pytest
import torch
from safetensors.torch import save_file
from awarevln_memory.training.artifacts import digest
from awarevln_memory.training.cache import FeatureStore


def test_readset_identity_follows_exact_feature_and_metadata_bytes(tmp_path):
    contract = {'base_identity': 'base', 'protocol_identity': 'protocol', 'source_identity': 'train'}
    store = FeatureStore(tmp_path / 'cache', contract, create=True)
    meta = {'source_split': 'train', 'dataset': 'rxr', 'language': 'en-US',
            'partition': 'train', 'route_key': 'rxr:scene:train1'}
    store.put('used', {'prompt': torch.tensor([[1.0, 2.0]])}, meta)
    first = store.readset_identity(['used', 'used'], partition='train')
    assert first['count'] == 1
    # Growing a cache with unrelated data must not invalidate a known run.
    store.put('unused', {'prompt': torch.tensor([[9.0, 0.0]])}, meta)
    assert store.readset_identity(['used'], partition='train') == first
    with pytest.raises(ValueError, match='crosses'):
        store.readset_identity(['used'], partition='memory-dev')
    with pytest.raises(ValueError, match='empty'):
        store.readset_identity([], partition='train')

    # Simulate an operator replacing BOTH a payload and its sidecar metadata.
    # Both are internally consistent, so existing FeatureStore.get alone cannot
    # distinguish this from the original training data.
    stem = store._stem('used')
    tensor_path, meta_path = stem.with_suffix('.safetensors'), stem.with_suffix('.json')
    save_file({'prompt': torch.tensor([[3.0, 4.0]])}, str(tensor_path))
    doc = json.loads(meta_path.read_text())
    doc['file_sha256'] = digest(tensor_path)
    meta_path.write_text(json.dumps(doc))
    assert torch.equal(store.get('used', partition='train')[0]['prompt'],
                       torch.tensor([[3.0, 4.0]]))
    assert store.readset_identity(['used'], partition='train')['sha256'] != first['sha256']


def test_readset_rejects_corrupt_feature_even_with_valid_metadata(tmp_path):
    store = FeatureStore(tmp_path / 'cache',
                         {'base_identity': 'b', 'protocol_identity': 'p', 'source_identity': 's'}, create=True)
    store.put('x', {'moment': torch.ones(4, 8)},
              {'source_split': 'train', 'dataset': 'r2r', 'partition': 'train'})
    store._stem('x').with_suffix('.safetensors').write_bytes(b'broken')
    with pytest.raises(ValueError, match='changed payload'):
        store.readset_identity(['x'], partition='train')


def test_route_join_alone_cannot_relabel_unverified_rollout(tmp_path):
    from awarevln_memory.training.rollouts import extract_rollout
    from awarevln_memory.training.artifacts import write_jsonl, identity
    route = {'dataset':'r2r','scene':'s','instruction_id':'1','source_split':'train',
             'language':None,'family':identity(['s',['v1','v2']]),'source_sha256':'a'*64,
             'path':['v1','v2'],'instruction':'Turn left'}
    # Not even a full match to an official train route can establish the
    # source split of an otherwise anonymous episode recording.
    raw = {'event_id':'x','rollout_id':'roll','call_id':1,'prompt':'<image>',
           'image_paths':['f.png']*8,'image_call_ids':[1]*8,'protocol_identity':'p',
           'scan':'s','instruction_id':'1','dataset':'r2r'}
    path=tmp_path/'unverified.jsonl';write_jsonl(path,[raw])
    fields={k:k for k in ('event_id','rollout_id','call_id','prompt',
                         'image_paths','image_call_ids','protocol_identity')}
    mapping={'fields':fields,'route_join':{'scene':'scan','instruction_id':'instruction_id','dataset':'dataset'}}
    accepted,rejected=extract_rollout(path,[route],mapping)
    assert not accepted and rejected[0]['reason']=='ROLLOUT_SPLIT_UNVERIFIED'
    raw['source_split']='train'
    verified_path=tmp_path/'verified.jsonl';write_jsonl(verified_path,[raw])
    accepted,rejected=extract_rollout(verified_path,[route],mapping)
    assert not rejected and len(accepted)==1


def test_deployment_refuses_clean_moment_precision_drift():
    from awarevln_memory.training.artifacts import require_clean_encoding_dtype
    require_clean_encoding_dtype('float16', torch.float16)
    require_clean_encoding_dtype('bfloat16', torch.bfloat16)
    # An older incomplete synthetic fixture without this key is still readable;
    # production bootstrap always records the required dtype.
    require_clean_encoding_dtype(None, torch.float32)
    with pytest.raises(ValueError, match='dtype mismatch'):
        require_clean_encoding_dtype('float16', torch.bfloat16)
    with pytest.raises(ValueError, match='unsupported'):
        require_clean_encoding_dtype('fp8', torch.float16)


def test_workspace_bootstrap_failure_does_not_claim_output(tmp_path):
    from awarevln_memory.training.bootstrap import initialize
    output = tmp_path / 'training-output'
    with pytest.raises(FileNotFoundError):
        initialize(tmp_path / 'workspace-without-preflight', output)
    assert not output.exists()


def test_native_precision_contract_and_training_plan():
    from pathlib import Path
    import yaml
    plan = yaml.safe_load((Path(__file__).resolve().parents[2] / 'configs/hamlet/training/plan.yaml').read_text())
    assert plan['tcl']['mixed_precision'] == 'no'
    assert plan['reader']['mixed_precision'] == 'no'
    assert plan['router']['mixed_precision'] == 'no'
    # Training must explicitly load the same dtype as clean prompt encoding,
    # not just rely on the CUDA-side BF16 default from load_llm().
    import inspect
    from awarevln_memory.training import runner
    source=inspect.getsource(runner.run)
    assert 'clean_encoding=True' in source
    assert 'BF16 autocast cannot be mixed' in source
