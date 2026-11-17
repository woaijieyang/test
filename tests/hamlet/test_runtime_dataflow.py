import json
from types import SimpleNamespace
import pytest
import torch
from transformers import GPT2Config,GPT2LMHeadModel
from awarevln_memory.config import MemoryAdapterConfig
from awarevln_memory.memory.adapter import AwareVLNMemoryAdapter
from awarevln_memory.cbem.config import CBEMConfig
from awarevln_memory.cbem.router import CBEMRouter
from hamlet_v2.model import HAMLETMemoryMixin
from hamlet_v2.runtime import HAMLETRuntime

class TinyModel(HAMLETMemoryMixin):
    def __init__(self):
        self.llm=GPT2LMHeadModel(GPT2Config(vocab_size=32,n_embd=16,n_inner=32,n_layer=1,n_head=2,n_positions=32,bos_token_id=1,eos_token_id=2,pad_token_id=0)).eval()
        self.config=SimpleNamespace(reason_token_id=3,act_token_id=4)
        self.memory_adapter=AwareVLNMemoryAdapter(MemoryAdapterConfig(llm_hidden_size=16,memory_hidden_size=8,moment_tokens=4,memory_layers=1,memory_heads=2,recent_calls=2,max_event_items=2,output_memory_tokens=4,max_age=8,dropout=0.0,alpha_init=0.25)).eval()
        self.cbem_router=CBEMRouter(CBEMConfig(adapter_hidden_size=8,rank=4,memory_types=3,max_age=8,prefilter_top_k=4,selected_top_k=2,archive_capacity=8,none_logit_init=-20)).eval()
    @property
    def device(self):return torch.device('cpu')
    @property
    def dtype(self):return next(self.llm.parameters()).dtype
    def get_input_embeddings(self):return self.llm.get_input_embeddings()
    def get_lm_head(self):return self.llm.lm_head

def runtime(tmp_path):
    torch.manual_seed(10)
    obj=HAMLETRuntime.__new__(HAMLETRuntime);obj.model=TinyModel();obj.stream=(tmp_path/'flow.jsonl').open('x');obj.config={}
    obj.episode=None;obj.state=None;obj.calls=obj.turns=obj.fallback_remaining=0
    return obj

def generate(obj,call,episode='A'):
    return obj.generate(episode=episode,call_id=call,frame=call-1,input_ids=torch.tensor([[1,4,5,6,7,8]]),images=None,do_sample=False,max_new_tokens=2,pad_token_id=0)

def records(tmp_path):return [json.loads(l) for l in (tmp_path/'flow.jsonl').read_text().splitlines()]

def test_actual_prefill_uses_adapted_prompt_and_prior_memory(tmp_path):
    obj=runtime(tmp_path);generate(obj,1);obj.action_decision(1,1);generate(obj,2);obj.action_decision(0,2);obj.end_episode('A');obj.close()
    rows=records(tmp_path);inputs=[r for r in rows if r['kind']=='memory_input'];calls=[r for r in rows if r['kind']=='memory_generation']
    assert inputs[0]['archive_items']==[]
    assert inputs[1]['archive_items'][0]['policy_call_id']==0
    assert inputs[1]['archive_items'][0]['moment']==calls[0]['stored_moment']
    assert calls[1]['selected_item_ids']==['archive_000000']
    assert calls[1]['prompt_max_abs_delta']>0
    assert all(c['adapted_prompt']==c['generation_prefill'] for c in calls)
    assert rows[-1]['kind']=='terminal_reset' and rows[-1]['archive_after_clear']==0

def test_turn_fallback_is_two_calls_and_does_not_stop_memory_writes(tmp_path):
    obj=runtime(tmp_path)
    for call in range(1,6):
        generate(obj,call);obj.action_decision(2 if call<=3 else 1,call)
    rows=records(tmp_path);inputs=[r for r in rows if r['kind']=='memory_input'];calls=[r for r in rows if r['kind']=='memory_generation']
    assert [r['fallback_active'] for r in inputs]==[False,False,False,True,True]
    assert inputs[3]['fallback_triggered'] and not inputs[4]['fallback_triggered']
    assert len(obj.state.archive)==5
    assert calls[3]['prompt_max_abs_delta']==0 and calls[4]['prompt_max_abs_delta']==0
    obj.end_episode('A');obj.close()

def test_episode_reset_clears_archive_and_fallback(tmp_path):
    obj=runtime(tmp_path);generate(obj,1);obj.turns=3;obj.fallback_remaining=2;obj.end_episode('A');generate(obj,1,'B')
    rows=records(tmp_path);last=[r for r in rows if r['kind']=='memory_input'][-1]
    assert last['episode_id']=='B' and last['archive_items']==[] and not last['fallback_active']
    obj.end_episode('B');obj.close()

def test_missing_reset_and_call_misalignment_are_rejected(tmp_path):
    obj=runtime(tmp_path);generate(obj,1)
    with pytest.raises(RuntimeError,match='before explicit memory reset'):generate(obj,1,'B')
    with pytest.raises(RuntimeError,match='call IDs diverged'):generate(obj,3)
    obj.end_episode('A');obj.close()

def test_actual_consumption_guard_rejects_a_different_prefill(tmp_path):
    obj=runtime(tmp_path)
    def corrupt(module,args,kwargs):
        if kwargs.get('inputs_embeds') is not None:kwargs=dict(kwargs);kwargs['inputs_embeds']=kwargs['inputs_embeds']+1
        return args,kwargs
    hook=obj.model.llm.register_forward_pre_hook(corrupt,with_kwargs=True)
    with pytest.raises(RuntimeError,match='did not consume'):generate(obj,1)
    hook.remove();obj.stream.close()
