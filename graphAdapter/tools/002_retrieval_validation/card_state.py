"""Prepare and run a fixed-state 2x2 comparison using the sealed, actually delivered attachment."""
from pathlib import Path
import json,tarfile,io,hashlib,sys,gzip
import numpy as np
import torch
from PIL import Image
from graphAdapter.map_memory.storage.store import clip_detection_box
from graphAdapter.map_memory.retrieval.host_input_compiler import LandmarkCard
from graphAdapter.map_memory.retrieval.input_audit import separate_attachment_encoding
from contextlib import nullcontext
from llava.model.builder import load_pretrained_model
from llava.mm_utils import process_images,tokenizer_image_token,KeywordsStoppingCriteria
from llava.constants import IMAGE_TOKEN_INDEX

def run(source,out):
    d=next(source.glob('results/*/shadow/attempt0'))
    def read(name):
        with gzip.open(d/name,'rt') as stream:return [json.loads(l)for l in stream]
    flow=read('flow.jsonl.gz'); trace=read('trace.jsonl.gz')
    e=next(v for v in flow if v['kind']=='MemoryAttachmentCompiled')
    a=next(v for v in flow if v['kind']=='HostInputAudit' and v['request_id']==e['request_id'])
    m=next(v for v in trace if v['kind']=='model_call' and v['call_id']==a['call_id'])
    uid=e['attachment_frame'];idx=int(e['source_refs'][0].rsplit(':d',1)[1])
    names={f"observations/{s['frame_uid']}.rgb.png" for s in a['slots'] if s['frame_uid']}
    names.add(f'detections/{uid}.npz')
    with tarfile.open(d/'final-map.tar.gz','r|gz')as ar:
        blobs={item.name:ar.extractfile(item).read() for item in ar if item.name in names}
    imgs=[]
    for slot,im in zip(a['slots'],m['images']):
        rgb=Image.open(io.BytesIO(blobs[f"observations/{slot['frame_uid']}.rgb.png"])).convert('RGB') if slot['frame_uid'] else Image.new('RGB',tuple(im['size']))
        assert hashlib.sha256(rgb.mode.encode()+str(rgb.size).encode()+rgb.tobytes()).hexdigest()==im['pixel_sha256']
        imgs.append(rgb)
    assert len(imgs)==9 and a['slots'][7]['is_current'] and not a['slots'][8]['is_current']
    with np.load(io.BytesIO(blobs[f'detections/{uid}.npz']),allow_pickle=False)as arr:
        cls=int(arr['class_id'][idx]);box=clip_detection_box(arr['xyxy'][idx],(imgs[-1].height,imgs[-1].width))
    vocab=list(dict.fromkeys(x.strip()for x in Path('vendor_sources/EvoMemNav/data/scannet200_classes.txt').read_text().splitlines()if x.strip()and x.strip()!='unknown'))
    card=LandmarkCard.verified(vocab[cls],e['attachment_step'],m['frame'],8,box,imgs[-1].size)
    old=m['prompt'];prefix,marker,remain=old.partition('\nRetrieved memory record (historical), step')
    assert marker and prefix.count('<image>')==8
    tail=remain[remain.index('<|eot_id|>'):];anchor=remain.split('\n')[1].partition(': <image>')[0]
    full=card.suffix().replace('Historical source photograph:',anchor+' (historical source photograph):',1)
    variants=[('eight_only',prefix+tail,8),('caption_and_photo',old,9),('fields_only',prefix+card.suffix(include_image=False)+tail,8),('fields_and_photo',prefix+full+tail,9)]
    tok,model,proc,_=load_pretrained_model('/data/zy/vln/case2/models/awarevln','awarevln',device_map={'':0})
    model.config.reason_token_id=tok.convert_tokens_to_ids('<BEGIN_OF_REASONING>');model.config.act_token_id=tok.convert_tokens_to_ids('<BEGIN_OF_ACTION>')
    model=model.cuda().eval()
    x=process_images(imgs,proc,model.config).half().cuda()
    assert hashlib.sha256(x.cpu().contiguous().numpy().tobytes()).hexdigest()==m['processed_image_sha256']
    projections=[]
    def record(mod,args,y):projections.append((list(y.shape),hashlib.sha256(y.contiguous().view(torch.uint8).cpu().numpy().tobytes()).hexdigest()))
    hook=model.get_mm_projector().register_forward_hook(record)
    results=[];out.mkdir(exist_ok=True,parents=True)
    try:
        for name,prompt,n in variants:
            ids=tokenizer_image_token(prompt,tok,IMAGE_TOKEN_INDEX,return_tensors='pt').unsqueeze(0).cuda()
            pos=(ids[0]==IMAGE_TOKEN_INDEX).nonzero().flatten().tolist()
            assert len(pos)==n and (not results or pos[:8]==results[0]['placeholder_positions'][:8])
            projections.clear()
            stop=KeywordsStoppingCriteria([m['stop_str']],tok,ids)
            with torch.inference_mode(), (separate_attachment_encoding(model,8)if n==9 else nullcontext()):
                y=model.generate(ids,images=x[:n],do_sample=False,temperature=0.,max_new_tokens=256,use_cache=True,stopping_criteria=[stop],pad_token_id=tok.eos_token_id)
            if name=='caption_and_photo':assert ids.tolist()==m['input_ids'] and y.tolist()==m['output_ids']
            assert [s[0][0]for s in projections]==([8,1]if n==9 else [8])
            assert not results or projections[0][1]==results[0]['projection'][0][1]
            reply=tok.batch_decode(y,skip_special_tokens=False)[0]
            results.append(dict(condition=name,output=reply,projection=list(projections),placeholder_positions=pos,
                token_ids=ids.numel(),expanded_tokens=ids.numel()+195*n,
                native_image_identity=m['processed_image_sha256'],prompt_suffix=prompt[len(prefix):-len(tail)]))
            print(name,reply,flush=True)
    finally:hook.remove()
    (out/'results.json').write_text(json.dumps(dict(scope='one fixed-state 8 vs 8+1 diagnostic',member=trace[0]['episode_scope']['member'],
        call_id=m['call_id'],source_refs=e['source_refs'],card=card.fields(),conditions=results),indent=2))
if __name__=='__main__':run(Path(sys.argv[1]),Path(sys.argv[2]))

