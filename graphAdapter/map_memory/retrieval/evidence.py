"""Construct and independently resolve structured historical text evidence."""
from dataclasses import dataclass
import re
from ..storage.archive import IntegrityError
from graphAdapter.map_memory.retrieval.protocol import native_slot_indices


def _match_category_cues(instruction,vocabulary,*,aliases=None,with_spans=False):
    vocab=tuple(vocabulary)
    if len(set(vocab))!=len(vocab) or any(not isinstance(x,str) or not x for x in vocab):
        raise ValueError('Explicit unique category vocabulary required')
    aliases={} if aliases is None else dict(aliases)
    if any(not isinstance(k,str) or not k or v not in vocab for k,v in aliases.items()):
        raise ValueError('Aliases must explicitly name existing vocabulary categories')
    lowered=instruction.casefold()
    hit=set()
    spans={}
    offsets=None
    if with_spans and len(lowered)!=len(instruction):
        offsets=[i for i,ch in enumerate(instruction) for _ in ch.casefold()]

    for term,category in [*((x,x)for x in vocab),*aliases.items()]:
        pattern=r'(?<!\w)'+re.escape(term.casefold())+r'(?!\w)'
        if not with_spans:
            if re.search(pattern,lowered):hit.add(category)
            continue
        for match in re.finditer(pattern,lowered):
            a,b=match.span()
            start,end=(a,b) if offsets is None else (offsets[a],offsets[b-1]+1)
            hits=spans.setdefault(category,set())
            hits.add((start,end))
    if with_spans:
        return {label:[dict(start=a,end=b,text=instruction[a:b]) for a,b in sorted(spans[label])]
                for label in vocab if label in spans}
    return tuple(x for x in vocab if x in hit)



def match_category_cues(instruction,vocabulary,*,aliases=None):
    return _match_category_cues(instruction,vocabulary,aliases=aliases)


def category_source_spans(text,vocabulary,*,aliases=None):
    """Offsets are half-open Python character indices into the unmodified source text."""
    return _match_category_cues(text,vocabulary,aliases=aliases,with_spans=True)


def landmark_query_cues(instruction,reasoning,vocabulary):
    """Restrict a known plan to positive object cues also present in the instruction."""
    verb=r"\bstand\s+(?:in|at|by|near|on|next|beside|between|to|still|facing)\b"
    def cues(text,labels):
        # Remove only the verb occurrence. A separate noun mention may still license the class.
        filtered=re.sub(verb,lambda m:m.group()[5:],text,flags=re.I)
        return match_category_cues(filtered,labels)
    original=cues(instruction,vocabulary)
    if not reasoning:
        return original
    clauses=re.split(r"\b(?:the |my )?next (?:plan|step) is to\s+",reasoning,flags=re.I)
    if len(clauses)!=2 or not clauses[1].strip():
        return ()
    plan=clauses[1].strip().strip("'\"").strip()
    # Use the first plan sentence. Abstain on negative or hypothetical intentions.
    plan=re.split(r"[.!?]",plan,maxsplit=1)[0]
    if re.search(r"\b(?:not|never|avoid|without|unless|if|don't|don’t)\b",plan,re.I):
        return ()
    return cues(plan,original)


@dataclass(frozen=True)
class ExtraRecord:
    text: str
    source_refs: tuple
    steps: tuple


def propose(candidates, current, reader, vocabulary, instruction, budget):
    """Prefer unshown observations, require an instruction cue and a real source."""
    timeline=sorted((*candidates.views,current), key=lambda v:v.capture_seq)
    native={timeline[i].frame_uid for i in native_slot_indices(len(timeline),budget) if i is not None}
    cue=set(candidates.category_cues)
    hints={side for side in ('left','right') if re.search(r'\b'+side+r'\b',instruction,re.I)}
    result=[];seen=set()
    for candidate in candidates.ranked:
        v=candidate.view
        if v.frame_uid in native or v.frame_uid not in candidates.channels['Q']:continue
        features=reader.get_view_features(v.frame_uid)
        for i,class_id in enumerate(features.get('class_ids',())):
            name=vocabulary.labels[int(class_id)]
            if name not in cue or ('landmark',name) in seen:continue
            result.append(dict(kind='landmark',uid=v.frame_uid,index=i,label=name))
            seen.add(('landmark',name));break
        if len(result)>=3:break
    if hints and len(result)<3:
        ranks={uid:i for i,uid in enumerate(candidates.channels['Q'])}
        trace=reader.get_trace()
        views={v.frame_uid:v for v in candidates.views}
        options=[]
        for e in trace:
            code=e['action']['action_id']
            side={2:'left',3:'right'}.get(code)
            if side not in hints or not (e['pre'] in views and e['post'] in views):continue
            if e['pre'] in native and e['post'] in native:continue
            rank=min(ranks.get(e['pre'],100),ranks.get(e['post'],100))
            if rank==100 or e['action'].get('collision') is not False:continue
            options.append((rank,-views[e['post']].capture_seq,e['post'],side,e['pre']))
        for _,_,post,side,pre in sorted(options):
            if ('turn',side) in seen:continue
            result.append(dict(kind='turn',pre=pre,post=post,side=side))
            seen.add(('turn',side))
            if len(result)>=3:break
    return result


def resolve(proposals, reader, vocabulary, current_seq, instruction):
    """Resolve facts independently on the host; free-form worker text is never rendered."""
    result=[];seen=set();trace=None
    if len(proposals)>3:raise IntegrityError('Supplementary fact count exceeds budget')
    def checked(uid):
        v=reader.get_retrieval_view(uid)
        if (v is None or v.episode_uid!=reader.identity['episode_uid'] or v.snapshot_id!=reader.snapshot_id
                or not 0<v.capture_seq<current_seq or v.capture_seq>reader.cutoff['capture_seq']
                or v.event_seq>reader.cutoff['event_seq']):
            raise IntegrityError('Supplementary evidence is outside the pinned history')
        return v
    for item in proposals:
        if item.get('kind')=='landmark' and set(item)=={'kind','uid','index','label'}:
            v=checked(item['uid']);idx=item['index'];row=reader.get_view_class_ids(v.frame_uid)
            if row['status']!='available' or type(idx)is not int or not 0<=idx<len(row['class_ids']):
                raise IntegrityError('Supplementary detection does not exist')
            class_id=int(row['class_ids'][idx])
            if not 0<=class_id<len(vocabulary.labels):raise IntegrityError('Invalid original vocabulary ID')
            if row['model_identity']['vocabulary_sha256']!=vocabulary.source_sha256:
                raise IntegrityError('Supplementary vocabulary differs from archived detector')
            label=vocabulary.labels[class_id]
            if label!=item['label'] or not re.search(r'(?<!\w)'+re.escape(label)+r'(?!\w)',instruction,re.I) or not re.fullmatch(r'[a-z0-9][a-z0-9 -]{0,60}',label):
                raise IntegrityError('Supplementary detection label is not supported')
            text=f'At step {v.env_step}, the detector recorded a possible {label}.'
            record=ExtraRecord(text,(f'{v.frame_uid}:d{idx:05d}',),(v.env_step,))
        elif item.get('kind')=='turn' and set(item)=={'kind','pre','post','side'}:
            v=checked(item['pre']);w=checked(item['post']);side=item['side']
            if trace is None:trace={e['post']:e for e in reader.get_trace()}
            e=trace.get(w.frame_uid)
            if (side not in ('left','right') or not re.search(r'\b'+side+r'\b',instruction,re.I)
                    or w.capture_seq!=v.capture_seq+1 or e is None or e['pre']!=v.frame_uid
                    or e['action']['action_id']!={'left':2,'right':3}[side] or e['action'].get('collision') is not False
                    or (e['motion']['temporal']['src'],e['motion']['temporal']['dst'])!=(v.frame_uid,w.frame_uid)):
                raise IntegrityError('Supplementary turn does not match recorded execution')
            record=ExtraRecord(f'From step {v.env_step} to {w.env_step}, a {side} turn was executed.',
                               (v.frame_uid,w.frame_uid,e['motion']['temporal']['id']),(v.env_step,w.env_step))
        else:raise IntegrityError('Unsupported supplementary fact format')
        if record.text not in seen:result.append(record);seen.add(record.text)
    return tuple(result)


def append_evidence(original, records, token_count, fits, budget):
    for n in range(len(records),0,-1):
        suffix='\nEarlier observations from memory:\n'+'\n'.join(record.text for record in records[:n])
        if token_count(suffix)<=budget and fits(original+suffix):
            return original+suffix,records[:n]
    return original,()


def requested_turns(instruction):
    # A side describing an object's position does not request a turn.
    return set(re.findall(r'\b(?:turn(?:ing)?(?:\s+to)?|take(?:\s+a)?|make(?:\s+a)?)\s+(?:the\s+)?(left|right)\b',instruction.lower()))


def motion_after(source_uid, trace_by_pre, cutoff, view, directions):
    cursor=source_uid
    path=[]; side=None; macro=None
    while cursor in trace_by_pre:
        e=trace_by_pre[cursor]
        pre,post=view(cursor),view(e['post'])
        if post.capture_seq>cutoff:return None
        temporal=e['motion']['temporal']
        if (e['pre'],temporal['src'],temporal['dst'],temporal['type'])!=(cursor,cursor,e['post'],'temporal_next') or post.capture_seq!=pre.capture_seq+1:
            raise IntegrityError('Nonconsecutive context evidence')
        a=e['action']
        if a['collision'] is not False:return None
        if a['action_id']==1 and side is None:
            moved=e['motion'].get('traversed')
            if not moved:return None
            if (moved['src'],moved['dst'],moved['type'])!=(cursor,e['post'],'traversed'):
                raise IntegrityError('Traversal identity mismatch')
            path.append(moved['id'])
        else:
            direction={2:'left',3:'right'}.get(a['action_id'])
            if direction not in directions:return None
            if side is None:
                if a['primitive_index']!=1:return None
                side=direction;macro=a['macro_id'];count=a['primitive_count'];ordinal=1
                if type(count)is not int or count<1 or macro is None:return None
            elif (side,macro,count,ordinal)!=(direction,a['macro_id'],a['primitive_count'],a['primitive_index']):return None
            path.append(temporal['id'])
            if ordinal==count:return post,side,tuple(path),macro
            ordinal+=1
        cursor=e['post']
    return None


def trace_index(reader):
    records=reader.get_trace();by_pre={e['pre']:e for e in records}
    if len(by_pre)!=len(records):raise IntegrityError('Repeated branch in recorded executed trajectory')
    return by_pre


def propose_context(candidates,current,reader,vocabulary,instruction,budget):
    dirs=requested_turns(instruction)
    if not dirs or not candidates.category_cues:return []
    views={v.frame_uid:v for v in candidates.views};timeline=sorted((*views.values(),current),key=lambda v:v.capture_seq)
    native={timeline[i].frame_uid for i in native_slot_indices(len(timeline),budget)if i is not None}
    by_pre=None;seen=set();result=[]
    for uid in candidates.channels['Q']:
        if uid not in views or uid in native:continue
        features=reader.get_view_features(uid)
        for idx,class_id in enumerate(features.get('class_ids',())):
            label=vocabulary.labels[int(class_id)]
            if label not in candidates.category_cues:continue
            if by_pre is None:by_pre=trace_index(reader)
            # Reader may include the current observation; only older steps can be evidence.
            motion=motion_after(uid,by_pre, min(current.capture_seq-1,reader.cutoff['capture_seq']),
                               reader.get_retrieval_view,dirs)
            if motion is None:continue
            post,side,path,macro=motion
            if (label,macro) in seen:continue
            seen.add((label,macro));result.append(dict(kind='landmark_then_turn',uid=uid,index=idx,
                            label=label,post=post.frame_uid,side=side))
            if len(result)==3:return result
    return result


def resolve_context(items,reader,vocabulary,current_seq,instruction):
    if len(items)>3:raise IntegrityError('Too many context records')
    out=[];by_pre=trace_index(reader) if items else {}
    for item in items:
        if set(item)!={'kind','uid','index','label','post','side'} or item['kind']!='landmark_then_turn':
            raise IntegrityError('Unsupported context record')
        landmark=resolve([dict(kind='landmark',uid=item['uid'],index=item['index'],label=item['label'])],
                         reader,vocabulary,current_seq,instruction)[0]
        motion=motion_after(item['uid'],by_pre,min(current_seq-1,reader.cutoff['capture_seq']),
                           reader.get_retrieval_view,requested_turns(instruction))
        if motion is None or (motion[0].frame_uid,motion[1])!=(item['post'],item['side']):
            raise IntegrityError('Proposed landmark/turn relation lacks consecutive source evidence')
        post,side,path,macro=motion
        record=ExtraRecord(f'{landmark.text} A recorded {side} turn ended at step {post.env_step}.',
            (*landmark.source_refs,*path,post.frame_uid),(*landmark.steps,post.env_step))
        out.append(record)
    return tuple(out)


def delivery_key(record):
    # The same completed turn and class may be supported by multiple adjacent detections.
    return record.text.partition('possible ')[2].partition('.')[0],record.source_refs[-1]


def fresh_records(records,delivered):
    unique={}
    for record in records:
        key=delivery_key(record)
        if key not in delivered:unique.setdefault(key,record)
    return tuple(unique.values())
