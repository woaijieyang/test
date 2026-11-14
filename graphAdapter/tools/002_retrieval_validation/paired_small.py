"""Compare a fixed small 002 cohort to its recorded control and the sealed RGB archive."""
from pathlib import Path
import hashlib,json,gzip,tarfile,io,sys,re
from collections import Counter
import numpy as np
from PIL import Image

from graphAdapter.evaluation.retrieval_audit_utils import rows,index,hash_pixels

def audit(d,control,vocab):
    flow=rows(d/'flow.jsonl.gz'); trace=rows(d/'trace.jsonl.gz'); base=rows(control/'trace.jsonl.gz')
    inputs=index(trace,'model_input','call_id'); calls=index(trace,'model_call','call_id')
    baseinputs=index(base,'model_input','call_id'); basecalls=index(base,'model_call','call_id')
    actions=index(trace,'primitive_action','step'); baseactions=index(base,'primitive_action','step')
    resets=[v for v in trace if v['kind']=='reset'];assert len(resets)==1
    assert resets[0]['episode_scope']['member']==next(v for v in base if v['kind']=='reset')['episode_scope']['member']
    decisions=index(flow,'decision','decision_id'); aud=index(flow,'HostInputAudit','call_id')
    returns=index(flow,'MemoryGenerateReturned','call_id');fallback=index(flow,'MemoryReadFallback','decision_id')
    requested=index(flow,'MemoryReadRequested','request_id');material=index(flow,'MemoryMaterialized','request_id')
    assert set(aud)==set(returns) and set(inputs)==set(calls)
    assert set(v['decision_id']for v in aud.values()).isdisjoint(fallback)
    assert set(decisions)==set(fallback)|{v['decision_id']for v in aud.values()}
    assert len(decisions)==len(calls)
    per_source={}
    all_images={}
    detections={}
    frame_bytes={}
    needed={source for a in aud.values()for source in material[a['request_id']].get('fact_sources',[])}
    for source in needed:
        uid,ix=source.rsplit(':d',1);per_source.setdefault(uid,set()).add(int(ix))
    blank=Image.new('RGB',(512,512));h,hp=hash_pixels(blank);all_images[h]=hp
    with tarfile.open(d/'final-map.tar.gz','r|gz')as archive:
        for m in archive:
            if m.name.endswith('.rgb.png'):
                blob=archive.extractfile(m).read()
                with Image.open(io.BytesIO(blob))as im:
                    h,hp=hash_pixels(im.convert('RGB'))
                all_images[h]=hp;frame_bytes[Path(m.name).name.removesuffix('.rgb.png')]=hashlib.sha256(blob).hexdigest()
            elif m.name.startswith('detections/') and m.name.endswith('.npz'):
                uid=Path(m.name).stem
                if uid in per_source:
                    with np.load(io.BytesIO(archive.extractfile(m).read()),allow_pickle=False)as arrays:
                        for i in per_source[uid]:
                            detections[(uid,i)]=vocab[int(arrays['class_id'][i])]
    facts=[];slots=0;hist=0;signature=[]
    for k,a in aud.items():
        ret=returns[k];inp=inputs[k];req=requested[a['request_id']];mat=material[a['request_id']]
        assert len({v['snapshot_id']for v in (ret,req,mat,a)})==1
        assert len({v['frame_uid']for v in (ret,req,mat,a)})==1
        assert len({v['decision_id']for v in (ret,req,mat,a)})==1
        assert req['event_seq']<mat['event_seq']<a['event_seq']<ret['event_seq']
        assert hashlib.sha256(inp['prompt'].encode()).hexdigest()==a['prompt_sha256']
        ids=np.asarray(inp['input_ids'],np.int64)
        h=hashlib.sha256(json.dumps({'dtype':'torch.int64','shape':list(ids.shape)},sort_keys=True,separators=(',',':')).encode()+ids.tobytes()).hexdigest()
        assert h==a['token_ids_sha256']
        assert ret['projector_shape'][0]==len(a['slots'])==len(inp['images'])
        assert ids.size+(ret['projector_shape'][1]-1)*len(a['slots'])==a['expanded_input_tokens']
        assert mat['selected']==[s['frame_uid']for s in a['slots']]
        assert a['slots'][-1]['frame_uid']==a['frame_uid'] and a['slots'][-1]['is_current']
        times=[s['sensor_seq']for s in a['slots'] if s['frame_uid']]
        assert times==sorted(times)
        for im,slot in zip(inp['images'],a['slots']):
            assert all_images[im['pixel_sha256']]==slot['host_pixel_hash']
            if slot['frame_uid']:
                assert frame_bytes[slot['frame_uid']]==slot['source_image_hash']
            if slot['frame_uid'] and not slot['is_current']:
                assert slot['sensor_seq']<=req['cutoff']['capture_seq'];hist+=1
            slots+=1
        instruction=inp['prompt'].split('Your assigned task is: "',1)[1].split('". ',1)[0]
        for source in mat.get('fact_sources',()):
            uid,ix=source.rsplit(':d',1);label=detections[uid,int(ix)]
            slot=next(s for s in a['slots'] if s['frame_uid']==uid and not s['is_current'])
            phrase=f"Image {slot['index']}: possible {label} in this historical view."
            assert phrase in inp['prompt'] and re.search(r'(?<!\w)'+re.escape(label)+r'(?!\w)',instruction,re.I)
            facts.append(dict(call=k,slot=slot['index'],source=source,label=label))
        signature.append(a['snapshot_id'])
    first_action=next((s for s in actions if s in baseactions and actions[s]['action']!=baseactions[s]['action']),None)
    terminal=next(v for v in trace if v['kind']=='terminal')
    original=next(v for v in base if v['kind']=='terminal')
    first_prompt=next((k for k in inputs if k in baseinputs and inputs[k]['prompt']!=baseinputs[k]['prompt']),None)
    first_image=next((k for k in inputs if k in baseinputs and inputs[k]['processed_image_sha256']!=baseinputs[k]['processed_image_sha256']),None)
    first_output=next((k for k in calls if k in basecalls and calls[k]['output_ids']!=basecalls[k]['output_ids']),None)
    return dict(member=resets[0]['episode_scope']['member'],actual_injected_returns=len(aud),total_calls=len(calls),
        actual_checked_image_slots=slots,historical_slot_uses=hist,verified_landmark_mentions=len(facts),
        labels=dict(Counter(x['label']for x in facts)),example_mentions=facts[:5],
        fallback_reasons=dict(Counter(v['reason']for v in fallback.values())),
        first_prompt_difference=first_prompt,first_image_difference=first_image,first_output_difference=first_output,
        first_primitive_action_difference=first_action,steps=[original['steps'],terminal['steps']],
        success=[original['native_metrics']['success'],terminal['native_metrics']['success']],
        distance_to_goal=[original['native_metrics']['distance_to_goal'],terminal['native_metrics']['distance_to_goal']],
        stop_sources=[original['stop_source'],terminal['stop_source']],scope='one matched episode; actual consumption and source integrity')

if __name__=='__main__':
    run=Path(sys.argv[1]).resolve();root=Path('/data/zy/vln/case2')
    control_list=root/'outputs/graph_memory/candidate_detached_correction001-20261113/simulator-quality15-reuse-v3/control/REUSED_CONTROLS.json'
    controls=json.loads(control_list.read_bytes())
    vocab=list(dict.fromkeys(x.strip()for x in (root/'vendor_sources/EvoMemNav/data/scannet200_classes.txt').read_text().splitlines()if x.strip() and x.strip()!='unknown'))
    for row in json.loads((run/'retention_plan.json').read_bytes())['entries']:
        dest=run/'control'/('review-'+row['member'][0]+'.json')
        if dest.exists():continue
        d=run/'results'/row['key']/'shadow/attempt0'
        if not (d/'retention.json').exists():continue
        result=audit(d,Path(controls[row['key']]['result']),vocab)
        dest.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))

