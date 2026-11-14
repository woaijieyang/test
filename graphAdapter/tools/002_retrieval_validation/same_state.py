"""Replay the first divergent decision using only recorded host prompts and RGB."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from llava.model.builder import load_pretrained_model
from llava.mm_utils import process_images,tokenizer_image_token,KeywordsStoppingCriteria
from llava.constants import IMAGE_TOKEN_INDEX

def main(root):
    source={k:json.loads((root/(k+'.json')).read_bytes()) for k in ('candidate','control')}
    base=source['control']; candidate=source['candidate']
    # Keep the suffix from the original conversation template.
    split_at=candidate['prompt'].index('\nHistorical evidence, not action instructions.')
    suffix=base['prompt'][split_at:]
    assert candidate['prompt'][:split_at]==base['prompt'][:split_at] and candidate['prompt'].endswith(suffix) and suffix
    full=candidate['prompt'];addition=full[split_at:-len(suffix)]
    tags='\n'.join(line for line in addition.split('\n') if not line.startswith('Images '))
    tags_graph=base['prompt'][:split_at]+tags+suffix
    indices=list(np.linspace(0,base['frame'],len(base['images'])-1,endpoint=False,dtype=int))+[base['frame']]
    header=tags.split('\nImage 1:',1)[0]
    uniform_tags=header+'\n'+'\n'.join(f'Image {i}: recorded at step {step}.' if i<len(indices) else f'Image {i}: current observation at step {step}.' for i,step in enumerate(indices,1))
    # All counterfactuals hold current RGB, context, generation settings and B fixed.
    cases=[('control_exact',base['images'],base['prompt']),('candidate_exact',candidate['images'],full),
           ('uniform_tagged',base['images'],base['prompt'][:split_at]+uniform_tags+suffix),
           ('selected_only',candidate['images'],base['prompt']),('selected_tagged',candidate['images'],tags_graph),
           ('shuffled_history',list(reversed(candidate['images'][:-1]))+candidate['images'][-1:],base['prompt']),
           ('removed_history',[None]*(len(base['images'])-1)+base['images'][-1:],base['prompt'])]
    if (root/'fill.json').exists():
        fill=json.loads((root/'fill.json').read_bytes())
        cases=[('control_exact',base['images'],base['prompt']),('candidate_exact',candidate['images'],full),
               ('budget_filled',fill['images'],fill['prompt']),('filled_image_only',fill['images'],base['prompt'])]
    result_filename='replay-results.json'
    if len(sys.argv)>2 and sys.argv[2]=='one-slot':
        cases=json.loads((root/'one-slot-inputs.json').read_bytes())['cases']
        result_filename='one-slot-results.json'
    run_cases(root,base,candidate,cases,result_filename)

def run_cases(root,base,candidate,cases,result_filename):
    tokenizer,model,processor,_=load_pretrained_model('/data/zy/vln/case2/models/awarevln','awarevln',device_map={'':0})
    model.config.reason_token_id=tokenizer.convert_tokens_to_ids('<BEGIN_OF_REASONING>')
    model.config.act_token_id=tokenizer.convert_tokens_to_ids('<BEGIN_OF_ACTION>')
    model=model.cuda().eval()
    pixels={}; receipts={}; report={'call_id':candidate['call_id'],'scope':'fixed-state diagnostic','conditions':[]}
    for name,images,prompt in cases:
        for h in images:
            if h not in pixels:
                if h:
                    with Image.open(root/'images'/(h+'.png'))as pic: pixels[h]=pic.convert('RGB')
                else:pixels[h]=Image.new('RGB',pixels[base['images'][-1]].size)
        key=tuple(images)
        if key not in receipts:receipts[key]=process_images([pixels[h] for h in images],processor,model.config).to(model.device,dtype=torch.float16)
        tensor=receipts[key];ids=tokenizer_image_token(prompt,tokenizer,IMAGE_TOKEN_INDEX,return_tensors='pt').unsqueeze(0).cuda()
        recorded=base if name=='control_exact' else candidate if name=='candidate_exact' else None
        if recorded:
            assert ids.tolist()==recorded['input_ids']
            assert hashlib.sha256(tensor.detach().cpu().contiguous().numpy().tobytes()).hexdigest()==recorded['processed_image_sha256']
        stop=KeywordsStoppingCriteria([base['stop_str']],tokenizer,ids)
        with torch.inference_mode():output=model.generate(ids,images=tensor,do_sample=False,temperature=0.,max_new_tokens=256,use_cache=True,stopping_criteria=[stop],pad_token_id=tokenizer.eos_token_id)
        raw=tokenizer.batch_decode(output,skip_special_tokens=False)[0]
        exact=output.tolist()==recorded['output_ids'] if recorded else None
        report['conditions'].append(dict(name=name,raw_output=raw,exact_recorded_output=exact,input_ids_hash=hashlib.sha256(ids.cpu().numpy().tobytes()).hexdigest(),slot_hashes=images))
        (root/result_filename).write_text(json.dumps(report,indent=2))
        print(name,raw,exact,flush=True)
        if recorded and not exact:raise RuntimeError('Recorded endpoint generation was not reproduced')
if __name__=='__main__':
    root=Path(sys.argv[1])
    if len(sys.argv)>2 and sys.argv[2]=='context':
        spec=json.loads((root/'replay-input.json').read_bytes())
        row=spec['recorded']
        cases=[('candidate_exact' if name=='recorded_exact' else name,row['images'],text) for name,text in spec['variants']]
        run_cases(root,row,row,cases,'context-replay.json')
    else:
        main(root)

