"""Compare original, text, and image+text at one sealed, identical observation."""
import sys,json,hashlib,io,tarfile,gzip,time
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from llava.model.builder import load_pretrained_model
from llava.mm_utils import process_images,tokenizer_image_token,KeywordsStoppingCriteria
from llava.constants import IMAGE_TOKEN_INDEX
from graphAdapter.map_memory.retrieval.host_input_compiler import attachment_suffix

def run(output):
    r=Path('/data/zy/vln/case2/outputs/graph_memory')
    state=r/'graph002-work-20261113/validation/context-read/rxr_us'
    replay=json.loads((state/'replay-input.json').read_bytes())
    model_call=replay['recorded'];coverage=json.loads((state/'coverage.json').read_text())['offered'][0]
    fact=coverage['facts'][0];d=next((r/'graph002-additive-small-01').glob('results/0ab*/shadow/attempt0'))
    uid,idx=fact['refs'][0].split(':d');step=fact['steps'][0]
    with tarfile.open(d/'final-map.tar.gz','r|gz') as archive:
        source=None;detection=None
        for m in archive:
            if m.name=='observations/'+uid+'.rgb.png':source=archive.extractfile(m).read()
            if m.name=='detections/'+uid+'.npz':
                with np.load(io.BytesIO(archive.extractfile(m).read()),allow_pickle=False)as z:detection=int(z['class_id'][int(idx)])
            if source is not None and detection is not None:break
    vocab=list(dict.fromkeys(v.strip()for v in Path('vendor_sources/EvoMemNav/data/scannet200_classes.txt').read_text().splitlines() if v.strip() and v.strip()!='unknown'))
    label=vocab[detection];assert label=='bed'
    extra=Image.open(io.BytesIO(source)).convert('RGB')
    imgs=[Image.open(state/'images'/(h+'.png')).convert('RGB') for h in model_call['images']]
    ph=lambda im:hashlib.sha256(im.mode.encode()+str(im.size).encode()+im.tobytes()).hexdigest()
    assert ph(extra)not in model_call['images']
    original=dict(replay['variants'])['native_visual_only']
    assert original.count('<image>')==len(imgs)==8
    prefix,suffix=original.rsplit('<|eot_id|><|start_header_id|>assistant',1);suffix='<|eot_id|><|start_header_id|>assistant'+suffix
    text=f'At step {step}, the detector recorded a possible {label}.'
    plain=prefix+attachment_suffix(step,text,with_image=False)+suffix
    visual=prefix+attachment_suffix(step,text,with_image=True)+suffix
    tok,model,proc,_=load_pretrained_model('/data/zy/vln/case2/models/awarevln','awarevln',device_map={'':0})
    model.config.reason_token_id=tok.convert_tokens_to_ids('<BEGIN_OF_REASONING>');model.config.act_token_id=tok.convert_tokens_to_ids('<BEGIN_OF_ACTION>')
    model=model.cuda().eval();assert model.config.num_video_frames==8
    native=process_images(imgs,proc,model.config).to(model.device,dtype=torch.float16)
    assert hashlib.sha256(native.cpu().numpy().tobytes()).hexdigest()==model_call['processed_image_sha256']
    pack=process_images([*imgs,extra],proc,model.config).to(model.device,dtype=torch.float16)
    assert torch.equal(native,pack[:8])
    proj=[];native_proj=None
    def observe(_,args,out):
        nonlocal native_proj
        if native_proj is None:native_proj=out.detach().clone()
        same=torch.equal(native_proj,out[:8]) if len(out)>=8 else None;maxdiff=(native_proj-out[:8]).abs().max().item() if len(out)>=8 else None
        proj.append(dict(shape=list(out.shape),native_projection_bit_exact=same,max_abs_delta=maxdiff))
    handle=model.get_mm_projector().register_forward_hook(observe)
    from graphAdapter.map_memory.retrieval.input_audit import separate_attachment_encoding
    from contextlib import nullcontext
    opts=[('recorded_exact',model_call['prompt'],native),('native_original',original,native),('structured_text',plain,native),('structured_text_and_source_photo',visual,pack),('separate_visual_encoding',visual,pack)]
    data=[];output.mkdir(parents=True,exist_ok=True)
    try:
        for name,prompt,tensor in opts:
            ids=tokenizer_image_token(prompt,tok,IMAGE_TOKEN_INDEX,return_tensors='pt').unsqueeze(0).cuda()
            positions=(ids[0]==IMAGE_TOKEN_INDEX).nonzero().flatten().tolist()
            assert len(positions)==len(tensor) and (not data or positions[:8]==data[0]['placeholder_positions'][:8])
            stop=KeywordsStoppingCriteria([model_call['stop_str']],tok,ids);torch.cuda.synchronize();start=time.perf_counter()
            split=name=='separate_visual_encoding'
            pos=len(proj)
            with torch.inference_mode(), (separate_attachment_encoding(model,8) if split else nullcontext()):generated=model.generate(ids,images=tensor,do_sample=False,temperature=0.,max_new_tokens=256,use_cache=True,stopping_criteria=[stop],pad_token_id=tok.eos_token_id)
            torch.cuda.synchronize();wall=time.perf_counter()-start
            if name=='recorded_exact':assert generated.tolist()==model_call['output_ids'] and ids.tolist()==model_call['input_ids']
            blocks=proj[pos:]
            assert [b['shape'][:2]for b in blocks]==([[8,196],[1,196]] if split else [[len(tensor),196]])
            if split:assert blocks[0]['native_projection_bit_exact']
            out=tok.batch_decode(generated,skip_special_tokens=False)[0]
            data.append(dict(condition=name,observed=blocks,native_visual_unchanged=torch.equal(tensor[:8],native),
                generated=out,placeholder_positions=positions,text_and_image_placeholder_ids=ids.numel(),vision_tokens=len(tensor)*196,
                expanded_prompt_tokens=ids.numel()+195*len(tensor),generation_seconds=wall));print(name,out,proj[-1],flush=True)
    finally:handle.remove()
    (output/'results.json').write_text(json.dumps(dict(member='RxR-US 10035',call_id=model_call['call_id'],current_step=model_call['frame'],attachment_step=step,
        detection_ref=fact['refs'][0],attachment_file_sha256=hashlib.sha256(source).hexdigest(),scope='Single fixed host state; projected inputs and actual generation',conditions=data),indent=2))
if __name__=='__main__':run(Path(sys.argv[1]))

