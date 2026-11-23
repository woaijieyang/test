"""Synthetic tensors are test-only. Real Hugging Face GPT2 supplies the decoder."""
import copy
import torch
import pytest
from transformers import GPT2Config,GPT2LMHeadModel
from awarevln_memory.training.models import ShortMemoryConfig,MemoryModules,StageModel,MomentEncoder,TemporalReader
from awarevln_memory.training.masks import block_causal_mask,causal_prompt_mask
from awarevln_memory.config import MemoryAdapterConfig
from awarevln_memory.memory.adapter import AwareVLNMemoryAdapter
from hamlet_v2.trained_runtime import RecentState


def tiny():
    torch.manual_seed(42)
    llm=GPT2LMHeadModel(GPT2Config(vocab_size=31,n_positions=64,n_embd=16,n_layer=1,n_head=4,
                                 attn_pdrop=0,resid_pdrop=0,embd_pdrop=0))
    modules=MemoryModules(ShortMemoryConfig(hidden_size=16,memory_size=16,heads=4,layers=1,projection_size=8,max_age=8))
    return llm,modules


def reader_batch():
    return dict(prompt=torch.randn(2,6,16),prompt_mask=torch.ones(2,6,dtype=torch.bool),
                current_moment=torch.randn(2,4,16),past_moments=torch.randn(2,3,4,16),
                past_valid=torch.tensor([[1,1,1],[0,0,0]],dtype=torch.bool),
                ages=torch.tensor([[3,2,1,0],[3,2,1,0]]),actions=torch.full((2,4),4),
                target_ids=torch.tensor([[2,3,4],[5,6,7]]),target_mask=torch.ones(2,3,dtype=torch.bool),
                kind=torch.tensor([0,1]),preserve=torch.tensor([True,False]))


def test_block_causal_same_slot_and_future():
    m=block_causal_mask(4,4)
    assert not m[:4,:4].any()
    assert m[:4,4:].all()
    assert not m[-4:].any()


def test_prompt_boundary_excludes_ignored_target_suffix():
    labels=torch.tensor([[-100,-100,3,-100,4]])
    mask=causal_prompt_mask(None,labels,None,labels.shape,labels.device)
    assert mask.tolist()==[[True,True,False,False,False]]
    with pytest.raises(ValueError):causal_prompt_mask(None,labels,torch.ones_like(labels),labels.shape,labels.device)


def test_legacy_target_changes_cannot_change_query_or_injection():
    adapter=AwareVLNMemoryAdapter(MemoryAdapterConfig(llm_hidden_size=16,memory_hidden_size=16,memory_heads=4,
                        memory_layers=1,alpha_init=.1,dropout=0)).eval()
    x=torch.randn(1,7,16);y=x.clone();y[:,3:]+=100
    labels=torch.tensor([[-100,-100,-100,4,-100,5,6]])
    memory=torch.randn(1,2,4,16)
    a=adapter(x,labels=labels,memory_moments=memory);b=adapter(y,labels=labels,memory_moments=memory)
    assert torch.equal(a.current_query,b.current_query)
    assert torch.equal(a.adapted_inputs[:,:3],b.adapted_inputs[:,:3])
    assert torch.equal(a.adapted_inputs[:,3:],x[:,3:])


@pytest.mark.parametrize('stage,prefix',[('tcl','moment.'),('reader','reader.'),('router','router.')])
def test_stage_parameter_allowlist(stage,prefix):
    llm,m=tiny();model=StageModel(llm,m,stage)
    names=[n for n,p in m.named_parameters() if p.requires_grad]
    assert names and all(n.startswith(prefix) for n in names)
    assert not any(p.requires_grad for p in llm.parameters())


def test_moment_backward_through_frozen_decoder():
    llm,m=tiny();model=StageModel(llm,m,'tcl')
    before={n:p.clone() for n,p in llm.named_parameters()}
    x=torch.randn(2,6,16);mask=torch.tensor([[1,1,1,1,1,1],[1,1,1,0,0,0]],dtype=torch.bool)
    b={k:x+(i*.2) for i,k in enumerate(('anchor','positive','negative'))}
    b.update({k+'_mask':mask for k in ('anchor','positive','negative')})
    model(**b)['loss'].backward()
    assert m.moment.tokens.grad.norm()>0
    assert all(p.grad is None and torch.equal(p,before[n]) for n,p in llm.named_parameters())


def test_moment_padding_invariant():
    llm,m=tiny();llm.eval();m.eval()
    x=torch.randn(1,4,16)
    a=m.moment(llm,x,torch.ones(1,4,dtype=torch.bool))
    padded=torch.cat([torch.full((1,3,16),999.),x,torch.full((1,2,16),-999.)],1)
    b=m.moment(llm,padded,torch.tensor([[0,0,0,1,1,1,1,0,0]],dtype=torch.bool))
    assert torch.equal(a,b)


def test_reader_zero_alpha_then_real_gradient():
    llm,m=tiny();model=StageModel(llm,m,'reader',memory_dropout=0);b=reader_batch()
    before={n:p.clone() for n,p in llm.named_parameters()}
    opt=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=.01)
    model(**b)['loss'].backward()
    assert m.reader.injection.alpha.grad.abs()>0
    opt.step();opt.zero_grad();model(**b)['loss'].backward()
    assert m.reader.down.weight.grad.norm()>0
    assert m.reader.slot.grad.norm()>0
    assert all(p.grad is None and torch.equal(p,before[n]) for n,p in llm.named_parameters())


def test_empty_memory_exact_zero_even_after_training_scale():
    _,m=tiny();m.reader.injection.alpha.data.fill_(.5)
    b=reader_batch();b['past_valid'].zero_();b['past_moments'].fill_(float('nan'))
    memory,gate,_=m.read(b['current_moment'],b['past_moments'],b['past_valid'],b['ages'],b['actions'])
    assert torch.isfinite(memory).all() and torch.count_nonzero(memory)==0
    adapted=m.reader.inject(b['prompt'],b['prompt_mask'],memory)
    assert torch.equal(adapted,b['prompt']) and gate.eq(0).all()
    adapted.sum().backward() # an all-empty DDP batch still has a valid zero-gradient graph
    assert m.reader.injection.alpha.grad is not None


def test_router_set_labels_are_separate_from_candidates():
    _,m=tiny();model=StageModel(None,m,'router')
    b=dict(query=torch.randn(2,4,16),items=torch.randn(2,3,16),valid=torch.ones(2,3,dtype=torch.bool),
           types=torch.zeros(2,3,dtype=torch.long),ages=torch.tensor([[3,2,1],[3,2,1]]),
           utility_sign=torch.zeros(2,3),set_sign=torch.tensor([1.,-1.]),set_valid=torch.ones(2,dtype=torch.bool))
    loss=model(**b)['loss'];loss.backward()
    assert torch.isfinite(loss) and m.router.none_head.weight.grad.norm()>0
    b['set_sign'].zero_();b['set_valid'].zero_()
    with pytest.raises(ValueError,match='unverified'):model(**b)


def test_state_clock_reset_and_no_proposed_action_leak():
    s=RecentState();x=torch.randn(4,16)
    past,valid,age,act=s.before('a',1,x)
    assert not valid.any();s.commit(1,x);s.executed(2)
    past,valid,age,act=s.before('a',2,x)
    assert valid.tolist()==[[False,False,True]] and act.tolist()==[[4,4,2,4]]
    s.commit(2,x)
    with pytest.raises(ValueError):s.before('a',2,x)
    _,valid,_,_=s.before('b',1,x)
    assert not valid.any()


def test_reader_preserves_four_independent_slot_gradients():
    _,m=tiny();b=reader_batch();b['past_moments'].requires_grad_(True)
    memory,_,_=m.read(b['current_moment'],b['past_moments'],b['past_valid'],b['ages'],b['actions'])
    memory.square().sum().backward()
    g=b['past_moments'].grad[0,0]
    assert not torch.allclose(g[0],g[1],atol=1e-8)


def test_checkpointing_is_actually_active_with_frozen_decoder():
    llm,m=tiny();llm.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    model=StageModel(llm,m,'reader',memory_dropout=0).train()
    assert llm.is_gradient_checkpointing and llm.transformer.training
    model(**reader_batch())['loss'].backward()
    assert m.reader.injection.alpha.grad.abs()>0
    assert all(not p.requires_grad and p.grad is None for p in llm.parameters())
    model.eval();assert not llm.training
