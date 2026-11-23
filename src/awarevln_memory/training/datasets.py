"""Three stage datasets with immutable provenance and causal event joins."""
from __future__ import annotations
import math
from collections import defaultdict
import torch
from torch.utils.data import Dataset
from .artifacts import identity
from .data import route_key, validate_route
from .models import pad_embeddings


def action_code(actions):
    """Actual executed primitives only. 4=verified no movement, 5=mixed or unobserved sequence."""
    if any(type(x) is not int or x not in range(4) for x in actions):raise ValueError('invalid executed primitive')
    return 4 if not actions else actions[0] if len(set(actions))==1 else 5


def validate_events(routes, events):
    lookup={route_key(validate_route(r)):r for r in routes}
    if len(lookup)!=len(routes):raise ValueError('duplicate route')
    result={}
    grouped=defaultdict(list)
    for event in events:
        e=dict(event);r=lookup.get(e.get('route_key'))
        if r is None:raise ValueError('event outside selected identities')
        if e.get('source_split')!='train':raise ValueError('evaluation event cannot train')
        for key in ('event_id','rollout_id','prompt','protocol_identity'):
            if not isinstance(e.get(key),str) or not e[key]:raise ValueError('event missing '+key)
        if e.get('prompt_contains_target',False):raise ValueError('current target in prompt')
        # A mislabeled flag is not sufficient evidence against a direct leak.
        # Do not normalize/approximate text here: repeated common words are
        # legitimate in navigation instructions, full target output is not.
        target=e.get('target_text')
        if isinstance(target,str) and target and target in e['prompt']:
            raise ValueError('current target text leaked into prompt')
        call=e.get('call_id')
        if type(call) is not int or call<1:raise ValueError('call_id must be positive integer')
        if len(e.get('image_paths',[]))!=8 or len(e.get('image_call_ids',[]))!=8:
            raise ValueError('exact eight-frame provenance required')
        if any(type(t) is not int or t<0 or t>call for t in e['image_call_ids']):raise ValueError('future/invalid observation index')
        if e['event_id'] in result:raise ValueError('duplicate event_id')
        if 'executed_actions' in e:action_code(e['executed_actions'])
        e.update(dataset=r['dataset'],language=r['language'],partition=r['partition'],scene=r['scene'],family=r['family'])
        e['source_sha256']=r['source_sha256']
        e['input_identity']=identity({k:e[k] for k in ('route_key','rollout_id','call_id','prompt','image_paths','image_call_ids','protocol_identity')})
        result[e['event_id']]=e;grouped[(e['route_key'],e['rollout_id'])].append(e)
    for seq in grouped.values():
        calls=[e['call_id'] for e in seq]
        if len(calls)!=len(set(calls)):raise ValueError('duplicate policy call')
    return result


def tcl_triplets(events, *, min_distance=2.0, per_route=12, seed=42,
                 allow_cross_scene_fallback=True):
    """Build TCL pairs without leaking validation data or inventing positions.

    First prefer verified, distinct spatial positions *within a rollout*.
    For observations without positions, an explicitly marked train-only,
    same-dataset, same-partition, different-scene negative may be used.
    This fallback is a PLACE-discrimination auxiliary signal, not equivalent
    to HAMLET's within-trajectory temporal negatives. It must be reported
    separately; experiments may disable it to recover the strict baseline.
    """
    if min_distance<=0 or per_route<1:raise ValueError('invalid TCL selection')
    grouped=defaultdict(list)
    for e in events.values():
        if e.get('source_split')!='train' or e.get('partition') not in ('train','memory-dev'):
            raise ValueError('TCL negatives require audited train partitions')
        grouped[e['route_key']].append(e)
    # Index once instead of repeatedly scanning every event, and NEVER cross
    # scene train/dev boundaries even when the two scenes have similar names.
    by_partition_dataset=defaultdict(list)
    for e in events.values():
        by_partition_dataset[(e['partition'],e['dataset'])].append(e)

    def position(event):
        value=event.get('training_position')
        if (not isinstance(value,(list,tuple)) or len(value)!=3
                or not all(type(v) in (float,int) and math.isfinite(v) for v in value)):
            return None
        return value

    pairs=[];rejected=[]
    for key,seq in sorted(grouped.items()):
        eligible=[]
        for e in seq:
            pos=position(e)
            negatives=[]
            if pos is not None:
                for n in seq:
                    other=position(n)
                    if (n['event_id']==e['event_id'] or n['rollout_id']!=e['rollout_id']
                            or other is None or e.get('viewpoint') is not None
                            and e['viewpoint']==n.get('viewpoint')):
                        continue
                    if sum((float(a)-float(b))**2 for a,b in zip(pos,other))>=min_distance**2:
                        negatives.append(n)
            kind='verified_spatial_same_rollout'
            if not negatives and allow_cross_scene_fallback:
                negatives=[n for n in by_partition_dataset[(e['partition'],e['dataset'])]
                           if n['scene']!=e['scene'] and n['event_id']!=e['event_id']]
                kind='cross_scene_train_fallback'
            if not negatives:
                rejected.append({'event_id':e['event_id'],
                                 'reason':'NO_SPATIAL_OR_SCENE_DISJOINT_NEGATIVE'})
                continue
            negatives.sort(key=lambda n:identity([seed,e['event_id'],n['event_id']]))
            negative=negatives[0]
            eligible.append({'schema':'hamlet.tcl.v1','route_key':key,'family':e['family'],
                             'scene':e['scene'],'partition':e['partition'],'dataset':e['dataset'],
                             'source_split':'train','language':e['language'],
                             'anchor':e['event_id'],'positive':e['event_id']+'::positive',
                             'negative':negative['event_id'],'negative_type':kind,
                             'negative_route_key':negative['route_key'],
                             'negative_scene':negative['scene'],
                             'augmentation_seed':seed})
        eligible.sort(key=lambda x:identity([seed,x['anchor']]))
        pairs.extend(eligible[:per_route])
    return pairs,rejected


class StageDataset(Dataset):
    """No tokenization or GT trajectory access inside the model's input path."""
    def __init__(self,rows,store,stage,partition,*,moment_store=None):
        if partition not in ('train','memory-dev'):raise ValueError('invalid partition')
        if stage not in ('tcl','reader','router'):raise ValueError('invalid stage')
        self.rows=[dict(r) for r in rows if r.get('partition')==partition]
        if not self.rows:raise ValueError('empty '+partition+' dataset')
        self.store=store;self.moment_store=moment_store;self.stage=stage;self.partition=partition
        for r in rows:
            if r.get('source_split')!='train' or r.get('dataset') not in ('r2r','rxr'):raise ValueError('nontrain source')
            if r['dataset']=='rxr' and r.get('language')!='en-US':raise ValueError('wrong language')
            if r.get('partition') not in ('train','memory-dev'):raise ValueError('missing partition')
            if not r.get('family') or not r.get('scene'):raise ValueError('missing route grouping')
        if stage=='reader' and moment_store is None:raise ValueError('Reader requires frozen moment cache')

    def __len__(self):return len(self.rows)

    def _get(self,key,store=None):return (store or self.store).get(key,partition=self.partition)

    def __getitem__(self,index):
        r=self.rows[index]
        if self.stage=='tcl':
            values={};metas=[]
            for role in ('anchor','positive','negative'):
                data,meta=self._get(r[role]);values[role]=data['prompt'];metas.append(meta)
            if any(m['route_key']!=r['route_key'] for m in metas[:2]):
                raise ValueError('TCL anchor/positive route mismatch')
            if metas[1].get('augmentation_of')!=r['anchor']:
                raise ValueError('positive is not same observed event')
            if metas[2].get('source_split')!='train' or metas[2].get('partition')!=self.partition:
                raise ValueError('TCL negative crosses train/dev partition')
            negative_type=r.get('negative_type','verified_spatial_same_rollout')
            if negative_type=='verified_spatial_same_rollout':
                if metas[2]['route_key']!=r['route_key']:
                    raise ValueError('TCL spatial negative route mismatch')
            elif negative_type=='cross_scene_train_fallback':
                if (metas[2]['route_key']!=r.get('negative_route_key')
                        or metas[2].get('scene')!=r.get('negative_scene')
                        or metas[2].get('scene')==r['scene']
                        or metas[2].get('dataset')!=r['dataset']):
                    raise ValueError('TCL cross-scene negative source mismatch')
            else:
                raise ValueError('unknown TCL negative provenance')
            return values
        if self.stage=='router':
            data,meta=self._get(r['feature_key'])
            if meta['reader_sha256']!=r['reader_sha256']:raise ValueError('router features from wrong Reader')
            return {k:data[k] for k in ('query','items','valid','types','ages','utility_sign','candidate_measured','set_sign','set_valid')}
        prompt,pmeta=self._get(r['current'])
        if pmeta['route_key']!=r['route_key'] or pmeta['call_id']!=r['call_id']:raise ValueError('current event identity mismatch')
        current,cmeta=self._get(r['current'],self.moment_store)
        if cmeta['input_identity']!=pmeta['input_identity']:raise ValueError('moment/prompt input mismatch')
        if len(r['past'])!=3:raise ValueError('recent-4 must have exactly 3 past slots')
        past=[];valid=[];ages=[];actions=[]
        for offset,key in zip((3,2,1),r['past']):
            if key is None:
                past.append(torch.zeros_like(current['moment']));valid.append(False);ages.append(offset);actions.append(4);continue
            item,meta=self._get(key,self.moment_store)
            if meta['route_key']!=r['route_key'] or meta['rollout_id']!=r['rollout_id'] or meta['call_id']!=r['call_id']-offset:
                raise ValueError('future/cross-rollout/nonrecent memory')
            past.append(item['moment']);valid.append(True);ages.append(offset)
            actions.append(action_code(meta.get('executed_actions',[])) if meta.get('executed_actions_available',False) else 5)
        if 'target_ids' not in prompt or not pmeta.get('verified_target'):raise ValueError('no trusted SFT target')
        if not pmeta.get('mode_compatible',False):raise ValueError('target mode conflicts with locked baseline')
        if pmeta.get('target_sha256')!=identity(r['target_text']):raise ValueError('target annotation/cache drift')
        return dict(prompt=prompt['prompt'],current_moment=current['moment'],past_moments=torch.stack(past),
                    past_valid=torch.tensor(valid,dtype=torch.bool),ages=torch.tensor(ages+[0]),
                    actions=torch.tensor(actions+[4]),target_ids=prompt['target_ids'].long(),
                    kind=torch.tensor(int(r['target_kind']=='reason')),preserve=torch.tensor(bool(pmeta.get('baseline_correct',False))))


def collate_stage(rows):
    if not rows:raise ValueError('empty batch')
    batch={}
    for key in rows[0]:
        values=[r[key] for r in rows]
        if key in ('prompt','anchor','positive','negative'):
            batch[key],batch[key+'_mask']=pad_embeddings(values)
        elif key=='target_ids':
            n=max(len(v) for v in values)
            batch[key]=torch.stack([torch.nn.functional.pad(v,(0,n-len(v)),value=0) for v in values])
            batch['target_mask']=torch.arange(n)[None,:]<torch.tensor([len(v) for v in values])[:,None]
        else:batch[key]=torch.stack(values)
    return batch


def validate_partitions(rows):
    scenes={};families={}
    for r in rows:
        p=r.get('partition')
        if p not in ('train','memory-dev'):raise ValueError('partition missing')
        for table,key in ((scenes,r['scene']),(families,r['family'])):
            if key in table and table[key]!=p:raise ValueError('train/dev scene or route family overlap')
            table[key]=p
    return {'scenes':len(scenes),'families':len(families)}
