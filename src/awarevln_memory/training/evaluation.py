"""Cumulative B screening; aggregation is always episode-weighted."""
from __future__ import annotations
import math
from .artifacts import identity


def episode_id(row):
    keys=('dataset','source_split','scene','instruction_id','episode_id')
    if any(k not in row for k in keys):raise ValueError(f'episode identity requires {keys}')
    if row['source_split']!='val_unseen':raise ValueError('B must be val_unseen')
    if row['dataset'] not in ('r2r','rxr'):raise ValueError('unsupported evaluation dataset')
    if row['dataset']=='rxr' and row.get('language')!='en-US':raise ValueError('B RxR must be en-US')
    return identity([str(row[k]) for k in keys])


def cumulative_sets(b1,b2,b3):
    maps=[]
    for rows in (b1,b2,b3):
        m={}
        for r in rows:
            k=episode_id(r)
            if k in m:raise ValueError('duplicate episode in one B partition')
            m[k]=r
        if not m:raise ValueError('empty B partition')
        maps.append(m)
    a,b,c=map(set,maps)
    if not (a&b or a&c or b&c):mode='disjoint'
    elif a<=b<=c:mode='nested'
    else:raise ValueError('ambiguous partial overlap; neither disjoint nor nested')
    merged={};result={}
    for name,values in zip(('B1','B12','B123'),maps):
        for k,row in values.items():
            if k in merged and merged[k]!=row:raise ValueError('conflicting episode content')
            merged[k]=row
        result[name]=[merged[k] for k in sorted(merged)]
    return result,mode


def aggregate(expected,results,checkpoint_sha,protocol_sha):
    wanted={episode_id(e) for e in expected};seen={}
    for r in results:
        key=episode_id(r)
        if key not in wanted:raise ValueError('unexpected episode (future B leakage or wrong set)')
        if r.get('checkpoint_sha256')!=checkpoint_sha or r.get('protocol_sha256')!=protocol_sha:
            raise ValueError('result cache identity mismatch')
        if key in seen:
            if seen[key]!=r:raise ValueError('conflicting repeated episode result')
            continue
        if r.get('status')!='complete':raise ValueError('incomplete/failed run cannot be dropped from denominator')
        for name in ('sr','spl','ndtw','ne'):
            value=r.get(name)
            if not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError(f'invalid {name}')
            if value<0 or (name!='ne' and value>1):raise ValueError('metrics require fractions, not percentages')
        if r['sr'] not in (0,1):raise ValueError('episode SR must be binary')
        seen[key]=r
    if set(seen)!=wanted:raise ValueError(f'incomplete result coverage: {len(seen)}/{len(wanted)}')
    if not wanted:raise ValueError('empty evaluation set')
    report={'n':len(wanted),'episodes_sha256':identity(sorted(wanted)),
            'checkpoint_sha256':checkpoint_sha,'protocol_sha256':protocol_sha}
    report.update({metric:sum(r[metric] for r in seen.values())/len(seen) for metric in ('sr','spl','ndtw','ne')})
    return report


def choose_candidate(baseline,candidates,*,stage='final'):
    """Predeclared constraints first; equal-weight datasets, NOT sample counts."""
    if stage not in ('reader','final'):raise ValueError('unknown selection stage')
    sr_tolerance=.01 if stage=='reader' else 0.0
    quality_tolerance=.02 if stage=='reader' else .01
    if set(baseline)!={'r2r','rxr'}:raise ValueError('both datasets required')
    survivors=[]
    for name,summary in candidates.items():
        if set(summary)!=set(baseline):raise ValueError('candidate lacks a dataset')
        eligible=True
        for dataset,base in baseline.items():
            cur=summary[dataset]
            for key in ('episodes_sha256','protocol_sha256','n'):
                if cur[key]!=base[key]:raise ValueError('unpaired candidate/baseline evaluation')
            eligible &= cur['sr']>=base['sr']-sr_tolerance
            eligible &= cur['spl']>=base['spl']-quality_tolerance and cur['ndtw']>=base['ndtw']-quality_tolerance
        if eligible:
            score=tuple(sum(summary[d][m]-baseline[d][m] for d in baseline)/2 for m in ('sr','spl','ndtw'))
            if stage=='reader' or score[0]>0:survivors.append((score,name))
    if not survivors:return {'status':'NO_ELIGIBLE_CANDIDATE','selected':None,'fallback':'baseline'}
    survivors.sort(key=lambda x:(tuple(-v for v in x[0]),x[1]))
    return {'status':'SELECTED','selected':survivors[0][1],
            'eligible':[n for _,n in survivors],'rule':'per-dataset constraints then macro SR/SPL/nDTW'}


def canonical_eval_rows(selection,dataset,annotations):
    """Resolve existing B ID lists or native CE episodes against an explicit source."""
    from pathlib import Path
    index={}
    for raw in annotations:
        if raw.get('split','val_unseen')!='val_unseen':raise ValueError('evaluation annotation is not val_unseen')
        info=raw.get('instruction',{})
        if not isinstance(info,dict):info={}
        language=raw.get('language',info.get('language'))
        if dataset=='rxr' and language!='en-US':continue
        eid=str(raw['episode_id']);scene_raw=raw.get('scene_id',raw.get('scan'))
        if not scene_raw:raise ValueError('episode scene missing')
        scene=Path(str(scene_raw)).stem
        iid=info.get('instruction_id',raw.get('instruction_id'))
        # '-' is the existing preflight.task_key convention for missing R2R IDs.
        native_key='|'.join((dataset,'val_unseen','en-US' if dataset=='rxr' else 'en',str(scene_raw),eid,str(iid) if iid is not None else '-'))
        row=dict(dataset=dataset,source_split='val_unseen',scene=scene,
                 episode_id=eid,instruction_id=str(iid) if iid is not None else '-',
                 language='en-US' if dataset=='rxr' else 'en',native_task_key=native_key)
        if eid in index:raise ValueError('ambiguous evaluation episode ID')
        index[eid]=row
    result=[]
    for item in selection:
        if isinstance(item,dict):
            eid=str(item['episode_id'])
            if item.get('source_split',item.get('split','val_unseen'))!='val_unseen':raise ValueError('non-val_unseen B item')
        else:eid=str(item)
        if eid not in index:raise ValueError('B identity absent from authoritative en-US/unseen annotation: '+eid)
        result.append(index[eid])
    return result


def convert_native_results(run,expected):
    """Translate existing immutable evaluator results without changing any metric."""
    import json
    from pathlib import Path
    from .artifacts import read_records,digest
    root=Path(run);manifest=json.loads((root/'run_manifest.json').read_text())
    if manifest.get('split')!='val_unseen':raise ValueError('native run is not val_unseen')
    for f in manifest.get('frozen_files',[]):
        if digest(f['path'])!=f['sha256']:raise ValueError('native evidence source changed: '+f['path'])
    required=('base_model_sha256','source_sha256','config_sha256','navmesh_sha256')
    if any(not manifest.get(k) for k in required):raise ValueError('incomplete native run identity')
    protocol=identity({k:manifest[k] for k in required})
    checkpoint=manifest['model_sha256']
    lookup={r['native_task_key']:r for r in expected}
    if len(lookup)!=len(expected):raise ValueError('ambiguous native task identities')
    rows=[]
    for raw in read_records(root/'results.jsonl'):
        if raw['task_key'] not in lookup:raise ValueError('native run contains unexpected episode')
        row=dict(lookup[raw['task_key']],checkpoint_sha256=checkpoint,protocol_sha256=protocol,
                 status='complete' if raw['status']=='completed' else raw['status'],**{k:raw['metrics'][k] for k in ('sr','spl','ndtw','ne')})
        rows.append(row)
    report=aggregate(expected,rows,checkpoint,protocol)
    return rows,report


def paired_report(expected,baseline,candidate,*,samples=2000,seed=42):
    """Episode flips + cluster bootstrap by scene, not independent-window CIs."""
    import numpy as np
    wanted={episode_id(e) for e in expected}
    b={episode_id(r):r for r in baseline};c={episode_id(r):r for r in candidate}
    if len(b)!=len(baseline) or len(c)!=len(candidate) or set(b)!=wanted or set(c)!=wanted:
        raise ValueError('paired report requires exact, unique coverage')
    scenes={}
    for key in sorted(wanted):
        if b[key]['protocol_sha256']!=c[key]['protocol_sha256']:raise ValueError('unpaired protocols')
        scenes.setdefault(b[key]['scene'],[]).append([c[key][m]-b[key][m] for m in ('sr','spl','ndtw','ne')])
    rescued=sum(b[k]['sr']==0 and c[k]['sr']==1 for k in wanted)
    harmed=sum(b[k]['sr']==1 and c[k]['sr']==0 for k in wanted)
    values=[np.asarray(v,float) for v in scenes.values()];rng=np.random.default_rng(seed)
    if not values or samples<1:raise ValueError('empty/invalid bootstrap')
    boot=[np.concatenate([values[i] for i in rng.integers(len(values),size=len(values))]).mean(0) for _ in range(samples)]
    lo,hi=np.quantile(boot,[.025,.975],axis=0)
    return {'rescued':int(rescued),'harmed':int(harmed),'scenes':len(scenes),
            'intervals':{m:[float(lo[i]),float(hi[i])] for i,m in enumerate(('sr','spl','ndtw','ne'))},
            'warning':'cluster bootstrap is descriptive with few scenes; not a guarantee of significance'}
