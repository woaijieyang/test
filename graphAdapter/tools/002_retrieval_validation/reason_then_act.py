"""Remove the extra record at frozen REASON/ACT boundaries without changing prior reasoning."""
import json,hashlib,sys
from pathlib import Path
import torch
from PIL import Image
from llava.model.builder import load_pretrained_model
from llava.constants import IMAGE_TOKEN_INDEX
from llava.mm_utils import process_images,tokenizer_image_token,KeywordsStoppingCriteria

def run(folder):
    states=json.loads((folder/'states.json').read_bytes())
    tok,model,processor,_=load_pretrained_model('/data/zy/vln/case2/models/awarevln','awarevln',device_map={'':0})
    model.config.reason_token_id=tok.convert_tokens_to_ids('<BEGIN_OF_REASONING>');model.config.act_token_id=tok.convert_tokens_to_ids('<BEGIN_OF_ACTION>')
    model=model.cuda().eval();tensors={};report=[]
    for state in states:
        row=state['row'];key=tuple(row['images'])
        if key not in tensors:
            rgbs=[]
            for h in key:
                with Image.open(Path(state['visual_dir'])/(h+'.png'))as im:rgbs.append(im.convert('RGB'))
            tensors[key]=process_images(rgbs,processor,model.config).to(model.device,dtype=torch.float16)
        tensor=tensors[key]
        assert hashlib.sha256(tensor.cpu().contiguous().numpy().tobytes()).hexdigest()==row['processed_image_sha256']
        for label,prompt in [('recorded',row['prompt']),('without_supplement',state['without'])]:
            ids=tokenizer_image_token(prompt,tok,IMAGE_TOKEN_INDEX,return_tensors='pt').unsqueeze(0).cuda()
            if label=='recorded':assert ids.tolist()==row['input_ids']
            stop=KeywordsStoppingCriteria([row['stop_str']],tok,ids)
            with torch.inference_mode():
                output=model.generate(ids,images=tensor,do_sample=False,temperature=0.,max_new_tokens=256,use_cache=True,stopping_criteria=[stop],pad_token_id=tok.eos_token_id)
            exact=output.tolist()==row['output_ids']
            if label=='recorded' and not exact:raise RuntimeError('Source generation not reproduced')
            text=tok.batch_decode(output,skip_special_tokens=False)[0]
            report.append(dict(member=state['member'],call_id=state['call_id'],frame=state['frame'],condition=label,
                identical_to_recorded=exact,raw=text,visual_hash=row['processed_image_sha256']))
            print(state['member'],state['call_id'],label,exact,text[:120],flush=True)
            (folder/'outcomes.json').write_text(json.dumps(report,indent=2))
if __name__=='__main__':run(Path(sys.argv[1]))

