"""Independent audit of native images and supplementary graph records in a sealed run."""
from pathlib import Path
from collections import Counter
import hashlib,tarfile,io,json,re,gzip,sys
import numpy as np
from PIL import Image
from .retrieval_audit_utils import rows,index,hash_pixels

def audit(d,reference,vocab):
    flow=rows(d/'flow.jsonl.gz')
    trace=rows(d/'trace.jsonl.gz')
    base=rows(reference/'trace.jsonl.gz')
    packets={p['frame_uid']:p for p in rows(d/'observation_packets.jsonl.gz')}
    by_seq={v['capture_seq']:v for v in packets.values()}
    aud=index(flow,'HostInputAudit','call_id')
    decisions=index(flow,'decision','decision_id')
    extra=index(flow,'AdditionalEvidenceCompiled','request_id')
    requested=index(flow,'MemoryReadRequested','request_id')
    ret=index(flow,'MemoryGenerateReturned','call_id')
    fallback=index(flow,'MemoryReadFallback','decision_id')
    mat=index(flow,'MemoryMaterialized','request_id')
    pub=index(flow,'PublishedSnapshot','snapshot_id')
    inputs=index(trace,'model_input','call_id')
    calls=index(trace,'model_call','call_id')
    ctrl=index(base,'model_call','call_id')
    assert set(inputs)==set(calls) and set(aud)==set(ret)
    assert set(extra)=={a['request_id']for a in aud.values()}
    assert set(decisions)==set(fallback)|{a['decision_id']for a in aud.values()} and len(calls)==len(decisions)
    assert trace[0]['episode_scope']['member']==base[0]['episode_scope']['member']
    lookup={};payloads={};needed={}
    for e in extra.values():
        for f in e['records']:
            if len(f['source_refs'])==1:
                uid,ix=f['source_refs'][0].rsplit(':d',1)
                needed.setdefault(uid,set()).add(int(ix))
    with tarfile.open(d/'final-map.tar.gz','r|gz')as ar:
        for m in ar:
            if m.name.endswith('.rgb.png'):
                uid=Path(m.name).name.removesuffix('.rgb.png')
                blob=ar.extractfile(m).read()
                with Image.open(io.BytesIO(blob)) as pic:lookup[uid]=hash_pixels(pic.convert('RGB'))
            elif m.name.startswith('detections/') and m.name.endswith('.npz') and Path(m.name).stem in needed:
                uid=Path(m.name).stem
                with np.load(io.BytesIO(ar.extractfile(m).read()),allow_pickle=False)as archive:
                    for i in needed[uid]:payloads[(uid,i)]=vocab[int(archive['class_id'][i])]
    blank=hash_pixels(Image.new('RGB',(512,512)))
    nslots=0;facts=Counter();ages=[];earliest=None
    for k,x in inputs.items():
        n=x['frame']+1;count=len(x['images']);assert count==8
        pad=max(count-n,0)
        seq=[None if i<pad else int(i)-pad+1 for i in np.linspace(0,max(count,n)-1,count-1,endpoint=False,dtype=int)]+[n]
        uids=[by_seq[i]['frame_uid']if i else None for i in seq]
        for uid,im in zip(uids,x['images']):
            assert (lookup[uid] if uid else blank)[0]==im['pixel_sha256']
            nslots+=1
        if k not in aud:
            assert 'Earlier observations from memory:' not in x['prompt'];continue
        a=aud[k];rid=a['request_id'];e=extra[rid];m=mat[rid];q=requested[rid];p=pub[q['snapshot_id']]
        assert uids==m['selected']==m['native_slots'] and m['replaced_slots']==[]
        assert [s['frame_uid']for s in a['slots']]==uids
        assert p['event_seq']<q['event_seq']<m['event_seq']<e['event_seq']<a['event_seq']<ret[k]['event_seq']
        assert len({v['snapshot_id']for v in (p,q,m,e,a,ret[k])})==1
        assert len({v['decision_id']for v in (q,m,e,a,ret[k])})==1
        ids=np.array(x['input_ids'],np.int64);assert (ids==-200).sum()==count
        head=json.dumps(dict(dtype='torch.int64',shape=list(ids.shape)),sort_keys=True,separators=(',',':')).encode()
        assert hashlib.sha256(head+ids.tobytes()).hexdigest()==a['token_ids_sha256']
        assert hashlib.sha256(x['prompt'].encode()).hexdigest()==a['prompt_sha256']
        assert ret[k]['projector_shape'][0]==count and ids.size+count*(ret[k]['projector_shape'][1]-1)==a['expanded_input_tokens']
        pre,marker,suffix=x['prompt'].partition('\nEarlier observations from memory:\n')
        assert marker
        body,stop,_=suffix.partition('<|eot_id|>');assert stop
        assert body.splitlines()==[rec['text']for rec in e['records']]
        for f in e['records']:
            steps=f['steps'];refs=f['source_refs'];assert all(i<n-1 and i+1<=q['cutoff']['capture_seq'] for i in steps)
            assert any(i+1 not in seq for i in steps); ages.append(n-1-min(steps))
            if len(refs)==1:
                uid,ix=refs[0].rsplit(':d',1);label=payloads[(uid,int(ix))]
                assert uid==by_seq[steps[0]+1]['frame_uid'] and f['text']==f'At step {steps[0]}, the detector recorded a possible {label}.'
                facts['landmark']+=1
            else:
                start,end,edge=refs;assert steps[0]+1==steps[1]
                assert (by_seq[steps[0]+1]['frame_uid'],by_seq[steps[1]+1]['frame_uid'])==(start,end)
                assert hashlib.sha256(('temporal_next|'+start+'|'+end).encode()).hexdigest()==edge
                action=packets[end]['action'];assert action['collision'] is False
                side={2:'left',3:'right'}[action['action_id']]
                assert f['text']==f'From step {steps[0]} to {steps[1]}, a {side} turn was executed.'
                facts['turn']+=1
            if earliest is None:earliest=dict(call=k,current_step=n-1,displayed=[i-1 if i else None for i in seq],fact=f['text'])
    result=trace[-1];original=base[-1];assert result['kind']==original['kind']=='terminal'
    return dict(member=trace[0]['episode_scope']['member'],calls=len(calls),native_slots_verified=nslots,injected=len(aud),
        facts_verified=dict(facts),oldest_evidence_steps=max(ages,default=0),first_example=earliest,
        first_output_difference=next((k for k,v in calls.items()if k in ctrl and v['output_ids']!=ctrl[k]['output_ids']),None),
        fallbacks=dict(Counter(v['reason']for v in fallback.values())),metrics={k:[original['native_metrics'][k],result['native_metrics'][k]] for k in ('success','spl','ndtw','path_length','steps_taken','distance_to_goal')},
        stop=[original['stop_source'],result['stop_source']],scope='development members; native visual identity checked against actual trajectory')
