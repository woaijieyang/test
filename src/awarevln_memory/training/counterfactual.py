"""Validate real branch evidence. This module does NOT simulate trajectories.

Native Habitat replay stays in the existing environment. A producer must emit
state/config/reader bindings and complete branch metrics; RGB alone is not a
same-state certificate. Set-level utility is never copied to candidate labels.
"""
from __future__ import annotations
import math
from .artifacts import digest,identity

STATE_FIELDS=('rgb','pose','primitive_step','action_queue','image_history',
              'reasoning','memory','python_rng','numpy_rng','torch_rng','environment')


def preference(off,on,quality_band=.01):
    for row in (off,on):
        if row.get('status')!='complete' or row.get('horizon')!='terminal':raise ValueError('strong utility requires complete terminal rollout')
        for metric in ('sr','spl','ndtw'):
            value=row.get(metric)
            if not isinstance(value,(float,int)) or not math.isfinite(value) or not 0<=value<=1:raise ValueError('invalid branch metrics')
        if row['sr'] not in (0,1):raise ValueError('SR must be binary')
    if off['sr']!=on['sr']:return 1 if on['sr']>off['sr'] else -1
    dn=on['ndtw']-off['ndtw'];ds=on['spl']-off['spl']
    if dn>quality_band and ds>=0:return 1
    if dn< -quality_band and ds<=0:return -1
    return 0


def validate_branch(branch,anchor,reader_sha):
    if branch.get('reader_sha256')!=reader_sha:raise ValueError('branch Reader changed')
    if branch.get('anchor_id')!=anchor['anchor_id']:raise ValueError('anchor mismatch')
    if branch.get('intervention_scope')!='current_read_only':raise ValueError('local and persistent interventions cannot mix')
    if branch.get('continuation_policy_sha256')!=anchor['continuation_policy_sha256']:raise ValueError('different continuation policy')
    state=branch.get('initial_state',{})
    if set(state)!=set(STATE_FIELDS) or any(not isinstance(v,str) or len(v)!=64 for v in state.values()):
        raise ValueError('complete same-state hashes required')
    if state!=anchor['initial_state']:raise ValueError('branch did not start from the same full state')
    evidence=branch.get('evidence_file');expected=branch.get('evidence_sha256')
    if not evidence or digest(evidence)!=expected:raise ValueError('missing or changed original branch evidence')
    import json
    recorded=json.loads(__import__('pathlib').Path(evidence).read_text())
    comparable={k:v for k,v in branch.items() if k not in ('evidence_file','evidence_sha256')}
    if recorded!=comparable:raise ValueError('branch labels differ from immutable original evidence')
    return branch


def label_anchor(anchor,branches,reader_sha,quality_band=.01):
    if anchor.get('source_split')!='train' or anchor.get('dataset') not in ('r2r','rxr'):raise ValueError('evaluation branch cannot train')
    if anchor['dataset']=='rxr' and anchor.get('language')!='en-US':raise ValueError('wrong language')
    if anchor.get('partition') not in ('train','memory-dev'):raise ValueError('partition missing')
    candidates=anchor['candidate_ids']
    if len(candidates)!=3 or len([c for c in candidates if c is not None])!=len(set(c for c in candidates if c is not None)):
        raise ValueError('three chronological past slots required')
    off=None;on=None;single={}
    for branch in branches:
        validate_branch(branch,anchor,reader_sha)
        mode=branch['intervention']
        if mode=='OFF':
            if off is not None:raise ValueError('duplicate OFF branch')
            off=branch
        elif mode=='ON':
            if on is not None:raise ValueError('duplicate ON branch')
            on=branch
        elif mode=='SINGLE':
            key=branch['candidate_id']
            if key is None or key not in candidates or key in single:raise ValueError('invalid/repeated candidate branch')
            single[key]=branch
        else:raise ValueError('unsupported evidence: REMOVE/PROXY are diagnostics, not singleton ranking labels')
    if off is None:raise ValueError('OFF branch required')
    result=dict(anchor)
    result.update(schema='hamlet.router-label.v1',reader_sha256=reader_sha,
                  label_kind='TERMINAL_ROLLOUT',utility_sign=[preference(off,single[c],quality_band) if c in single else 0 for c in candidates],
                  candidate_measured=[c in single for c in candidates],
                  set_sign=preference(off,on,quality_band) if on else 0,set_valid=on is not None,
                  evidence_sha256=identity(branches))
    return result


def cache_router_features(labels,prompt_store,moment_store,modules,store,reader_sha):
    import torch
    from .datasets import action_code
    modules.eval().requires_grad_(False)
    rows=[];rejected=[]
    for label in labels:
        try:
            if label['reader_sha256']!=reader_sha:raise ValueError('Reader label version mismatch')
            current,meta=moment_store.get(label['current'],partition=label['partition'])
            if meta['route_key']!=label['route_key']:raise ValueError('current route mismatch')
            past=[];valid=[]
            for offset,key in zip((3,2,1),label['candidate_ids']):
                if key is None:past.append(torch.zeros_like(current['moment']));valid.append(False);continue
                data,m=moment_store.get(key,partition=label['partition'])
                if m['route_key']!=meta['route_key'] or m['rollout_id']!=meta['rollout_id'] or m['call_id']!=meta['call_id']-offset:
                    raise ValueError('candidate is not causal recent history')
                past.append(data['moment']);valid.append(True)
            with torch.no_grad():
                query=modules.reader.down(current['moment'].float())
                items=modules.reader.router_features(torch.stack(past))
            tensors={'query':query,'items':items,'valid':torch.tensor(valid),'types':torch.zeros(3,dtype=torch.long),
                     'ages':torch.tensor([3,2,1]),'utility_sign':torch.tensor(label['utility_sign'],dtype=torch.float32),
                     'candidate_measured':torch.tensor(label['candidate_measured'],dtype=torch.bool),
                     'set_sign':torch.tensor(float(label['set_sign'])),'set_valid':torch.tensor(label['set_valid'])}
            if any(v and not valid[i] for i,v in enumerate(label['candidate_measured'])):raise ValueError('label for invalid candidate')
            key=label['anchor_id']
            meta=dict(meta,reader_sha256=reader_sha,evidence_sha256=label['evidence_sha256'])
            store.put(key,tensors,meta)
            rows.append(dict(label,feature_key=key))
        except (OSError,ValueError,KeyError) as exc:rejected.append({'anchor_id':label.get('anchor_id'),'reason':str(exc)})
    return rows,rejected
