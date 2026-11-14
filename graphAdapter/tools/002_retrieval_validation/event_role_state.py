"""Fixed-state role annotations for a verified collision and changed viewpoint; no navigation policy."""
from pathlib import Path
import sys,json,hashlib,gzip,tarfile,io,time
from contextlib import nullcontext
import numpy as np
import torch
from PIL import Image
from llava.model.builder import load_pretrained_model
from llava.constants import IMAGE_TOKEN_INDEX
from llava.mm_utils import process_images,tokenizer_image_token,KeywordsStoppingCriteria
from graphAdapter.map_memory.retrieval.input_audit import separate_attachment_encoding

def run(root):
    work=Path('outputs/graph_memory/graph002-work-20261113')
    state=work/'validation/context-read/revisit-2182'
    bind=json.loads((state/'binding.json').read_text());spec=json.loads((state/'replay-input.json').read_text())
    record=spec['recorded'];cur=bind['step'];prior=bind['old_step']
    registry=Path('outputs/graph_memory/candidate_detached_correction001-20261113/simulator-quality15-reuse-v3/control/REUSED_SHADOWS.json')
    d=Path(next(v['result']for v in json.loads(registry.read_text()).values()if v['member']==bind['member']))
    with gzip.open(d/'observation_packets.jsonl.gz','rt') as stream:pk=[json.loads(l)for l in stream][:cur+1]
    mat=lambda i:np.asarray(pk[i]['pose_record']['T_odom_base'])
    assert all(v['pose_record']['valid'] and v['pose_record']['episode_instance']==bind['same_pose_chart'] and v['pose_record']['map_version']==0 for v in pk)
    assert record['frame']==cur and pk[prior]['action']['collision']is True
    native=set(bind['native_image_steps'])
    # First completed turn at the same position, following the previous blocked observation.
    changed=next(i for i in range(prior+1,cur)if i not in native and pk[i]['action']['action_id'] in (2,3)
        and pk[i]['action']['collision']is False and pk[i]['action']['primitive_index']==pk[i]['action']['primitive_count']
        and np.linalg.norm(mat(i)[:3,3]-mat(prior)[:3,3])<.08)
    assert prior not in native
    with tarfile.open(d/'final-map.tar.gz','r|gz')as ar:
        need={f"observations/{pk[i]['frame_uid']}.rgb.png":i for i in (prior,changed)}
        extra={}
        for m in ar:
            if m.name in need:extra[need[m.name]]=Image.open(io.BytesIO(ar.extractfile(m).read())).convert('RGB')
            if len(extra)==2:break
    images=[Image.open(state/'images'/(h+'.png')).convert('RGB')for h in record['images']]
    ph=lambda pic:hashlib.sha256(pic.mode.encode()+str(pic.size).encode()+pic.tobytes()).hexdigest()
    collision_slots=[i for i,h in enumerate(record['images'],1)if h==ph(extra[prior])]
    assert ph(extra[changed]) not in record['images']
    turn=mat(prior)[:3,:3].T@mat(changed)[:3,:3];angle=round(np.rad2deg(np.arctan2(turn[1,0],turn[0,0])))
    assert angle>0
    prompt=record['prompt'];marker='<|eot_id|><|start_header_id|>assistant';prefix,tail=prompt.rsplit(marker,1)
    tail=marker+tail
    collision=dict(role='past_forward_collision',observation_step=prior,executed_action='forward',reported_result='collision')
    alternate=dict(role='past_changed_viewpoint',observation_step=changed,relative_to_collision_view=f'{angle} degrees left',
                   executed_action='turn',reported_result='completed rotation')
    context=dict(current_step=cur,historical_step=prior,estimated_revisit=True,recent_consecutive_forward_collisions=bind['consecutive_collisions'])
    def block(entry):return json.dumps(entry,separators=(',',':'))
    desc='\nGraph memory:\n'+block(context)+'\n'+block(collision)+'\n'+block(alternate)
    def material(entry):
        return prefix+desc+'\nHistorical photograph for '+entry['role']+' at step '+str(entry['observation_step'])+': <image>'+tail
    reuse=prefix+desc+f"\nThe collision photograph has identical pixels to native image {collision_slots[0]}."+tail if collision_slots else None
    conditions=[('recorded_exact',prompt,None),('roles_text',prefix+desc+tail,None),(('collision_native_reference',reuse,None) if collision_slots else ('collision_photo',material(collision),prior)),
        ('changed_viewpoint_photo',material(alternate),changed)]
    tok,model,proc,_=load_pretrained_model('/data/zy/vln/case2/models/awarevln','awarevln',device_map={'':0})
    model.config.reason_token_id=tok.convert_tokens_to_ids('<BEGIN_OF_REASONING>');model.config.act_token_id=tok.convert_tokens_to_ids('<BEGIN_OF_ACTION>')
    model=model.cuda().eval();native_tensor=process_images(images,proc,model.config).half().cuda()
    assert hashlib.sha256(native_tensor.cpu().contiguous().numpy().tobytes()).hexdigest()==record['processed_image_sha256']
    proj=[]
    def hook(_,args,y):proj.append(dict(shape=list(y.shape),hash=hashlib.sha256(y.contiguous().view(torch.uint8).cpu().numpy().tobytes()).hexdigest()))
    callback=model.get_mm_projector().register_forward_hook(hook)
    results=[];root.mkdir(parents=True,exist_ok=True)
    try:
        for name,prompt,frame in conditions:
            proj.clear()
            tensor=native_tensor if frame is None else torch.cat((native_tensor,process_images([extra[frame]],proc,model.config).half().cuda()))
            ids=tokenizer_image_token(prompt,tok,IMAGE_TOKEN_INDEX,return_tensors='pt').unsqueeze(0).cuda()
            assert (ids==IMAGE_TOKEN_INDEX).sum().item()==len(tensor)
            budget=ids.numel()+195*len(tensor)
            assert budget+256<=model.llm.config.tokenizer_model_max_length
            stop=KeywordsStoppingCriteria([record['stop_str']],tok,ids)
            with torch.inference_mode(), (nullcontext()if frame is None else separate_attachment_encoding(model,8)):
                out=model.generate(ids,images=tensor,do_sample=False,temperature=0.,max_new_tokens=256,use_cache=True,
                    stopping_criteria=[stop],pad_token_id=tok.eos_token_id)
            if name=='recorded_exact':assert ids.tolist()==record['input_ids'] and out.tolist()==record['output_ids']
            assert [p['shape'][0]for p in proj]==([8]if frame is None else [8,1])
            assert not results or proj[0]['hash']==results[0]['projections'][0]['hash']
            answer=tok.batch_decode(out,skip_special_tokens=False)[0]
            results.append(dict(condition=name,attachment_step=frame,generated=answer,projections=list(proj),expanded_tokens=budget))
            print(name,answer,flush=True)
    finally:callback.remove()
    (root/'role-replay.json').write_text(json.dumps(dict(member=bind['member'],call_id=record['call_id'],context=context,
        evidence=[collision,alternate],native_pixel_matches_for_collision=collision_slots,frames={i:pk[i]['frame_uid'] for i in (prior,changed)},conditions=results,
        selection='Existing first revisit and first following completed turn at same position; no evaluation fields in prompt',
        scope='one fixed-state diagnostic'),indent=2))
if __name__=='__main__':run(Path(sys.argv[1]))

