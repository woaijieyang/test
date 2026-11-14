from types import SimpleNamespace
import pytest
import torch
from graphAdapter.evaluation.language_prefill import observe_language_prefill
from graphAdapter.map_memory.storage.store import IntegrityError


def test_prefill_rejects_wrong_slot_and_omitted_text_even_when_projector_shape_matches():
    class Language(torch.nn.Module):
        def forward(self,*,inputs_embeds,attention_mask,position_ids):
            return inputs_embeds
    language=Language();projector=torch.nn.Identity();embedding=torch.nn.Embedding(7,4)
    model=SimpleNamespace(get_llm=lambda:language,get_mm_projector=lambda:projector,get_input_embeddings=lambda:embedding)
    token=-200;ids=torch.tensor([[2,token,3,token,4]])
    visual=torch.arange(16,dtype=torch.float32).reshape(2,2,4)
    def process(mode):
        with observe_language_prefill(model,ids,token) as record:
            blocks=projector(visual)
            if mode=='swap':blocks=blocks.flip(0)
            t=embedding(torch.tensor([2,3,4]))
            seq=torch.cat((t[:1],blocks[0],t[1:2],blocks[1],t[2:]))
            if mode=='truncate':seq=seq[:-1]
            if mode=='replace_text':seq=seq.clone();seq[-1]=t[0]
            mask=torch.ones((1,len(seq)),dtype=torch.bool)
            if mode=='mask':mask[0,2]=False
            language(inputs_embeds=seq[None],attention_mask=mask,position_ids=torch.arange(len(seq))[None])
        return record
    assert process('pass')['image_segments']==[[1,3],[4,6]]
    for mode in ('swap','truncate','replace_text','mask'):
        with pytest.raises(IntegrityError):process(mode)
        assert not language._forward_pre_hooks and not projector._forward_hooks
