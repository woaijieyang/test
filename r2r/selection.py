"""Deterministic R2R teaching selection, not a semantic route parser."""
from pathlib import Path
from functools import lru_cache
import hashlib,json,re,math
ROOT=Path(__file__).resolve().parents[1]
PATTERNS={
 'entity_frame':[r'\b(?:left|right) of (?:the |a )?[^,.!?;]{1,50}'],
 'frame':[r'\b(?:on your (?:left|right)|with[^,.!?]{0,50}on your|between[^,.!?]{0,70}and|facing)\b'],
 'ordinal':[r'\b(?:first|second|third|fourth|last|1st|2nd|3rd)\b'],
 'terminal':[r'\b(?:stop|wait|stand|stopping)\b'],
 'endpoint':[r'\b(?:until|once|when|arrived|halfway|midway)\b'],
 'hall_end':[r'\b(?:end of (?:the )?(?:hall|hallway|corridor)|hallway end)\b'],
 'bounded':[r'\b(?:one|two|three|four|five|\d+)\s+(?:steps?|paces?|feet|meters?)\b',r'\b(?:halfway|midway|flight)\b'],
 'stair_target':[r'\b(?:down|up|top|bottom|landing)\b[^.!?]{0,40}\b(?:stairs?|staircase|stairway)\b',r'\bstairs?\b[^.!?]{0,30}\b(?:left|right|landing)\b'],
 'scope':[r'\b(?:before|after|while|until|once|when|keep|on the)\b'],
 'attribute':[r'\b(?:open|closed)\s+(?:(?:sliding|glass|arched|double)\s+)?doors?\b'],
 'observation':[r'\b(?:you (?:will |should |can )?(?:see|face)|you are facing|there (?:is|are))\b'],
 'entry':[r'\b(?:enter|exit|into|through|out of)\b'],
 'transit':[r'\b(?:continue|keep going|straight through)\b',r'\bthrough\b[^.!?]{0,100}\b(?:past|out|door|exit)\b'],
 'coupled':[r'\bturn\b[^.!?]{0,45}\b(?:walk|go|continue|climb)\b'],
 'direction':[r'\b(?:turn|take|veer|head)\b[^,.!?]{0,25}\b(?:left|right)\b'],
 'attachment':[r'\b(?:past|passing)\b[^,.!?]{0,50}'],
 'pass_by':[r'\b(?:past|passing|pass)\b'],
 'target_identity':[r'\b(?:with|next to|other side|center door|far wall|left of|right of)\b'],
 'final_approach':[r'\b(?:toward|towards|approach)\b'],
 'negation':[r"\b(?:do not|don't|never|without)\b"],
 'branch':[r'\b(?:if|otherwise|either)\b'],
 'return':[r'\b(?:return|backtrack|retrace|back to|same door)\b'],
 'uncertainty':[r'\b(?:either|unclear|not sure|or)\b'],
}
# Transparent specificity priorities, not learned navigation-success estimates.
SPECIFIC=frozenset({'entity_frame','ordinal','bounded','hall_end','attribute','observation','negation','branch','return','attachment'})

def digest(raw):return hashlib.sha256(raw).hexdigest()
def normalized(text):return ' '.join(text.casefold().split())
def _source(row):return (row.get('input') or row['review_input'])['original_instruction']
def _weight(skills):return sum(2 if k in SPECIFIC else 1 for k in sorted(skills))

@lru_cache(maxsize=4)
def _index_blob(blob):
    obj=json.loads(blob)
    if obj.get('profile')!='r2r-en':raise ValueError('Cross-profile teaching index')
    items=obj['items'];index={r['template_id']:r for r in items}
    if len(index)!=len(items):raise ValueError('Duplicate teaching index identity')
    return index

def teaching_index():
    blob=(ROOT/'shared/dataset_rules/r2r_teaching_index.json').read_bytes()
    return _index_blob(blob),digest(blob)

def signals(text):
    if not isinstance(text,str):raise TypeError('R2R source must be a string')
    out={}
    for skill,patterns in PATTERNS.items():
        spans=sorted({(m.start(),m.end(),m.group()) for p in patterns for m in re.finditer(p,text,re.I)})
        if spans:out[skill]=[dict(start=a,end=b,quote=q) for a,b,q in spans]
    return out

def _verify(row,item):
    if item['quality']!='authored_and_contract_checked' or item['role']!=row['role'] or item['template_id']!=row['template_id']:
        raise ValueError('Unapproved role/teaching identity')
    if row['dataset_scope']!='R2R' or row['language']!='en':raise ValueError('Cross-profile R2R template')
    rel=Path(item['path'])
    if rel.is_absolute() or '..' in rel.parts or '/templates/R2R/' not in rel.as_posix():raise ValueError('Invalid R2R asset path')
    raw=(ROOT/rel).read_bytes()
    if digest(raw)!=item['content_sha256'] or digest(_source(row).encode())!=item['source_sha256']:raise ValueError('R2R teaching index content drift: '+row['template_id'])
    if json.loads(raw)!=row:raise ValueError('Cached R2R library differs from indexed asset')
    if not item.get('skills') or not item.get('lesson') or not item.get('counter_boundary'):raise ValueError('Incomplete teaching intent')


def core_rows(role):
    from host.template_selector import validate_template
    if role not in ('generator','reviewer'):raise ValueError('Invalid Core role')
    rows=[json.loads(p.read_bytes()) for p in sorted((ROOT/role/'templates/R2R/core').glob('*.json'))]
    ids=[f'R2R-CORE-{"G" if role=="generator" else "R"}{i:02d}' for i in range(1,11)]
    if [r['template_id'] for r in rows]!=ids:raise ValueError('R2R fixed Core count/order mismatch')
    for row in rows:
        validate_template(role,row)
        if row['dataset_scope']!='R2R' or row['language']!='en' or row['role']!=role:raise ValueError('R2R Core identity mismatch')
    return rows


def _choose(rows,text,index,core,minimum,maximum,count=None,exclude=()):
    if count is not None and (type(count) is not int or not minimum<=count<=maximum):raise ValueError(f'R2R count must be {minimum}..{maximum}')
    hits=signals(text);query=set(hits);words=set(re.findall(r'[a-z]+',text.casefold()))
    core_focus=set()
    for r in core:
        item=index[r['template_id']];_verify(r,item)
        core_focus.update(item['skills'][:1])
    options=[];excluded=[];blocked={normalized(text),*(normalized(x) for x in exclude)}
    for row in rows:
        tid=row['template_id'];item=index.get(tid)
        if item is None:raise ValueError('Missing R2R teaching metadata: '+tid)
        _verify(row,item)
        identity=normalized(_source(row))
        if item['status']!='dynamic':excluded.append(dict(template_id=tid,reason=item['status']));continue
        if identity in blocked:excluded.append(dict(template_id=tid,reason='same_source'));continue
        matched=query&set(item['skills']);terms=set(re.findall(r'[a-z]+',_source(row).casefold()))
        lexical=len(words&terms)/math.sqrt(max(1,len(terms)))
        options.append(dict(row=row,identity=identity,matched=matched,lexical=lexical,cost=len(_source(row).encode()),item=item))
    if len({x['identity'] for x in options})<(count or minimum):raise ValueError('Insufficient eligible R2R calibration library')
    selected=[];trace=[];covered=set();ranking=[];initial_pool=sorted(x['row']['template_id'] for x in options)
    while options and len(selected)<(count or maximum):
        base=len(selected)<(count or minimum)
        eligible=options if base else [x for x in options if x['matched']-covered-core_focus]
        if not eligible:break
        def components(x):
            novelty=x['matched']-covered
            # Actual new Dynamic skills lead; fixed Core overlap is a soft cost.
            incremental=_weight(novelty)-0.25*_weight(novelty&core_focus)
            return incremental,_weight(x['matched']),_weight(x['matched']&covered)
        def key(x):
            inc,fit,repeat=components(x)
            return (not bool(x['matched']),-inc,-fit,repeat,-.2*x['lexical'],x['cost'],x['row']['template_id'])
        ordered=sorted(eligible,key=key);best=ordered[0];tid=best['row']['template_id']
        ranking.append(dict(slot=len(selected),ordered_candidates=[dict(template_id=x['row']['template_id'],matched_skills=sorted(x['matched']),incremental_skills=sorted(x['matched']-covered),core_overlap=sorted(x['matched']&core_focus),incremental_score=components(x)[0],relation_score=components(x)[1],redundancy_score=components(x)[2],lexical=round(x['lexical'],10),source_bytes=x['cost'],content_sha256=x['item']['content_sha256']) for x in ordered]))
        reason='explicit_count' if count is not None else 'specific_complement' if base and best['matched'] else 'broad_calibration' if base else 'uncovered_skill'
        trace.append(dict(template_id=tid,selection_reason=reason,matched_skills=sorted(best['matched']),added_coverage=sorted(best['matched']-covered),optional_coverage=sorted(best['matched']-covered-core_focus) if not base else [],core_overlap=sorted(best['matched']&core_focus),matched_source_spans={s:hits[s] for s in sorted(best['matched'])}))
        selected.append(best['row']);covered.update(best['matched'])
        duplicates=[x for x in options if x['identity']==best['identity'] and x['row']['template_id']!=tid]
        excluded.extend(dict(template_id=x['row']['template_id'],reason='selected_source_family',selected_id=tid) for x in duplicates)
        options=[x for x in options if x['identity']!=best['identity']]
    return selected,dict(selected=trace,excluded=excluded,ranking=ranking,eligible_pool=initial_pool,query_signals=hits)


def _projection_receipts(role,ids,bank):
    from r2r.teaching import card,dynamic_is_detailed
    from shared.identity import canonical
    out=[]
    for position,tid in enumerate(ids):
        detailed=dynamic_is_detailed(role,ids,position)
        payload=canonical(card(bank[tid],role,detailed))
        out.append(dict(template_id=tid,detailed=detailed,projection_utf8_bytes=len(payload.encode()),projection_sha256=digest(payload.encode())))
    return out


def select_bundle(text,count=None):
    from host.template_selector import library
    index,index_sha=teaching_index()
    gen=library('generator','r2r-en')
    gs,ge=_choose(gen,text,index,core_rows('generator'),4,6,count)
    rev=library('reviewer','r2r-en');pairs={r['pair_id']:r for r in rev if r.get('pair_id')}
    if len(pairs)!=sum(bool(r.get('pair_id')) for r in rev):raise ValueError('Duplicate Reviewer pair')
    ids=[r['template_id'] for r in gs]
    if any(i not in pairs for i in ids):raise ValueError('Missing paired R2R Reviewer')
    paired=[pairs[i] for i in ids]
    for g,r in zip(gs,paired):
        _verify(r,index[r['template_id']])
        if _source(g)!=_source(r):raise ValueError('Dynamic paired source mismatch')
    ds,de=_choose([r for r in rev if not r.get('pair_id')],text,index,core_rows('reviewer'),2,3,exclude=[_source(r) for r in paired])
    rids=[r['template_id'] for r in paired+ds]
    ge['projection']=_projection_receipts('generator',ids,{r['template_id']:r for r in gs})
    revidence=dict(paired=[dict(template_id=r['template_id'],pair_id=r['pair_id'],selection_reason='frozen_generator_pair') for r in paired],diagnostics=de,projection=_projection_receipts('reviewer',rids,{r['template_id']:r for r in paired+ds}))
    return dict(generator=ids,reviewer=rids,evidence={'generator':ge,'reviewer':revidence},source_sha256=digest(text.encode()),teaching_index_sha256=index_sha,policy='source_relation_complementarity')


def validate_selection(role,ids,mode='adaptive'):
    from host.template_selector import library
    if role not in ('generator','reviewer'):raise ValueError('Invalid R2R role')
    rows=library(role,'r2r-en');bank={r['template_id']:r for r in rows};index,_=teaching_index()
    if len(ids)!=len(set(ids)) or any(i not in bank for i in ids):raise ValueError('Invalid R2R selected IDs')
    for i in ids:_verify(bank[i],index[i])
    if mode=='all':
        if list(ids)!=[r['template_id'] for r in rows]:raise ValueError('Offline all mode must use the complete ordered library')
        return
    if mode!='adaptive':raise ValueError('Unknown selection mode')
    if role=='generator':
        if not 4<=len(ids)<=6:raise ValueError('R2R Generator requires 4..6 Dynamic examples')
        return
    ps=[i for i in ids if bank[i].get('pair_id')];ds=[i for i in ids if not bank[i].get('pair_id')]
    eligible={r['template_id']:r for r in library('generator','r2r-en')}
    if not 4<=len(ps)<=6 or not 2<=len(ds)<=3 or list(ids)!=ps+ds or any(bank[i]['pair_id'] not in eligible for i in ps):raise ValueError('R2R Reviewer requires ordered eligible pairs then diagnostics')
    for i in ps:
        if _source(bank[i])!=_source(eligible[bank[i]['pair_id']]):raise ValueError('Reviewer pair source mismatch')
