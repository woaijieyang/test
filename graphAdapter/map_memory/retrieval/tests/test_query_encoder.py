from types import SimpleNamespace
import hashlib
import numpy as np
import pytest
import torch
from open_clip.tokenizer import SimpleTokenizer
from graphAdapter.map_memory.retrieval.query_adapter import QueryEncoder
from graphAdapter.map_memory.retrieval.contracts import MemoryQuery,CategoryVocabulary
from graphAdapter.map_memory.storage.archive import IntegrityError

class FakeCLIP(torch.nn.Module):
    context_length=11
    def __init__(self):
        super().__init__();self.weight=torch.nn.Parameter(torch.ones(1));self.calls=[]
    def encode_text(self,tokens):
        self.calls.append(tokens.detach().cpu().clone())
        x=tokens.float()
        return torch.stack((x.sum(1),x[:,1],torch.ones(len(x),device=x.device)),dim=1)

def setup(**kw):
    vocab=CategoryVocabulary.from_bytes(b'door\nchair\n')
    model=FakeCLIP().eval();tokenizer=SimpleTokenizer(context_length=11)
    models=SimpleNamespace(clip_model=model,clip_tokenizer=tokenizer,clip_model_hash='weights',
        preprocess_hash='pre',class_vocabulary_hash=vocab.ordered_labels_sha256)
    identity={'weights':{'open_clip_pytorch_model.bin':'weights'},'preprocess_hash':'pre','vocabulary_sha256':vocab.source_sha256}
    return model,models,identity,vocab

def query(instruction='Walk past the chair and stop near the door.',reasoning=None):
    return MemoryQuery('ep','snap','f2',2,2,20,instruction,last_reasoning=reasoning,
        last_reasoning_event_seq=21 if reasoning else None,decision_event_seq=22)

def test_repeated_query_reuses_model_and_exact_features_without_rng_change():
    model,models,identity,vocab=setup();encoder=QueryEncoder(models,identity,vocab,overlap=3,batch_windows=2)
    q=query();before=torch.get_rng_state().clone()
    first=encoder.encode(q);calls=len(model.calls);second=encoder.encode(q)
    assert len(model.calls)==calls and calls>0 and torch.equal(before,torch.get_rng_state())
    assert first.windows is second.windows
    assert not first.windows.flags.writeable
    assert encoder.audit(q.instruction)['covered_tokens']==len(models.clip_tokenizer.encode(q.instruction))
    assert all(x.shape[1]==11 and len(x)<=2 for x in model.calls)
    encoder.close()
    with pytest.raises(RuntimeError):encoder.encode(q)


def test_new_reasoning_does_not_reencode_full_instruction():
    model,models,identity,vocab=setup();encoder=QueryEncoder(models,identity,vocab,overlap=3)
    a=encoder.encode(query());calls=len(model.calls)
    b=encoder.encode(query(reasoning='The door is ahead.'))
    assert b.windows is a.windows and len(model.calls)>calls
    calls=len(model.calls);c=encoder.encode(query(reasoning='The door is ahead.'))
    assert len(model.calls)==calls and c.reasoning is b.reasoning

@pytest.mark.parametrize('field,value',[('clip_model_hash','wrong'),('preprocess_hash','wrong'),('class_vocabulary_hash','wrong')])
def test_model_preprocess_and_vocabulary_identity_are_bound(field,value):
    model,models,identity,vocab=setup();setattr(models,field,value)
    with pytest.raises(IntegrityError):QueryEncoder(models,identity,vocab,overlap=3)


def test_training_or_context_mismatch_is_rejected():
    model,models,identity,vocab=setup();model.train()
    with pytest.raises(IntegrityError):QueryEncoder(models,identity,vocab,overlap=3)
    model.eval();model.context_length=12
    with pytest.raises(IntegrityError):QueryEncoder(models,identity,vocab,overlap=3)


def test_zero_cache_budget_has_no_unbounded_retention():
    model,models,identity,vocab=setup();encoder=QueryEncoder(models,identity,vocab,overlap=3,max_bytes=0)
    encoder.encode(query());calls=len(model.calls);encoder.encode(query())
    assert len(model.calls)>calls and encoder.cache_bytes==0 and not encoder.cache


def test_token_range_audit_does_not_run_model_when_cache_is_disabled():
    model,models,identity,vocab=setup();encoder=QueryEncoder(models,identity,vocab,overlap=3,max_bytes=0)
    encoder.encode(query());calls=len(model.calls);encoder.audit(query().instruction)
    assert len(model.calls)==calls
