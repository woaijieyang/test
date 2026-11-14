"""Evaluate context-evidence eligibility and original host prompts at recorded cutoffs."""
from pathlib import Path
from types import SimpleNamespace
import gzip,json,tarfile,io,re,hashlib,sys
import numpy as np
from graphAdapter.map_memory.service import execution_relation
from graphAdapter.map_memory.retrieval.evidence import propose_context,resolve_context,fresh_records,delivery_key
from graphAdapter.map_memory.retrieval.contracts import CategoryVocabulary
from graphAdapter.map_memory.retrieval.candidates import match_category_cues
from graphAdapter.interfaces.host_slots import native_slot_indices
from PIL import Image

def read(p):
    with gzip.open(p,'rt')as stream:return [json.loads(line) for line in stream]

def inspect(run,entry,dest):
    d=run/'results'/entry['key']/'shadow/attempt0'
    flow=read(d/'flow.jsonl.gz');history=read(d/'observation_packets.jsonl.gz');trace=read(d/'trace.jsonl.gz')
    calls={v['call_id']:v for v in trace if v['kind']=='model_call'}
    requests={x['request_id']:x for x in flow if x['kind']=='MemoryReadRequested'}
    vocab=CategoryVocabulary.from_file('vendor_sources/EvoMemNav/data/scannet200_classes.txt')
    detection={};data={};byid={p['frame_uid']:p for p in history}
    observed=next(r for r in flow if r['kind']=='HostInputAudit')
    with tarfile.open(d/'final-map.tar.gz','r|gz')as archive:
        for m in archive:
            if m.name.startswith('detections/') and m.name.endswith('.npz'):
                with np.load(io.BytesIO(archive.extractfile(m).read()),allow_pickle=False)as blob:
                    detection[Path(m.name).stem]=blob['class_id'].copy()
            if m.name.endswith('.rgb.png'):
                data[Path(m.name).name[:-len('.rgb.png')]]=archive.extractfile(m).read()
    edges=[]
    for before,after in zip(history,history[1:]):
        motion=execution_relation(before,after);edges.append(dict(pre=before['frame_uid'],post=after['frame_uid'],action=after['action'],motion=motion))
    delivered=set();decisions=[];state=None
    for row in flow:
        if row['kind']!='MemoryCandidates':continue
        req=requests[row['request_id']];q=req['cutoff'];cur=byid[row['frame_uid']];sid=req['snapshot_id']
        model=calls[row['decision_id']]
        inst=model['prompt'].split('Your assigned task is: "',1)[1].split('". ',1)[0]
        def view(uid):
            p=byid[uid]
            return SimpleNamespace(frame_uid=uid,capture_seq=p['capture_seq'],event_seq=p['event_seq'],env_step=p['env_step'],episode_uid=p['episode_uid'],snapshot_id=sid)
        def features(uid):
            return dict(status='available',class_ids=detection[uid],model_identity={'vocabulary_sha256':vocab.source_sha256}) if uid in detection else dict(status='unavailable')
        views=[view(p['frame_uid'])for p in history if p['capture_seq']<=q['capture_seq'] and p['event_seq']<=q['event_seq'] and p['capture_seq']<cur['capture_seq']]
        allowed={v.frame_uid for v in views}
        reader=SimpleNamespace(snapshot_id=sid,identity={'episode_uid':cur['episode_uid']},cutoff=q,get_view_features=features,get_retrieval_view=view,
            get_trace=lambda:[e for e in edges if e['pre'] in allowed and e['post'] in allowed])
        c=SimpleNamespace(views=views,channels=row['channels'],category_cues=match_category_cues(inst,vocab.labels))
        proposals=propose_context(c,view(cur['frame_uid']),reader,vocab,inst,8)
        facts=fresh_records(resolve_context(proposals,reader,vocab,cur['capture_seq'],inst),delivered)
        delivered.update(map(delivery_key,facts))
        if facts:
            decisions.append(dict(decision=row['decision_id'],current_step=cur['env_step'],facts=[dict(text=f.text,refs=f.source_refs,steps=f.steps) for f in facts]))
            if state is None:state=(model,cur,facts)
    out=dest/entry['member'][0];out.mkdir(parents=True,exist_ok=True)
    (out/'coverage.json').write_text(json.dumps(dict(member=entry['member'],total_calls=len(calls),offered=decisions,scope='counterfactual delivery ledger on recorded state sequence'),indent=2))
    if state:
        model,cur,facts=state;pics=out/'images';pics.mkdir(exist_ok=True)
        for idx,im in zip(native_slot_indices(cur['capture_seq'],8),model['images']):
            if idx is None:
                pic=Image.new('RGB',(512,512))
            else:
                pic=Image.open(io.BytesIO(data[history[idx]['frame_uid']])).convert('RGB')
            assert hashlib.sha256(pic.mode.encode()+str(pic.size).encode()+pic.tobytes()).hexdigest()==im['pixel_sha256']
            pic.save(pics/(im['pixel_sha256']+'.png'))
        prompt=model['prompt'];prefix,mark,_=prompt.partition('\nEarlier observations from memory:\n')
        assert mark
        suffix=prompt[prompt.index('<|eot_id|>',len(prefix)):]
        compact=dict(model,images=[im['pixel_sha256']for im in model['images']]);compact.pop('task_key',None)
        variants=[('recorded_exact',prompt),('native_visual_only',prefix+suffix),
            ('verified_context',prefix+mark+'\n'.join(f.text for f in facts)+suffix)]
        (out/'replay-input.json').write_text(json.dumps(dict(recorded=compact,variants=variants)))
    print(entry['member'][2],len(calls),[(x['decision'],x['facts'][0]['text']) for x in decisions])
if __name__=='__main__':
    run=Path(sys.argv[1]);out=Path(sys.argv[2])
    for e in json.loads((run/'retention_plan.json').read_text())['entries']:inspect(run,e,out)

