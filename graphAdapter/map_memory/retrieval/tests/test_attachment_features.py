import pytest
import torch
from graphAdapter.map_memory.retrieval.input_audit import AttachmentFeatureCache
from graphAdapter.map_memory.storage.archive import IntegrityError

class TinyTower(torch.nn.Module):
    select_layer=-2
    select_feature='cls_patch'
    def __init__(self):
        super().__init__()
        self.scale=torch.nn.Parameter(torch.tensor(1.0))
    def forward(self,x):return x*self.scale

def test_attachment_cache_identity_eviction_and_weight_change():
    t=TinyTower().eval();c=AttachmentFeatureCache(16);a=torch.tensor([1.,2.]);b=torch.tensor([7.,8.])
    with torch.no_grad():
        assert c.bind(t,('ep','session'))
        initial=c.feature(t,a,'a')
        assert torch.equal(initial,c.feature(t,a,'a')) and (c.hits,c.encodes,c.bytes)==(1,1,16)
        with pytest.raises(IntegrityError):c.feature(t,b,'a')
        c.feature(t,b,'b');assert list(c.items)==['b']
        t.scale.add_(2);c.bind(t,('ep','session'))
        assert not c.items and torch.equal(c.feature(t,b,'b'),3*b)
        c.bind(t,('ep','other'));assert not c.items
        c.feature(t,a,'a');t.train();assert not c.bind(t,('ep','other')) and not c.items
    assert not c.bind(t.eval(),('ep','session'))
    c.clear();assert c.bytes==0

def test_feature_too_large_is_recomputed():
    t=TinyTower().eval();c=AttachmentFeatureCache(1)
    with torch.no_grad():
        c.bind(t,('ep','session'))
        for _ in range(2):c.feature(t,torch.ones(4),'same')
        assert not c.items and c.bytes==c.hits==0 and c.encodes==2
