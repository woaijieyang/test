import ast
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
import torch
from graphAdapter.map_memory.retrieval.tests.test_host_input_compiler import prepared
from graphAdapter.map_memory.retrieval.input_audit import observe_process_images,audit_final_inputs
from graphAdapter.map_memory.storage.archive import IntegrityError

class Processor:
    image_mean=(0.,0.,0.)
    crop_size={'height':8,'width':8}
    def __init__(self,crops=1):self.calls=0;self.crops=crops
    def preprocess(self,image,return_tensors):
        self.calls+=1
        a=torch.from_numpy(np.array(image).copy()).permute(2,0,1).float()/255
        if self.crops>1:a=torch.stack([a+i for i in range(self.crops)])
        return {'pixel_values':a.unsqueeze(0)}

def original_process_images():
    path=Path('/data/zy/vln/case2/src/llava/mm_utils.py');tree=ast.parse(path.read_text())
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name in ('process_image','process_images')]
    from PIL import Image
    namespace={'torch':torch,'Image':Image}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    return namespace['process_images']

def tokenize(prompt):return torch.tensor([1]+[-200]*prompt.count('<image>')+[2,3])
def inputs(crops=1):
    history=prepared();processor=Processor(crops);cfg=SimpleNamespace(image_aspect_ratio='resize')
    tensor,receipt=observe_process_images(history,processor,cfg,process_images=original_process_images())
    prompt='original task '+('<image> '*8)
    return history,processor,tensor.half(),receipt,prompt,tokenize(prompt).unsqueeze(0)
def audit(args,**kw):
    h,p,t,r,text,ids=args
    values=dict(history=h,receipt=r,images_tensor=t,prompt=text,input_ids=ids,
        tokenize_prompt=tokenize,original_question='original task',image_token_id=-200,
        generation_config={'max_new_tokens':16,'do_sample':False},vision_tokens_per_slot=[4]*8,context_limit=100)
    values.update(kw);return audit_final_inputs(**values)

def test_R06_exact_native_preprocessing_runs_once_and_final_cast_is_audited():
    args=inputs();result=audit(args)
    assert args[1].calls==8
    assert result['status']=='VERIFIED_FINAL_INPUT_MATERIALS'
    assert result['expanded_input_tokens']==35 and result['reserved_generation_tokens']==16
    assert [row['tensor_range']for row in result['slots']]==[[i,i+1]for i in range(8)]
    assert result['slots'][-1]['frame_uid']=='f4'


def test_R06_multiple_crops_have_explicit_ranges_not_false_frame_counts():
    args=inputs(crops=3);result=audit(args)
    assert args[1].calls==8 and result['crop_count']==24
    assert result['slots'][-1]['tensor_range']==[21,24]
    assert result['logical_image_slots']==8


def test_swapped_actual_tensor_is_rejected_even_when_shape_is_unchanged():
    args=inputs();wrong=args[2].clone();wrong[5],wrong[6]=args[2][6],args[2][5]
    with pytest.raises(IntegrityError):audit(args,images_tensor=wrong)


def test_truncated_token_input_or_missing_original_text_is_rejected():
    args=inputs()
    with pytest.raises(IntegrityError):audit(args,input_ids=args[5][:,:-1])
    with pytest.raises(IntegrityError):audit(args,original_question='lost original instruction')


def test_model_context_accounts_for_vision_tokens_and_generation_reservation():
    args=inputs()
    with pytest.raises(IntegrityError):audit(args,context_limit=50)
    result=audit(args,vision_tokens_per_slot=None)
    assert result['status']=='VERIFIED_MATERIALS_PENDING_VISION_BUDGET'
    assert result['expanded_input_tokens'] is None


def test_R12_privileged_text_and_image_sentinels_fail_closed():
    args=inputs()
    with pytest.raises(IntegrityError):audit(args,forbidden_texts=('original task',))
    with pytest.raises(IntegrityError):audit(args,forbidden_pixel_hashes=(args[0].slots[-1].host_pixel_hash,))


def test_modified_materialized_pixels_are_rejected_before_preprocess():
    history=prepared();history.images[-1].putpixel((0,0),(9,9,9))
    processor=Processor()
    with pytest.raises(IntegrityError):observe_process_images(history,processor,SimpleNamespace(image_aspect_ratio='resize'),process_images=original_process_images())
    assert processor.calls==0



def test_host_compile_binds_exact_prompt_and_native_fallback_tensor(monkeypatch):
    from graphAdapter.map_memory.retrieval import host_decision as host
    hist=prepared()
    dec=host.HostDecision(None,{},'facts_only',{})
    # Budget rejection removes the selected material during compile.
    dec.history=hist;dec.emit=lambda *a,**k:None
    def reject(*args):
        dec.use_uniform('no_supplement_within_budget')
        return args[0]
    dec.compile=reject
    native=list(reversed(hist.images))
    api=host.HostInjection(dec,native,8,lambda xs,**k:list(xs))
    q='original task '+('<image> '*8);template=lambda s:'wrapper '+s
    assert api.compile(q,template,None,None,None)==q and api.images==native
    tensor=api.preprocess(Processor(),SimpleNamespace(image_aspect_ratio='resize'),original_process_images(),
                          cast_to_model=lambda t:t.half())
    def generation(prompt,value,tokens=None):
        return api.generation(model=None,call_id=1,images_tensor=value,prompt=prompt,
                              input_ids=tokenize(prompt).unsqueeze(0) if tokens is None else tokens,
                              tokenize_prompt=tokenize,image_token_id=-200,generation_config={})
    prompt=template(q)
    with generation(prompt,tensor):pass
    with pytest.raises(IntegrityError,match='compiled decision'):generation(prompt+' stale',tensor)
    with pytest.raises(IntegrityError):generation(prompt,tensor,tokenize(prompt).unsqueeze(0)[:,:-1])
    with pytest.raises(IntegrityError,match='dtype'):generation(prompt,tensor.float())
    with pytest.raises(IntegrityError,match='differs'):generation(prompt,tensor.flip(0))
    tensor.add_(1)
    with pytest.raises(IntegrityError,match='mutated'):generation(prompt,tensor)


def test_normal_generation_rejects_unsourced_text_before_projection():
    from graphAdapter.map_memory.retrieval import host_decision as host
    hist=prepared();dec=host.HostDecision(None,{},'facts_only',{})
    dec.history=hist;dec.compile=lambda *a:a[0]+' allowed'
    api=host.HostInjection(dec,hist.images,8,None)
    api.compile('original',lambda q:'wrapper '+q,None,None,None)
    with pytest.raises(IntegrityError,match='compiled decision'):
        api.generation(model=None,call_id=1,images_tensor=None,prompt='wrapper original allowed OTHER',
                       input_ids=None,tokenize_prompt=None,image_token_id=-200,generation_config={})
