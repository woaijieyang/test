"""Read existing camera features to measure redundancy and route coverage of a real substitution."""
import gzip,json,tarfile,io,sys
from pathlib import Path
import numpy as np
from collections import Counter
def records(path):
    with gzip.open(path,'rt') as f:return [json.loads(x)for x in f]
def summarize(vals):
    return dict(n=len(vals),median=float(np.median(vals)),minimum=float(min(vals)),maximum=float(max(vals)))
def run(d):
    flow=records(d/'flow.jsonl.gz');packets=records(d/'observation_packets.jsonl.gz')
    byseq={p['capture_seq']:p['frame_uid'] for p in packets}
    mats={v['request_id']:v for v in flow if v['kind']=='MemoryMaterialized'}
    feats={};examples=[];all_sims=[];old_sims=[];dif=[]
    with tarfile.open(d/'final-map.tar.gz','r|gz')as ar:
        for m in ar:
            if m.name.startswith('detections/') and m.name.endswith('.npz'):
                with np.load(io.BytesIO(ar.extractfile(m).read()),allow_pickle=False)as npz:
                    if 'full_clip' in npz:
                        v=np.asarray(npz['full_clip'],dtype=np.float64);feats[Path(m.name).stem]=v/np.linalg.norm(v)
    for a in flow:
        if a['kind']!='HostInputAudit':continue
        B=a['logical_image_slots'];n=packets[a['env_step']]['capture_seq']
        native=[byseq[int(i)+1] for i in np.linspace(0,n-1,B-1,endpoint=False,dtype=int)]+[byseq[n]]
        selected=mats[a['request_id']]['selected'];ix,=[i for i in range(B)if selected[i]!=native[i]]
        group,=mats[a['request_id']]['groups'];uid=group['seed_ref'];other,=[v for v in group['view_refs']if v!=uid]
        assert selected[ix]==uid
        retained=[v for i,v in enumerate(native) if i!=ix]
        if any(v not in feats for v in [*native,uid,other]):continue
        sim=float(feats[uid]@feats[other]);newmax=max(float(feats[uid]@feats[v])for v in retained)
        oldmax=max(float(feats[native[ix]]@feats[v])for v in retained)
        all_sims.append(sim);old_sims.append(oldmax);dif.append(newmax-oldmax)
        examples.append(dict(call=a['call_id'],seed=uid,paired=other,displaced=native[ix],pair_cosine=sim,
                             incoming_max_similarity=newmax,outgoing_max_similarity=oldmax))
    return dict(scope='Visual redundancy from existing full-image CLIP; does not measure navigation relevance',checked=len(examples),
        pair_similarity=summarize(all_sims)if all_sims else None,displaced_similarity=summarize(old_sims)if old_sims else None,
        incoming_minus_outgoing=summarize(dif)if dif else None,increased_redundancy=sum(x>0 for x in dif),per_call=examples)
if __name__=='__main__':
    root=Path(sys.argv[1])
    for row in json.loads((root/'retention_plan.json').read_bytes())['entries']:
        d=root/'results'/row['key']/'shadow/attempt0';p=root/'control'/('visual-overlap-'+row['member'][0]+'.json')
        if (d/'retention.json').exists() and not p.exists():
            v=run(d);p.write_text(json.dumps(v,indent=2));print({k:x for k,x in v.items() if k!='per_call'})

