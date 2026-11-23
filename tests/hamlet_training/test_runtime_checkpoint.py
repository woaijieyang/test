import json
from types import SimpleNamespace
import pytest
import torch
from test_models import tiny
from awarevln_memory.training.artifacts import write_json,identity
from awarevln_memory.training.checkpoints import file_inventory,save_modules,load_modules,read_identity,verify_parent,export_bundle
from hamlet_v2.trained_runtime import TrainedHAMLETRuntime,bundle_identity
from hamlet_v2.model import HAMLETMemoryMixin

class NativeTextHarness:
    """Test-only native-style wrapper around the REAL tiny HF language model."""
    _base_reason_act_token_ids=HAMLETMemoryMixin._base_reason_act_token_ids
    _select_last_context_tokens=staticmethod(HAMLETMemoryMixin._select_last_context_tokens)
    def __init__(self,llm):self.llm=llm.eval();self.config=SimpleNamespace(reason_token_id=2,act_token_id=3)
    def get_llm(self):return self.llm
    def get_lm_head(self):return self.llm.lm_head
    def get_input_embeddings(self):return self.llm.get_input_embeddings()
    def generate(self,input_ids,images=None,**kwargs):
        assert images is None
        mask=kwargs.pop('attention_mask',torch.ones_like(input_ids))
        return self.llm.generate(inputs_embeds=self.get_input_embeddings()(input_ids),attention_mask=mask,**kwargs)


def bundle_fixture(tmp_path,router=False):
    llm,m=tiny();base=tmp_path/'test-base-identity.txt';base.write_text('synthetic test fixture; not deployed weights')
    inv=file_inventory([base]);protocol={'visual_frames':8,'temporal_total_slots':4,'history_past_calls':3}
    contract={'base_identity':inv['sha256'],'protocol_identity':identity(protocol),'data_identity':'test-fixture'}
    tcl=save_modules(tmp_path/'tcl',m,stage='tcl',contract=contract)
    m.reader.injection.alpha.data.fill_(.25)
    rd=save_modules(tmp_path/'reader',m,stage='reader',contract=contract,parent_sha=tcl['checkpoint_sha256'])
    source=tmp_path/'reader'
    if router:
        m.router.none_head.bias.data.fill_(1000.)
        save_modules(tmp_path/'router',m,stage='router',contract=contract,parent_sha=rd['checkpoint_sha256'])
        source=tmp_path/'router'
    export_bundle(source,tmp_path/'bundle',base_inventory=inv,protocol=protocol,use_router=router)
    return NativeTextHarness(llm),m,contract


def test_checkpoint_parent_integrity_and_exclusive_save(tmp_path):
    model,m,contract=bundle_fixture(tmp_path)
    with pytest.raises(ValueError):verify_parent('router',tmp_path/'tcl')
    with pytest.raises(ValueError):load_modules(tmp_path/'reader',expected_base='wrong')
    with pytest.raises(FileExistsError):save_modules(tmp_path/'reader',m,stage='reader',contract=contract,parent_sha='x')
    (tmp_path/'reader'/'memory.safetensors').write_bytes(b'changed')
    with pytest.raises(ValueError):read_identity(tmp_path/'reader')


def test_runtime_empty_read_mode_lock_and_clean_write(tmp_path):
    model,m,contract=bundle_fixture(tmp_path)
    runtime=TrainedHAMLETRuntime(model,tmp_path/'bundle',tmp_path/'trace.jsonl')
    ids=torch.tensor([[1,5,7,8,9]])
    kwargs=dict(do_sample=False,max_new_tokens=2,pad_token_id=0,eos_token_id=30)
    base=model.generate(ids,**kwargs)
    first=runtime.generate(episode='e',call_id=1,frame=0,input_ids=ids,images=None,**kwargs)
    assert torch.equal(first,base)
    runtime.action_decision(2,1)
    assert runtime.state.events[-1]['executed_actions']==[]
    runtime.record_executed_action(2)
    assert runtime.state.events[-1]['executed_actions']==[2]
    second=runtime.generate(episode='e',call_id=2,frame=1,input_ids=ids,images=None,**kwargs)
    clean=runtime.modules.moment(model.llm,model.get_input_embeddings()(ids),torch.ones_like(ids,dtype=torch.bool))[0]
    assert torch.equal(clean,runtime.state.events[-1]['moment'])
    rows=[json.loads(x) for x in (tmp_path/'trace.jsonl').read_text().splitlines()]
    assert [r['injected'] for r in rows if r['event']=='read']==[False,True]
    runtime.end_episode('e')
    reset=runtime.generate(episode='new',call_id=1,frame=0,input_ids=ids,images=None,**kwargs)
    assert torch.equal(reset,base)
    runtime.close()


def test_router_none_is_exact_native_generation(tmp_path):
    model,_,_=bundle_fixture(tmp_path,router=True)
    runtime=TrainedHAMLETRuntime(model,tmp_path/'bundle',tmp_path/'trace.jsonl')
    ids=torch.tensor([[1,5,7,8,9]]);kw=dict(do_sample=False,max_new_tokens=2,pad_token_id=0,eos_token_id=30)
    runtime.generate(episode='e',call_id=1,frame=0,input_ids=ids,images=None,**kw)
    result=runtime.generate(episode='e',call_id=2,frame=1,input_ids=ids,images=None,**kw)
    assert torch.equal(result,model.generate(ids,**kw))
    runtime.close()


def test_bundle_scoped_and_changed_base_rejected(tmp_path):
    model,m,c=bundle_fixture(tmp_path)
    bound=bundle_identity(tmp_path,tmp_path/'bundle')
    assert bound['method']=='hamlet-trained'
    with pytest.raises(ValueError):bundle_identity(tmp_path/'other',tmp_path/'bundle')
    (tmp_path/'test-base-identity.txt').write_text('changed')
    with pytest.raises(ValueError):TrainedHAMLETRuntime(model,tmp_path/'bundle',tmp_path/'bad.jsonl')
