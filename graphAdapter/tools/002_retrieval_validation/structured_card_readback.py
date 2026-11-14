"""Audit the exact native RGB prefix, attachment, structured fields, tokens and returned call."""
import json,gzip,hashlib,tarfile,io,sys
from pathlib import Path
from collections import Counter
import numpy as np
from PIL import Image
from graphAdapter.evaluation.retrieval_audit_utils import rows,index,hash_pixels
from graphAdapter.interfaces.host_slots import native_slot_indices
from graphAdapter.map_memory.storage.store import clip_detection_box

def audit(run,prev,original):
    entry,=json.loads((run/'retention_plan.json').read_bytes())['entries'];key=entry['key']
    result=lambda r:r/'results'/key/'shadow/attempt0'
    d=result(run);t=rows(d/'trace.jsonl.gz');f=rows(d/'flow.jsonl.gz')
    ctrls=json.loads((original/'control/REUSED_CONTROLS.json').read_bytes())
    bas=rows(Path(ctrls[key]['result'])/'trace.jsonl.gz'); prior=rows(result(prev)/'trace.jsonl.gz')
    ms=index(t,'model_call','call_id');pr=index(prior,'model_call','call_id');bc=index(bas,'model_call','call_id')
    ps={p['capture_seq']:p for p in rows(d/'observation_packets.jsonl.gz')}
    au=index(f,'HostInputAudit','call_id');ret=index(f,'MemoryGenerateReturned','call_id')
    compiled=index(f,'MemoryAttachmentCompiled','request_id');requested=index(f,'MemoryReadRequested','request_id')
    mats=index(f,'MemoryMaterialized','request_id');pub=index(f,'PublishedSnapshot','snapshot_id')
    triggers=index(f,'EvoReadTrigger','decision_id')
    fallback=[v for v in f if v['kind']=='MemoryReadFallback']
    assert set(au)==set(ret) and len(ms)==len(au)+len(fallback)
    hashes={};detections={};attached={v['attachment_frame'] for v in compiled.values()}
    with tarfile.open(d/'final-map.tar.gz','r|gz')as archive:
        for m in archive:
            if m.name.endswith('.rgb.png'):
                data=archive.extractfile(m).read()
                with Image.open(io.BytesIO(data))as im:
                    hashes[Path(m.name).name[:-len('.rgb.png')]]=(*hash_pixels(im.convert('RGB')),hashlib.sha256(data).hexdigest(),im.size)
            elif m.name.startswith('detections/') and m.name.endswith('.npz') and Path(m.name).stem in attached:
                with np.load(io.BytesIO(archive.extractfile(m).read()),allow_pickle=False)as z:
                    detections[Path(m.name).stem]=(z['class_id'].copy(),z['xyxy'].copy())
    blank=hash_pixels(Image.new('RGB',(512,512)))[0]
    vocab=list(dict.fromkeys(x.strip()for x in Path('vendor_sources/EvoMemNav/data/scannet200_classes.txt').read_text().splitlines()if x.strip() and x.strip()!='unknown'))
    facts=[];slots=0
    for k,m in ms.items():
        n=m['frame']+1;ids=native_slot_indices(n,8);expected=[hashes[ps[i+1]['frame_uid']][0]if i is not None else blank for i in ids]
        assert [im['pixel_sha256']for im in m['images'][:8]]==expected;slots+=8
        assert len(m['images'])==(9 if k in au else 8) and m['input_ids'][0].count(-200)==len(m['images'])
        if k not in au:continue
        a=au[k];rid=a['request_id'];c=compiled[rid];rec=c['model_fields'];q=requested[rid];v=ret[k]
        assert a['native_image_slots']==8 and a['memory_attachment_slots']==1 and a['current_native_image_index']==8
        assert v['projector_batches']==[[8,196,4096],[1,196,4096]]
        assert mats[rid]['replaced_slots']==[] and mats[rid]['selected']==mats[rid]['native_slots']
        assert c['model_suffix']in m['prompt'] and hashlib.sha256(m['prompt'].encode()).hexdigest()==a['prompt_sha256']
        assert json.loads(c['model_suffix'].splitlines()[2])==rec
        token=np.asarray(m['input_ids'],np.int64);tag=json.dumps(dict(dtype='torch.int64',shape=list(token.shape)),sort_keys=True,separators=(',',':')).encode()
        assert hashlib.sha256(tag+token.tobytes()).hexdigest()==a['token_ids_sha256']
        assert c['snapshot_id']==q['snapshot_id']==a['snapshot_id']==v['snapshot_id'] and c['attachment_step']+1<=q['cutoff']['capture_seq']
        assert pub[c['snapshot_id']]['event_seq']<triggers[a['decision_id']]['event_seq']<q['event_seq']<c['event_seq']<a['event_seq']<v['event_seq']
        uid=c['attachment_frame'];ref,=c['source_refs'];src,idx=ref.rsplit(':d',1);assert uid==src==ps[c['attachment_step']+1]['frame_uid']
        cl,box=detections[uid];i=int(idx);h,hp,sha,size=hashes[uid]
        assert h==m['images'][8]['pixel_sha256'] and h not in expected and a['slots'][8]['host_pixel_hash']==hp and sha==c['source_image_hash']
        assert rec['instruction_landmark']==vocab[int(cl[i])] and rec['detector_region_xyxy_pixels']==list(clip_detection_box(box[i],(size[1],size[0])))
        assert rec['photo_width_height']==list(size) and rec['observed_step']==c['attachment_step'] and rec['current_step']==m['frame']
        assert rec['current_image_slot']==8 and rec['historical_photo_slot']==9
        facts.append(dict(call=k,trigger=triggers[a['decision_id']]['trigger'],fields=rec,output=m['normalized_output'],
            prior_same_images=k in pr and [i['pixel_sha256']for i in m['images']]==[i['pixel_sha256']for i in pr[k]['images']]))
    return dict(member=entry['member'],calls=len(ms),read_events=len(requested),attachments=len(facts),native_slots_verified=slots,
        sources=facts,fallbacks=dict(Counter(v['reason']for v in fallback)),
        first_output_difference_from_caption=next((k for k in ms if k in pr and ms[k]['output_ids']!=pr[k]['output_ids']),None),
        metrics={k:[tr[-1]['native_metrics'][k]for tr in (bas,prior,t)]for k in ('success','spl','steps_taken','distance_to_goal')},scope='one development episode, columns original/caption/structured')
if __name__=='__main__':
    run,prev,original=map(Path,sys.argv[1:]);res=audit(run,prev,original);(run/'control/card-audit.json').write_text(json.dumps(res,indent=2));print(json.dumps(res))

