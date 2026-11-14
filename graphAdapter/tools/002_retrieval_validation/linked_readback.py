"""Independently verify causal graph reads and actual host slots in small diagnostics."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,tarfile,io,sys
import numpy as np
from PIL import Image
from paired_small import rows,index,hash_pixels

def inspect(run,entry,control):
    d=run/'results'/entry['key']/'shadow/attempt0'
    flow=rows(d/'flow.jsonl.gz');trace=rows(d/'trace.jsonl.gz')
    packets=index([dict(row,kind='packet')for row in rows(d/'observation_packets.jsonl.gz')],'packet','frame_uid')
    base=rows(control/'trace.jsonl.gz')
    calls=index(trace,'model_call','call_id');inputs=index(trace,'model_input','call_id')
    audits=index(flow,'HostInputAudit','call_id');returns=index(flow,'MemoryGenerateReturned','call_id')
    decisions=index(flow,'decision','decision_id');fallback=index(flow,'MemoryReadFallback','decision_id')
    published=index(flow,'PublishedSnapshot','snapshot_id');reads=index(flow,'MemoryReadRequested','request_id')
    mats=index(flow,'MemoryMaterialized','request_id');candidates=index(flow,'MemoryCandidates','request_id')
    def check(condition,reason):
        if not condition:raise ValueError(reason)
    check(set(inputs)==set(calls) and set(returns)==set(audits),'Incomplete model input/output/audit')
    check(len(decisions)==len(calls) and set(decisions)==set(fallback)|{a['decision_id']for a in audits.values()}
          and set(fallback).isdisjoint(a['decision_id']for a in audits.values()),'Incomplete decision coverage')
    member=next(row for row in trace if row['kind']=='reset')['episode_scope']['member']
    check(member==entry['member']==next(row for row in base if row['kind']=='reset')['episode_scope']['member'],'Wrong member')
    image_lookup={};raw_file_hash={}
    with tarfile.open(d/'final-map.tar.gz','r|gz')as archive:
        for item in archive:
            if not item.name.endswith('.rgb.png'):continue
            data=archive.extractfile(item).read()
            uid=Path(item.name).name[:-len('.rgb.png')]
            with Image.open(io.BytesIO(data))as pic:h,p=hash_pixels(pic.convert('RGB'))
            image_lookup[h]=p
            raw_file_hash[uid]=hashlib.sha256(data).hexdigest()
    blank=hash_pixels(Image.new('RGB',(512,512)));image_lookup[blank[0]]=blank[1]
    edges=Counter();ages=[];spans=[];slots=0; facts=0
    for call,a in audits.items():
        x=inputs[call];ret=returns[call];m=mats[a['request_id']];q=reads[a['request_id']];c=candidates[a['request_id']]
        check(len({v['snapshot_id']for v in (q,c,m,a,ret)})==1,'Mixed read snapshot')
        check(len({v['frame_uid']for v in (q,c,m,a,ret)})==1,'Mixed current frame')
        pub=published[q['snapshot_id']]
        check(pub['event_seq']<q['event_seq']<c['event_seq']<m['event_seq']<a['event_seq']<ret['event_seq'],'Out-of-order evidence')
        check(q['cutoff']=={'capture_seq':pub['capture_seq'],'event_seq':pub['cutoff_event_seq']},'Future cutoff')
        ids=np.asarray(x['input_ids'],np.int64)
        basis=json.dumps(dict(dtype='torch.int64',shape=list(ids.shape)),sort_keys=True,separators=(',',':')).encode()
        check(hashlib.sha256(basis+ids.tobytes()).hexdigest()==a['token_ids_sha256'],'Token mismatch')
        check(hashlib.sha256(x['prompt'].encode()).hexdigest()==a['prompt_sha256'],'Prompt mismatch')
        B=a['logical_image_slots'];seq=[s['sensor_seq']for s in a['slots']]
        check(ret['projector_shape'][0]==B==len(x['images']) and
              ids.size+B*(ret['projector_shape'][1]-1)==a['expanded_input_tokens'],'Actual visual/token budget mismatch')
        check(m['selected']==[s['frame_uid']for s in a['slots']],'Selected/materialized mismatch')
        current=packets[q['frame_uid']]
        check(seq==sorted(seq) and seq[-1]==current['capture_seq'],'Chronology/current mismatch')
        native=list(np.linspace(0,seq[-1]-1,B-1,endpoint=False,dtype=int)+1)+[seq[-1]]
        check(sum(v!=n for v,n in zip(seq,native))==1,'Multiple host history slots replaced')
        for slot,im in zip(a['slots'],x['images']):
            uid=slot['frame_uid']
            check(uid in packets and uid in raw_file_hash,'Unknown archived image')
            check(raw_file_hash[uid]==slot['source_image_hash'] and image_lookup[im['pixel_sha256']]==slot['host_pixel_hash'],'Actual host pixels differ from raw source')
            if not slot['is_current']:
                check(packets[uid]['capture_seq']<=pub['capture_seq'] and packets[uid]['event_seq']<=pub['cutoff_event_seq'],'Future historical observation')
            slots+=1
        group,=m['groups'];seed=group['seed_ref']
        check(seed in c['channels']['Q'] and seed in m['selected'],'Seed not from full instruction or not actually used')
        pre,post=[packets[uid]for uid in group['view_refs']]
        check(pre['frame_uid']in m['selected'] and post['frame_uid']in m['selected'],'Missing relation endpoint')
        check(pre['episode_uid']==post['episode_uid']==q['episode_uid'] and pre['capture_seq']+1==post['capture_seq'],'Not a same-episode primitive edge')
        kind,=group['edge_types'];edges[kind]+=1
        if kind=='traversed':
            key=hashlib.sha256(('traversed|'+pre['frame_uid']+'|'+post['frame_uid']).encode()).hexdigest()
            check(group['execution_refs']==[key] and post['action']['action_id']==1 and post['action']['collision'] is False,'Invented movement')
            p0,p1=pre['pose_record'],post['pose_record'];check(p0['episode_instance']==p1['episode_instance'] and p0['valid'] and p1['valid'],'Invalid pose pair')
            distance=np.linalg.norm(np.asarray(p0['T_odom_base'])[:3,3]-np.asarray(p1['T_odom_base'])[:3,3])
            check(.03<distance<=.5,'Motion inconsistent with stored traversal')
            si,sj=[m['selected'].index(v['frame_uid'])+1 for v in (pre,post)]
            check(f'Images {si} and {sj} have a recorded movement connection (historical).' in x['prompt'],'Movement text not bound to final slot indices')
            facts+=1
        else:check(kind=='temporal_next' and not group['execution_refs'],'Invalid temporal evidence')
        ages.append(current['capture_seq']-packets[seed]['capture_seq'])
        spans.append(seq[-1]-min(seq))
    acts=lambda data:[x for x in data if x['kind']=='primitive_action']
    ta=trace[-1];tb=base[-1];check(ta['kind']==tb['kind']=='terminal','Missing terminal')
    keys=['success','spl','ndtw','distance_to_goal','path_length','steps_taken']
    return dict(member=member,total_calls=len(inputs),injected=len(audits),image_slots_checked=slots,edge_types=dict(edges),
        movement_facts_checked=facts,fallbacks=dict(Counter(v['reason']for v in fallback.values())),
        recalled_age_steps={'min':min(ages),'median':float(np.median(ages)),'max':max(ages)}if ages else None,
        metrics={k:{'original':tb['native_metrics'][k],'candidate':ta['native_metrics'][k]}for k in keys},
        first_action_difference=next((x['step']for x,y in zip(acts(trace),acts(base))if x['action']!=y['action']),None),
        stop=[tb['stop_source'],ta['stop_source']],stage_promotion=False)
if __name__=='__main__':
    root=Path(sys.argv[1]);reg=json.loads(Path('outputs/graph_memory/candidate_detached_correction001-20261113/simulator-quality15-reuse-v3/control/REUSED_CONTROLS.json').read_bytes())
    for e in json.loads((root/'retention_plan.json').read_bytes())['entries']:
        dst=root/'control'/('linked-audit-'+e['member'][0]+'.json')
        if not dst.exists() and (root/'results'/e['key']/'shadow/attempt0/retention.json').is_file():
            result=inspect(root,e,Path(reg[e['key']]['result']));dst.write_text(json.dumps(result,indent=2));print(json.dumps(result))

