"""Hash-bound CPU-readable features. No torch.load of untrusted pickle files."""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
import torch
from safetensors.torch import load_file, save_file
from .artifacts import digest, identity, write_json, training_path


class FeatureStore:
    def __init__(self, root, contract, *, create=False):
        self.root=training_path(root)
        for key in ('base_identity','protocol_identity','source_identity'):
            if not isinstance(contract.get(key),str) or not contract[key]:raise ValueError('cache contract missing '+key)
        self.contract=contract
        if create:
            self.root.mkdir(parents=True,exist_ok=False)
            write_json(self.root/'contract.json',{'schema':'hamlet.features.v1','contract':contract})
        saved=json.loads((self.root/'contract.json').read_text())
        if saved!={'schema':'hamlet.features.v1','contract':contract}:raise ValueError('stale/incompatible feature cache')

    def _stem(self, key):return self.root/identity(key)

    def put(self,key,tensors,metadata):
        if metadata.get('source_split')!='train':raise ValueError('no evaluation features in training cache')
        if metadata.get('dataset') not in ('r2r','rxr'):raise ValueError('unsupported dataset')
        if metadata['dataset']=='rxr' and metadata.get('language')!='en-US':raise ValueError('not en-US')
        if metadata.get('partition') not in ('train','memory-dev'):raise ValueError('cache partition missing')
        if not tensors or any(not isinstance(t,torch.Tensor) or not torch.isfinite(t).all() for t in tensors.values()):
            raise ValueError('invalid/nonfinite feature tensors')
        stem=self._stem(key);target=stem.with_suffix('.safetensors');meta=stem.with_suffix('.json')
        if target.exists() or meta.exists():raise FileExistsError(str(stem))
        fd,tmp=tempfile.mkstemp(dir=self.root,prefix='.feature-');os.close(fd)
        try:
            save_file({k:t.detach().cpu().contiguous() for k,t in tensors.items()},tmp)
            os.link(tmp,target)
        finally:Path(tmp).unlink(missing_ok=True)
        doc={'key':key,'contract_sha256':identity(self.contract),'file_sha256':digest(target),
             'metadata':metadata,'shapes':{k:list(t.shape) for k,t in tensors.items()}}
        try:
            write_json(meta,doc)
        except BaseException:
            # Safetensors was published first; never leave an orphaned tensor
            # that makes a later clean retry fail with FileExistsError.
            target.unlink(missing_ok=True)
            raise
        return doc

    def readset_identity(self, keys, *, partition=None):
        """Bind a training run to the exact, validated files it will consume.

        Cache *contracts* do not describe the actual contents of individual
        feature files.  This read-set is deliberately restricted to referenced
        keys, so unrelated cache growth does not invalidate a run.  Every
        tensor file is rehashed; changing a blob and its metadata together
        still changes the identity used by checkpoint/resume verification.
        """
        keys = sorted(set(keys))
        if not keys:
            raise ValueError('empty feature read-set')
        rows = []
        for key in keys:
            stem = self._stem(key)
            meta_path, data_path = stem.with_suffix('.json'), stem.with_suffix('.safetensors')
            doc = json.loads(meta_path.read_text())
            if doc.get('key') != key or doc.get('contract_sha256') != identity(self.contract):
                raise ValueError('feature read-set identity mismatch')
            if partition is not None and doc.get('metadata', {}).get('partition') != partition:
                raise ValueError('feature read-set crosses train/dev partition')
            file_hash = digest(data_path)
            if file_hash != doc.get('file_sha256'):
                raise ValueError('feature read-set contains changed payload')
            rows.append({'key': key, 'feature_sha256': file_hash,
                         'metadata_sha256': digest(meta_path)})
        return {'count': len(rows), 'sha256': identity(rows)}

    def get(self,key,*,partition=None):
        stem=self._stem(key);meta=json.loads(stem.with_suffix('.json').read_text())
        if meta['key']!=key or meta['contract_sha256']!=identity(self.contract):raise ValueError('cache identity mismatch')
        if partition is not None and meta['metadata']['partition']!=partition:raise ValueError('cross-split cache read')
        path=stem.with_suffix('.safetensors')
        if digest(path)!=meta['file_sha256']:raise ValueError('corrupt feature cache')
        data=load_file(str(path))
        if {k:list(t.shape) for k,t in data.items()}!=meta['shapes']:raise ValueError('cached tensor shape mismatch')
        if any(not torch.isfinite(t).all() for t in data.values()):raise ValueError('nonfinite cached features')
        return data,meta['metadata']
