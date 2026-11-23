"""Reuse native AwareVLN tokenizer/image preparation; no fabricated observations."""
from __future__ import annotations
import math
from pathlib import Path
import torch
from .artifacts import digest, identity, training_path
from .cache import FeatureStore
from .data import trusted_label


def prepare_event(model,tokenizer,image_processor,event,*,augment=False,seed=42,encoding_contract=None):
    from PIL import Image,ImageEnhance,ImageFilter
    from llava.mm_utils import process_images,tokenizer_image_token
    from llava.constants import IMAGE_TOKEN_INDEX
    import random
    if event.get('source_split')!='train':raise ValueError('only train events may be cached')
    if len(event['image_paths'])!=8:raise ValueError('eight-frame protocol required')
    if event['prompt'].count('<image>')!=8:raise ValueError('prompt must contain original eight image slots')
    if event.get('prompt_contains_target',False):raise ValueError('current target in prompt')
    if (isinstance(event.get('target_text'),str) and event['target_text']
            and event['target_text'] in event['prompt']):
        raise ValueError('current target text leaked into prompt')
    images=[];hashes=[]
    for path in event['image_paths']:
        path=training_path(path)
        with Image.open(path) as image:images.append(image.convert('RGB'))
        hashes.append(digest(path))
    augmentation=None
    if augment:
        rng=random.Random(identity([seed,event['event_id']]))
        brightness=rng.uniform(.95,1.05)
        images[-1]=ImageEnhance.Brightness(images[-1]).enhance(brightness).filter(ImageFilter.GaussianBlur(.2))
        augmentation={'type':'current_frame_brightness_blur','brightness':brightness,'blur_radius':.2,'seed':seed}
    llm=model.get_llm();device=next(llm.parameters()).device;dtype=next(llm.parameters()).dtype
    pixels=process_images(images,image_processor,model.config)
    if isinstance(pixels,list):pixels=[p.to(device=device,dtype=dtype) for p in pixels]
    else:pixels=pixels.to(device=device,dtype=dtype)
    ids=tokenizer_image_token(event['prompt'],tokenizer,IMAGE_TOKEN_INDEX,return_tensors='pt').unsqueeze(0).to(device)
    with torch.no_grad():
        _,_,mask,_,embeddings,_=model.prepare_inputs_labels_for_multimodal(ids,None,None,None,None,pixels)
    if embeddings is None:raise ValueError('native multimodal preparation returned no embeddings')
    if mask is None:mask=torch.ones(embeddings.shape[:2],dtype=torch.bool,device=device)
    prompt=embeddings[0,mask[0].bool()].detach().cpu()
    metadata={k:event[k] for k in ('event_id','route_key','rollout_id','call_id','source_split','dataset','language','partition','scene','family','input_identity','image_call_ids')}
    capture_protocol=event['protocol_identity']
    encoding_contract=encoding_contract or {}
    metadata.update(image_sha256=hashes,clean_encoding_dtype=str(dtype).removeprefix('torch.'),
                    executed_actions=event.get('executed_actions',[]),
                    executed_actions_available='executed_actions' in event,
                    protocol_identity=encoding_contract.get('protocol_identity',capture_protocol),
                    capture_protocol_identity=capture_protocol,verified_target=False,
                    mode_compatible=False,baseline_correct=False)
    # Key includes observed pixels, not merely path names; stale pixels invalidate downstream caches.
    metadata['input_identity']=identity([event['input_identity'],hashes,augmentation])
    tensors={'prompt':prompt}
    if augment:
        metadata.update(augmentation_of=event['event_id'],augmentation=augmentation)
    elif trusted_label(event) and event.get('target_kind') in ('act','reason'):
        kind=event['target_kind'];target=event['target_text']
        mode_token=getattr(model.config,'act_token_id' if kind=='act' else 'reason_token_id',None)
        if mode_token is None:raise ValueError('original mode token IDs must be initialized before preprocessing')
        target_ids=tokenizer(target,add_special_tokens=False,return_tensors='pt').input_ids[0]
        if not len(target_ids) or int(target_ids[0])!=mode_token:
            metadata['target_error']='MISSING_NATIVE_MODE_TOKEN';return tensors,metadata
        # Termination is explicit in the trace/annotation contract, never invented from prose.
        stop_text=event.get('stop_text')
        if not stop_text:
            metadata['target_error']='MISSING_CONVERSATION_STOP_TEXT';return tensors,metadata
        if not target.endswith(stop_text):
            target_ids=tokenizer(target+stop_text,add_special_tokens=False,return_tensors='pt').input_ids[0]
        with torch.no_grad():
            base_mode=model._base_reason_act_token_ids(embeddings,mask)
        metadata.update(verified_target=True,mode_compatible=int(base_mode[0])==mode_token,
                        target_source=event['target_source'],target_provenance=event['target_provenance'],
                        target_sha256=identity(target),
                        baseline_correct=bool(event.get('baseline_correct_verified',False) and
                            (event.get('baseline_check_provenance') or {}).get('base_identity')==encoding_contract.get('base_identity') and
                            encoding_contract.get('base_identity')))
        tensors['target_ids']=target_ids
    return tensors,metadata


def build_prompt_cache(model,tokenizer,image_processor,events,store,triplets=()):
    positives={r['anchor']:r['augmentation_seed'] for r in triplets}
    report={'events':0,'positives':0,'mode_conflicts':0,'failures':[]}
    for key,event in sorted(events.items()):
        try:
            data,meta=prepare_event(model,tokenizer,image_processor,event,encoding_contract=store.contract)
            store.put(key,data,meta);report['events']+=1
            if meta['verified_target'] and not meta['mode_compatible']:report['mode_conflicts']+=1
            if key in positives:
                data,meta=prepare_event(model,tokenizer,image_processor,event,augment=True,seed=positives[key],encoding_contract=store.contract)
                store.put(key+'::positive',data,meta);report['positives']+=1
        except (OSError,ValueError) as exc:
            report['failures'].append({'event_id':key,'error':str(exc)})
    return report


def build_moment_cache(llm,modules,event_keys,prompt_store,moment_store):
    if not moment_store.contract.get('moment_checkpoint_sha256'):raise ValueError('frozen moment identity required')
    modules.moment.requires_grad_(False);modules.moment.eval();llm.eval()
    device=next(llm.parameters()).device;dtype=next(llm.parameters()).dtype
    expected=moment_store.contract.get('clean_encoding_dtype')
    if expected and str(dtype).removeprefix('torch.')!=expected:raise ValueError('moment cache/deployment precision mismatch')
    count=0
    for key in event_keys:
        data,meta=prompt_store.get(key)
        p=data['prompt'].to(device=device,dtype=dtype)[None]
        with torch.no_grad():moment=modules.moment(llm,p,torch.ones(p.shape[:2],dtype=torch.bool,device=device))[0]
        moment_store.put(key,{'moment':moment},meta);count+=1
    return {'cached_events':count}


def audit_cache_coverage(rows,store,stage,moment_store=None,*,mask_missing_past=False):
    """Report missing/corrupt assets; only explicit missing-past repair is allowed."""
    from .datasets import StageDataset
    accepted=[];rejected=[]
    for original in rows:
        row=dict(original)
        try:
            if mask_missing_past and stage=='reader':
                past=list(row['past']);repairs=[]
                for index,key in enumerate(past):
                    if key is None:continue
                    try:moment_store.get(key,partition=row['partition'])
                    except FileNotFoundError as exc:
                        # Never hide stale/corrupt/cross-split features as missing.
                        repairs.append({'slot':index,'event_id':key,'reason':'MISSING_PAST_FEATURE','detail':str(exc)})
                        past[index]=None
                if repairs:
                    row['past']=past;row['missing_past_repairs']=repairs
            dataset=StageDataset([row],store,stage,row['partition'],moment_store=moment_store)
            dataset[0];accepted.append(row)
        except (OSError,ValueError,KeyError) as exc:
            rejected.append({'record_id':row.get('window_id',row.get('anchor')),'reason':str(exc)})
    return accepted,rejected


def select_cache_events(events,triplets,windows):
    """Only encode references actually consumed by selected windows/triplets."""
    lookup={e['event_id']:e for e in events}
    if len(lookup)!=len(events):raise ValueError('duplicate observed event identity')
    needed=set()
    for row in triplets:
        needed.update((row['anchor'],row['negative']))
    for row in windows:
        needed.add(row['current']);needed.update(k for k in row['past'] if k is not None)
    missing=needed-set(lookup)
    if missing:raise ValueError('referenced observation identities missing: '+str(sorted(missing)[:10]))
    return {key:lookup[key] for key in sorted(needed)}
