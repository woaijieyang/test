"""R2R/RxR-en-US identity audit, scene-disjoint selection and causal windows.

Missing RGB or reasoning is a repairable capability gap, never a split bypass.
All heuristics are explicit in the selection record; none is a utility label.
"""
from __future__ import annotations
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from .artifacts import digest, identity, read_records, training_path

ROOMS = frozenset('bedroom bathroom kitchen living room hallway corridor stairs staircase '
                  'door doorway chair table sofa couch bed desk cabinet window carpet lobby'.split())
ORDER = re.compile(r'\b(?:after|before|until|past|second|third|then|through|between|beside)\b', re.I)


def route_key(row):
    return f"{row['dataset']}:{row['scene']}:{row['instruction_id']}"


def validate_route(row):
    if row.get('dataset') not in ('r2r', 'rxr'):
        raise ValueError('DATASET_NOT_ALLOWED')
    if row.get('source_split') != 'train':
        raise ValueError('SPLIT_NOT_TRAIN')
    if row['dataset'] == 'rxr' and row.get('language') != 'en-US':
        raise ValueError('LANGUAGE_NOT_EN_US')
    for key in ('scene', 'instruction_id', 'instruction', 'family', 'source_sha256'):
        if not str(row.get(key, '')).strip():
            raise ValueError(f'MISSING_{key.upper()}')
    if len(row.get('path', [])) < 2:
        raise ValueError('INVALID_PATH')
    if row.get('partition') not in (None, 'train', 'memory-dev'):
        raise ValueError('INVALID_PARTITION')
    return row


def ingest(source, dataset, source_split, guide_source=None):
    """Read official raw lists or VLN-CE episodes. Source split is explicit.

    CE RxR records may omit language: then an official guide index is mandatory.
    No language inference from English text or rxr_us directory names is allowed.
    """
    source = training_path(source)
    if dataset not in ('r2r', 'rxr') or source_split != 'train':
        raise ValueError('only r2r/train and rxr/train/en-US are permitted')
    source_hash = digest(source)
    # Native official R2R/RxR records do not always carry `split` per row.
    # In that case require a train-labelled source artifact; the caller's
    # `--source-split train` assertion alone must not relabel an anonymous
    # val-unseen JSON copied outside checkpoint-choice.
    filename = source.name.lower()
    filename = filename[:-3] if filename.endswith('.gz') else filename
    source_train_named = bool(re.search(r'(^|[._-])train([._-]|$)', filename))
    if (re.search(r'(^|[._-])(val|unseen|test)([._-]|$)', source.name.lower())
            or any(parent.name.lower() in ('val', 'validation', 'val_unseen', 'val_seen', 'test')
                   for parent in list(source.parents)[:3])):
        raise ValueError('SOURCE_PATH_NOT_TRAIN')
    guides = {}
    guide_identity = None
    if guide_source is not None:
        gp = training_path(guide_source)
        guide_identity = {"path": str(gp), "sha256": digest(gp)}
        for guide in read_records(gp):
            gid = str(guide['instruction_id'])
            if gid in guides:
                raise ValueError('duplicate official guide instruction identity')
            guides[gid] = guide
    accepted, rejected = [], []
    seen = {}
    for index, raw in enumerate(read_records(source)):
        try:
            explicit_split = raw.get('split', raw.get('source_split'))
            if explicit_split is not None and explicit_split != 'train':
                raise ValueError('SPLIT_NOT_TRAIN')
            if explicit_split is None and not source_train_named:
                raise ValueError('SOURCE_SPLIT_UNVERIFIED')
            inst = raw.get('instruction', '')
            info = inst if isinstance(inst, dict) else {}
            iid = info.get('instruction_id', raw.get('instruction_id'))
            guide = guides.get(str(iid), {})
            if guide and guide.get('split', 'train') != 'train':
                raise ValueError('GUIDE_SPLIT_NOT_TRAIN')
            scan_raw = raw.get('scan', raw.get('scene_id', guide.get('scan', '')))
            scene = Path(str(scan_raw)).stem
            if scene.endswith('.basis'): scene = scene[:-6]
            if guide.get('scan') and guide['scan'] != scene:
                raise ValueError('GUIDE_SCENE_MISMATCH')
            path = raw.get('path', guide.get('path'))
            # reference_path is continuous coordinates: preserve order and units.
            if path is None: path = raw.get('reference_path', [])
            language = raw.get('language', info.get('language', guide.get('language')))
            if dataset == 'rxr' and language != 'en-US':
                raise ValueError('LANGUAGE_NOT_EN_US')
            texts = raw.get('instructions')
            if texts is None:
                texts = [info.get('instruction_text', inst if isinstance(inst, str)
                                  else guide.get('instruction', ''))]
            if not isinstance(texts, list): raise ValueError('INVALID_INSTRUCTIONS')
            pid = raw.get('path_id', guide.get('path_id'))
            for j, text in enumerate(texts):
                item_id = iid
                if item_id is None:
                    if dataset != 'r2r':raise ValueError('MISSING_INSTRUCTION_ID')
                    if pid is not None:item_id = f'{pid}_{j}'
                    elif raw.get('episode_id') is not None:item_id = f'ce-episode:{raw["episode_id"]}'
                    else:raise ValueError('MISSING_INSTRUCTION_ID')
                row = dict(dataset=dataset, source_split='train', language=language,
                           scene=scene, instruction_id=str(item_id), path_id=pid,
                           instruction=str(text), path=path,
                           family=identity([scene, path]), source=str(source),
                           source_sha256=source_hash, source_row=index,
                           heading=raw.get('heading', guide.get('heading')),
                           episode_id=raw.get('episode_id'), partition=None,
                           capabilities={'observation': False, 'act': False,
                                         'reason': False, 'replay': False})
                if guide_identity is not None:row["guide_source"] = guide_identity
                validate_route(row)
                key = route_key(row)
                if key in seen:
                    if (seen[key]['instruction'], seen[key]['path']) != (row['instruction'], row['path']):
                        raise ValueError('CONFLICTING_INSTRUCTION_ID')
                    continue
                seen[key] = row; accepted.append(row)
        except (ValueError, TypeError, KeyError) as exc:
            rejected.append(dict(source_row=index, reason=str(exc)))
    return accepted, rejected


def attach_events(routes, events):
    lookup = {route_key(r): dict(r) for r in routes}
    if len(lookup) != len(routes): raise ValueError('duplicate route identity')
    grouped = defaultdict(list)
    for event in events:
        key = event.get('route_key')
        if key not in lookup: raise ValueError(f'event outside train allowlist: {key}')
        if event.get('source_split') != 'train': raise ValueError('event is not train')
        grouped[key].append(event)
    for key, row in lookup.items():
        ev = grouped[key]
        # Observation availability is separate from label/replay availability.
        row['capabilities'] = dict(
            observation=any(e.get('prompt') and e.get('image_paths') for e in ev),
            act=any(e.get('target_kind') == 'act' and trusted_label(e) for e in ev),
            reason=any(e.get('target_kind') == 'reason' and trusted_label(e) for e in ev),
            replay=any(e.get('replay_state_sha256') for e in ev))
        actions = [a for e in ev for a in e.get('executed_actions', [])]
        # IDs are baseline primitive IDs: stop=0, forward=1, left=2, right=3.
        turns = [a for a in actions if a in (2, 3)]
        blocks = [a for i, a in enumerate(actions) if i == 0 or a != actions[i-1]]
        row['features_raw'] = dict(
            L=max(len(row['path'])-1, 0),
            G=len(set(re.findall(r'\b\w+\b', row['instruction'].lower())) & ROOMS)
              + 2*len(ORDER.findall(row['instruction'])),
            T=len(blocks),
            A=sum(x != y for x, y in zip(turns, turns[1:])),
            V=row.get('visual_diversity'),
            Q=sum(bool(e.get('prompt') and e.get('image_paths')) for e in ev)/max(1,len(ev)))
        row['event_count'] = len(ev)
        row['event_provenance_sha256'] = identity(ev)
    return list(lookup.values())


def trusted_label(event):
    return (event.get('target_source') in ('expert', 'verified_correction', 'verified_annotation')
            and bool(event.get('target_text')) and bool(event.get('target_provenance')))


def _rank(values, x):
    values = sorted(values)
    if not values or len(set(values)) == 1: return .5
    lo = sum(v < x for v in values)
    eq = sum(v == x for v in values)
    return min(1.0,max(0.0,(lo + (max(eq, 1)-1)/2) / max(1,len(values)-1)))


def select_routes(routes, total=1500, dev_fraction=.1, seed=42, pilot=False):
    if not pilot and not 1000 <= total <= 2000:
        raise ValueError('production selection size must be in [1000,2000]')
    if total < 2 or not 0 < dev_fraction < .5: raise ValueError('invalid selection budget')
    rows = [dict(validate_route(r)) for r in routes]
    if len({route_key(r) for r in rows}) != len(rows): raise ValueError('duplicate routes')
    # Select only repair-complete SFT routes; keep unselected TCL-only assets in audit.
    rows = [r for r in rows if r.get('capabilities', {}).get('act')]
    scenes = sorted({r['scene'] for r in rows}, key=lambda s:identity([seed,s]))
    if len(scenes) < 2: raise ValueError('need at least two train scenes for held-out dev')
    # Deterministic round-robin scene search; both datasets must exist in each side.
    dev_n = max(1, round(len(scenes)*dev_fraction))
    dev_scenes = None
    for offset in range(len(scenes)):
        proposal = set((scenes+scenes)[offset:offset+dev_n])
        if all({r['dataset'] for r in rows if (r['scene'] in proposal)==side} == {'r2r','rxr'}
               for side in (False, True)):
            dev_scenes = proposal;break
    if dev_scenes is None:
        raise ValueError('cannot create scene-disjoint train/dev with both datasets; repair coverage')
    stats = {}
    for dataset in ('r2r','rxr'):
        train = [r for r in rows if r['dataset']==dataset and r['scene'] not in dev_scenes]
        stats[dataset] = {k:[float(r.get('features_raw',{}).get(k,0) or 0) for r in train
                              if r.get('features_raw',{}).get(k) is not None]
                          for k in 'LGTAVQ'}
    for r in rows:
        r['partition'] = 'memory-dev' if r['scene'] in dev_scenes else 'train'
        raw=r.get('features_raw',{}); normalized={}; available={}
        for k,w in {'L':.25,'G':.20,'T':.20,'A':.15,'V':.10,'Q':.10}.items():
            v=raw.get(k)
            if v is None: continue
            if not math.isfinite(float(v)):raise ValueError('nonfinite selection feature')
            q=_rank(stats[r['dataset']][k],float(v))
            normalized[k]=(q/.75 if q<=.75 else 1-.4*(q-.75)/.25) if k=='L' else q
            available[k]=w
        if not available: raise ValueError('candidate lacks audited features')
        r['selection_score']=sum(available[k]*normalized[k] for k in available)/sum(available.values())
        r['selection_evidence']=dict(normalized=normalized, missing=[k for k in 'LGTAVQ' if k not in available])
        repeated = len({str(v) for v in r['path']})<len(r['path'])
        r['category']=('confusable' if repeated or normalized.get('V',1)<.1 else
                       'turns' if normalized.get('A',0)>=.75 else
                       'grounded' if normalized.get('L',0)>=.6 and normalized.get('G',0)>=.6 else 'ordinary')
    selected=[];relaxations=[]
    ratios={'grounded':.35,'turns':.25,'confusable':.20,'ordinary':.20}
    # Family first: one instruction in round one, a second only to fill a real deficit.
    family_counts=Counter();scene_counts=Counter()
    for dataset,target_ds in [('r2r',total//2),('rxr',total-total//2)]:
        for partition,count in [('memory-dev',max(1,round(target_ds*dev_fraction))),
                                ('train',target_ds-max(1,round(target_ds*dev_fraction)))]:
            pool=[r for r in rows if r['dataset']==dataset and r['partition']==partition]
            pool.sort(key=lambda r:(-r['selection_score'],identity([seed,route_key(r)])))
            picked=[];cat_counts=Counter();cap=max(1,math.ceil(count*max(.05,1/max(1,len({r['scene'] for r in pool})))) )
            for family_cap,scene_cap,quota in [(1,cap,True),(1,cap,False),(1,count,False),(2,count,False)]:
                for r in pool:
                    if len(picked)>=count:break
                    if r in picked or family_counts[r['family']]>=family_cap:continue
                    if sum(x['scene']==r['scene'] for x in picked)>=scene_cap:continue
                    if quota and cat_counts[r['category']]>=math.ceil(count*ratios[r['category']]):continue
                    picked.append(r);family_counts[r['family']]+=1;scene_counts[r['scene']]+=1;cat_counts[r['category']]+=1
            if len(picked)<count:relaxations.append(dict(dataset=dataset,partition=partition,wanted=count,actual=len(picked)))
            selected.extend(picked)
    actual_train=sum(r['partition']=='train' for r in selected)
    status='READY' if (pilot or actual_train>=1000) else 'INSUFFICIENT_TRAIN_ROUTES'
    return selected,dict(status=status,pilot=pilot,requested=total,actual=len(selected),
                         train=actual_train,dev=len(selected)-actual_train,
                         families=len({r['family'] for r in selected}),
                         scenes=len({r['scene'] for r in selected}),dev_scenes=sorted(dev_scenes),
                         score_statistics=stats,deficits=relaxations,
                         missing_visual=sum('V' in r['selection_evidence']['missing'] for r in selected))


def build_windows(routes, events, max_anchors=12, total_slots=4):
    if total_slots != 4: raise ValueError('first experiment is total_slots=4 (past3 + current)')
    lookup={route_key(r):validate_route(r) for r in routes}
    groups=defaultdict(list)
    for event in events:
        if event.get('route_key') not in lookup:raise ValueError('event not in selected route allowlist')
        if event.get('source_split')!='train':raise ValueError('evaluation event in training')
        groups[(event['route_key'],event['rollout_id'])].append(event)
    result=[];excluded=[]
    for (key,rollout),sequence in groups.items():
        route=lookup[key];sequence=sorted(sequence,key=lambda e:int(e['call_id']))
        calls=[int(e['call_id']) for e in sequence]
        if len(calls)!=len(set(calls)) or any(c<1 for c in calls):raise ValueError('duplicate/invalid call ID')
        legal=[]
        for i,e in enumerate(sequence):
            # Missing calls remain a causal gap, not a compressed false recent-4.
            history=[p for p in sequence[:i] if int(e['call_id'])-3<=int(p['call_id'])<int(e['call_id'])]
            if not e.get('prompt') or not e.get('image_paths'):
                excluded.append(dict(route_key=key,call_id=e['call_id'],reason='REPAIR_PROMPT_OR_FRAMES'));continue
            if e.get('prompt_contains_target',False):raise ValueError('target answer in prompt')
            frames=e['image_paths'];frame_calls=e.get('image_call_ids')
            if len(frames)!=8:raise ValueError('eight-frame protocol violated')
            if frame_calls is None or len(frame_calls)!=8 or any(int(c)>int(e['call_id']) for c in frame_calls):
                raise ValueError('image provenance missing or includes future observations')
            if e.get('target_kind') not in ('act','reason') or not trusted_label(e):
                excluded.append(dict(route_key=key,call_id=e['call_id'],reason='OBSERVATION_ONLY_NO_TRUSTED_LABEL'));continue
            refs={int(p['call_id']):p['event_id'] for p in history}
            past=[refs.get(c) for c in range(int(e['call_id'])-3,int(e['call_id']))]
            row=dict(schema='hamlet.window.v1',window_id=identity([key,rollout,e['call_id']]),
                     route_key=key,family=route['family'],scene=route['scene'],dataset=route['dataset'],
                     source_split='train',language=route['language'],partition=route['partition'],
                     rollout_id=rollout,current=e['event_id'],past=past,
                     call_id=int(e['call_id']),target_kind=e['target_kind'],target_text=e['target_text'],
                     target_source=e['target_source'],target_provenance=e['target_provenance'],
                     event_sha256=identity(e),priority=bool(e.get('executed_actions') in ([2],[3],[0])) )
            legal.append(row)
        # Event priority first; fill with time-stratified positions without duplication.
        picks=[r for r in legal if r['priority']][:max_anchors]
        remaining=[r for r in legal if r not in picks]
        needed=max_anchors-len(picks)
        if needed and remaining:
            positions=sorted({round(i*(len(remaining)-1)/max(1,needed-1)) for i in range(needed)})
            picks.extend(remaining[p] for p in positions)
        result.extend(sorted(picks,key=lambda r:r['call_id']))
    # Cap across rollout variants as well: variants are not independent routes.
    by_route=defaultdict(list)
    for row in result:by_route[row['route_key']].append(row)
    limited=[]
    for key,rows in sorted(by_route.items()):
        rows.sort(key=lambda r:(not r['priority'],identity([key,r['window_id']])))
        limited.extend(rows[:max_anchors])
    return limited,excluded
