"""Replay only the selector on frozen decisions. Every query uses its own public cutoff."""
import gzip,json,hashlib,tarfile,sys,io
import numpy as np
from pathlib import Path
from types import MappingProxyType
from collections import Counter
from graphAdapter.map_memory.service import execution_relation
from graphAdapter.map_memory.retrieval.contracts import ViewRef,Candidate,CandidateResult
from graphAdapter.map_memory.retrieval.selector import select_linked_view

def read(path):
    with gzip.open(path,'rt')as f:return [json.loads(line) for line in f]

def replay(d, gain=False):
    flow=read(d/'flow.jsonl.gz')
    packets=read(d/'observation_packets.jsonl.gz')
    hashes={};features={}
    with tarfile.open(d/'final-map.tar.gz','r|gz')as archive:
        for m in archive:
            if gain and m.name.startswith('detections/') and m.name.endswith('.npz'):
                with np.load(io.BytesIO(archive.extractfile(m).read()),allow_pickle=False)as bundle:
                    if 'full_clip' in bundle:features[Path(m.name).stem]=bundle['full_clip']
            if m.name.endswith('.rgb.png'):
                uid=Path(m.name).name.removesuffix('.rgb.png')
                hashes[uid]=hashlib.sha256(archive.extractfile(m).read()).hexdigest()
    request={v['request_id']:v for v in flow if v['kind']=='MemoryReadRequested'}
    result=[];futures=0
    packet_by_uid={p['frame_uid']:p for p in packets}
    all_edges=[]
    for before,after in zip(packets,packets[1:]):
        rel=execution_relation(before,after)
        all_edges.append(rel['temporal'])
        if rel['traversed']:all_edges.append(rel['traversed'])
    for row in flow:
        if row['kind']!='MemoryCandidates':continue
        req=request[row['request_id']];sid=req['snapshot_id'];current=packet_by_uid[req['frame_uid']]
        def ref(p):
            h=hashes[p['frame_uid']]
            return ViewRef(p['episode_uid'],sid,p['frame_uid'],p['capture_seq'],p['event_seq'],p['env_step'],h,h,None,p['pose_record']['map_version'],(),None)
        historical={p['frame_uid']:ref(p) for p in packets if p['capture_seq']<current['capture_seq'] and p['capture_seq']<=req['cutoff']['capture_seq'] and p['event_seq']<=req['cutoff']['event_seq']}
        ranked=tuple(Candidate(historical[x['frame_uid']],x['score'],tuple(map(tuple,x['ranks'])),None,None,tuple(x['matched_categories']),('rgb',)) for x in row['candidates'])
        pool=CandidateResult(sid,tuple(historical.values()),ranked,MappingProxyType(row['channels']),(),())
        edges=[e for e in all_edges if e['src'] in historical and e['dst'] in historical]
        chosen=select_linked_view(pool,ref(current),{'edges':edges},budget=8,full_image_feature=features.get if gain else None)
        group=chosen.groups[0] if chosen.groups else None
        result.append(dict(decision_id=row['decision_id'],current_seq=current['capture_seq'],snapshot_id=sid,selected=[v.frame_uid for v in chosen.slots],selected_steps=[v.env_step for v in chosen.slots],edge_refs=list(group.execution_refs) if group else [],pair=[v.frame_uid for v in group.views]if group else [],
            capture_cutoff=req['cutoff']['capture_seq'],pool_size=len(historical),reason=chosen.fallback_reason,
            seed_seq=historical[group.seed_ref].capture_seq if group else None,edge_types=group.edge_types if group else (),
            age=current['capture_seq']-historical[group.seed_ref].capture_seq if group else None))
    ages=[v['age']for v in result if v['age'] is not None]
    return dict(scope='selector replay at recorded same-state decisions; no new model or navigation results',decisions_with_candidate_logs=len(result),
        contextual_reads=len(ages),no_category_hit_decisions=sum(not any(c['matched_categories']for c in v['candidates'])for v in flow if v['kind']=='MemoryCandidates'),
        oldest_recalled_age=max(ages,default=None),fallback_reasons=dict(Counter(v['reason']for v in result if v['reason'])),rows=result)

if __name__=='__main__':
    run=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
    for entry in json.loads((run/'retention_plan.json').read_text())['entries']:
        res=replay(run/'results'/entry['key']/'shadow/attempt0',gain='--gain' in sys.argv[3:]);res['member']=entry['member']
        (out/(entry['member'][2]+'.json')).write_text(json.dumps(res,indent=2))
        print({k:v for k,v in res.items()if k!='rows'})

