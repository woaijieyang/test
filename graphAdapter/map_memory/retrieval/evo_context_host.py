"""Bind optional archived Q/V/C group references on the host, without a second encoder."""
from collections import defaultdict
from ..storage.store import IntegrityError
from .semantic_topology import visible_detection_owners


def verify_context(reader,query,current,reply,vocabulary):
    if (reply.get('episode_uid')!=query.episode_uid or reply.get('snapshot_id')!=reader.snapshot_id
            or reply.get('current_source_snapshot_id')!=current.source_snapshot_id
            or reply.get('current_frame_uid')!=current.frame_uid or reply['query']['instruction_sha256']!=query.instruction_hash):
        raise IntegrityError('Crossed Q/V/C material request')
    import hashlib
    reason_hash=hashlib.sha256(query.last_reasoning.encode()).hexdigest() if query.last_reasoning else None
    if reply['query']['reasoning_sha256']!=reason_hash:
        raise IntegrityError('Q/V/C query reason differs')
    g=reader._graph
    def frame(uid):
        row=g['views'][uid]
        if not (row['source_event_seq']<=query.cutoff_event_seq and row['capture_seq']<=query.cutoff_capture_seq
                and row['capture_seq']<query.current_capture_seq):
            raise IntegrityError('Future context view')
        return row
    channels=reply['channels']
    if set(channels)!={'Q','V','C'}:raise IntegrityError('Missing Q/V/C channel')
    for uids in channels.values():
        if len(set(uids))!=len(uids):raise IntegrityError('Duplicate ranking source')
        for uid in uids:frame(uid)
    edges={e['id']:e for e in g['edges']}
    sections=[]
    receipts={}
    for group in reply['groups']:
        seed=group['seed_ref'];refs={v['uid']:v for v in group['views']}
        if len(refs)!=len(group['views']) or seed not in refs or not any(seed in a for a in channels.values()):
            raise IntegrityError('Context group lacks a ranked seed')
        for uid,v in refs.items():
            row=frame(uid)
            if (row['env_step'],row['capture_seq'])!=(v['step'],v['capture_seq']):raise IntegrityError('Wrong context time')
        facts=context_facts(reader,group,refs,edges,vocabulary,receipts)
        if not facts:continue
        sections.append(dict(seed=seed,group=group,text='Historical evidence around step '+str(refs[seed]['step'])+': '+ '; '.join(facts)+'.'))
    return sections


def context_facts(reader,group,refs,edges,vocabulary,receipts):
    """Compile facts from each selected source; memoize only within this pinned call."""
    seed=group['seed_ref']
    facts=[]
    used=set()
    for edge in group['edges']:
        src,dst=edge['src'],edge['dst']
        kind=edge['type']
        if (edge['id'] in used or kind not in ('temporal_next','traversed')
                or seed not in (src,dst) or src not in refs or dst not in refs):
            raise IntegrityError('Context edge is not a unique one-hop connection')
        used.add(edge['id'])
        stored=edges.get(edge['id'])
        if stored is None or any(stored[k]!=edge[k] for k in ('type','src','dst')):
            raise IntegrityError('Unsupported context edge')
        seq=refs[dst]['capture_seq']
        if seq!=refs[src]['capture_seq']+1:
            raise IntegrityError('Context edge skips an observation')
        if seq not in receipts:
            rows=reader.get_trace(seq,seq)
            if len(rows)!=1:raise IntegrityError('Context edge has no unique execution receipt')
            receipts[seq]=rows[0]
        receipt=receipts[seq]
        motion=receipt['motion'].get('traversed' if kind=='traversed' else 'temporal')
        if (receipt['pre']!=src or receipt['post']!=dst or not motion
                or any(motion.get(k)!=edge[k] for k in ('src','dst','id'))):
            raise IntegrityError('Context edge differs from executed endpoints or motion')
        if kind=='traversed' and (type(receipt['action']['action_id']) is not int
                or receipt['action']['action_id']!=1 or receipt['action']['collision'] is not False):
            raise IntegrityError('Forward travel lacks a successful primitive')
        label='recorded forward travel' if kind=='traversed' else 'successive observations'
        facts.append(f"step {refs[src]['step']} to {refs[dst]['step']}: {label}")
    seen=defaultdict(dict)
    for item in group['visibility']:
        uid=item['uid'];owner=item['object_id']
        u,sep,d=item['member'].rpartition(':d')
        if uid not in refs or uid!=u or not sep or not d.isascii() or not d.isdecimal():
            raise IntegrityError('Unbound context object member')
        ordinal=int(d)
        if (d!=f'{ordinal:05d}' or item['epoch']!=reader._graph['scene_state']['epoch']
                or uid in seen[owner] or visible_detection_owners(reader,uid).get(ordinal)!=owner):
            raise IntegrityError('Unbound or duplicate context object visibility')
        rec=reader.get_view_class_ids(uid)
        if (rec['status']!='available' or rec['model_identity']['vocabulary_sha256']!=vocabulary.source_sha256
                or ordinal>=len(rec['class_ids'])):
            raise IntegrityError('Context camera record differs')
        category=int(rec['class_ids'][ordinal])
        if not 0<=category<len(vocabulary.labels):raise IntegrityError('Context class outside vocabulary')
        seen[owner][uid]=(refs[uid]['step'],vocabulary.labels[category])
    for observations in seen.values():
        if len(observations)<2 or seed not in observations:
            raise IntegrityError('Co-visibility lacks distinct source views including the seed')
        names=', '.join(f'{step} (detected: {label})' for step,label in observations.values())
        facts.append('one graph instance was observed at steps '+names)
    return facts
