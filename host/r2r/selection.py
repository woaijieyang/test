"""Deterministic R2R teaching selection, not a semantic route parser."""
from pathlib import Path
from functools import lru_cache
import hashlib,json,re,math
from host.r2r.relations import facet_signals, FACET_PATTERNS, applicability
ROOT=Path(__file__).resolve().parents[2]
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
 'uncertainty':[r"\b(?:unclear|unknown|not sure|cannot tell|can't tell)\b"],
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
    for item in items:
        prefix='G-' if item['role']=='generator' else 'R-'
        if not item.get('rule_ids') or any(not r.startswith(prefix) for r in item['rule_ids']):raise ValueError('Missing or cross-role teaching-rule mapping')
        if not item.get('retrieval_skills') or set(item.get('facets',()))-set(FACET_PATTERNS):raise ValueError('Invalid teaching relation metadata')
        if 'required_query_facets' not in item:
            raise ValueError('Missing specialist applicability declaration')
        applicability(item, set())  # validate gate structure before any selection
        if item.get('teaching_polarity') not in ('generate','accept','detect','source_limitation'):raise ValueError('Invalid teaching polarity')
    return index

@lru_cache(maxsize=8)
def _linked_index(blob, generator_rules, reviewer_rules):
    # Cache by actual rule bytes as well as index bytes. A changed active rule
    # cannot keep an obsolete link alive via the already loaded index cache.
    index=_index_blob(blob)
    for role,raw in (('generator',generator_rules),('reviewer',reviewer_rules)):
        ids=set(re.findall(r'^#{2,3} ([GR]-P[012](?:-[A-Z][0-9]?)?)\s+—',raw.decode('utf-8'),re.M))
        if not ids:raise ValueError('Missing active R2R role rules: '+role)
        for item in index.values():
            if item['role']==role and set(item['rule_ids'])-ids:
                raise ValueError('Teaching refers to unknown active role rule: '+item['template_id'])
    return index


def teaching_index():
    blob=(ROOT/'host/r2r/teaching_index.json').read_bytes()
    rules=[(ROOT/role/'dataset_rules/r2r_en.md').read_bytes() for role in ('generator','reviewer')]
    return _linked_index(blob,*rules),digest(blob)

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


def _lesson_units(item, query_facets):
    """A positive example is not a negative contrast, even for the same facet."""
    polarity=item.get('teaching_polarity','unspecified')
    return {facet+'|'+polarity for facet in set(item.get('facets',())) & query_facets}


def _choose(rows,text,index,core,minimum,maximum,count=None,exclude=(),prior=(),source_family=None):
    if count is not None and (type(count) is not int or not minimum<=count<=maximum):
        raise ValueError(f'R2R count must be {minimum}..{maximum}')
    hits=signals(text);query=set(hits);facet_hits=facet_signals(text);query_facets=set(facet_hits)
    words=set(re.findall(r'[a-z]+',text.casefold()))
    core_focus=set();core_units=set();prior_units=set();prior_skills=set()
    for row in core:
        item=index[row['template_id']];_verify(row,item)
        core_focus.update(item.get('retrieval_skills',item['skills']))
        core_units.update(_lesson_units(item,query_facets))
    for row in prior:
        item=index[row['template_id']];_verify(row,item)
        prior_skills.update(query & set(item.get('retrieval_skills',item['skills'])))
        prior_units.update(_lesson_units(item,query_facets))
    options=[];excluded=[];blocked={normalized(text),*(normalized(x) for x in exclude)}
    for row in rows:
        tid=row['template_id'];item=index.get(tid)
        if item is None:raise ValueError('Missing R2R teaching metadata: '+tid)
        _verify(row,item)
        identity=normalized(_source(row));family=item.get('route_family')
        if item['status']!='dynamic':
            excluded.append(dict(template_id=tid,reason=item['status']));continue
        if identity in blocked:
            excluded.append(dict(template_id=tid,reason='same_source'));continue
        if source_family is not None and family==source_family:
            excluded.append(dict(template_id=tid,reason='same_route_family'));continue
        if not applicability(item, query_facets):
            excluded.append(dict(template_id=tid,reason='inapplicable_specialist',required_query_facets=item['required_query_facets']))
            continue
        matched=query & set(item.get('retrieval_skills',item['skills']))
        facets=query_facets & set(item.get('facets',()))
        terms=set(re.findall(r'[a-z]+',_source(row).casefold()))
        lexical=len(words&terms)/math.sqrt(max(1,len(terms)))
        options.append(dict(row=row,identity=identity,family=family,matched=matched,
                            facets=facets,units=_lesson_units(item,query_facets),lexical=lexical,
                            cost=len(_source(row).encode()),item=item))
    if len({x['family'] or x['identity'] for x in options})<(count or minimum):
        raise ValueError('Insufficient eligible R2R calibration library')
    selected=[];trace=[];covered=set();covered_units=set();ranking=[]
    initial_pool=sorted(x['row']['template_id'] for x in options)
    available_skills=set().union(*(x['matched'] for x in options)) if options else set()
    while options and len(selected)<(count or maximum):
        base=len(selected)<(count or minimum)
        def new_units(x):return x['units']-covered_units-core_units-prior_units
        def optional_skills(x):return x['matched']-covered-core_focus-prior_skills
        eligible=options if base else [x for x in options if new_units(x) or optional_skills(x)]
        if not eligible:break
        def components(x):
            novelty=x['matched']-covered
            # Core is a soft cost during mandatory selection; paired examples
            # reduce redundant diagnosis, not opposite-polarity contrasts.
            inc=_weight(novelty)-0.25*_weight(novelty&core_focus)-0.15*_weight(novelty&prior_skills)
            inc+=2*len(new_units(x))
            repeat=_weight(x['matched']&covered)+len(x['units']&(covered_units|prior_units))
            return inc,_weight(x['matched'])+len(x['facets']),repeat
        def key(x):
            inc,fit,repeat=components(x)
            return (not bool(x['matched'] or x['facets']),-inc,-fit,repeat,-.2*x['lexical'],x['cost'],x['row']['template_id'])
        ordered=sorted(eligible,key=key);best=ordered[0];tid=best['row']['template_id']
        ranking.append(dict(slot=len(selected),ordered_candidates=[dict(
            template_id=x['row']['template_id'],matched_skills=sorted(x['matched']),
            incremental_skills=sorted(x['matched']-covered),core_overlap=sorted(x['matched']&core_focus),
            incremental_score=components(x)[0],relation_score=components(x)[1],redundancy_score=components(x)[2],
            added_lesson_units=sorted(new_units(x)),matched_facets=sorted(x['facets']),
            lexical=round(x['lexical'],10),source_bytes=x['cost'],content_sha256=x['item']['content_sha256']) for x in ordered]))
        if count is not None:reason='explicit_count'
        elif base:reason='specific_complement' if best['matched'] or best['facets'] else 'broad_calibration'
        else:reason='uncovered_facet_or_contrast' if new_units(best) else 'uncovered_skill'
        trace.append(dict(template_id=tid,selection_reason=reason,
            matched_skills=sorted(best['matched']),added_coverage=sorted(best['matched']-covered),
            optional_coverage=sorted(optional_skills(best)) if not base else [],
            core_overlap=sorted(best['matched']&core_focus),matched_facets=sorted(best['facets']),
            applicability_basis='specialist_relation' if best['item'].get('required_query_facets') else 'general_calibration',
            required_query_facets=list(best['item'].get('required_query_facets', [])),
            added_lesson_units=sorted(new_units(best)),teaching_polarity=best['item'].get('teaching_polarity'),
            matched_source_spans={s:hits[s] for s in sorted(best['matched'])},
            matched_facet_spans={f:facet_hits[f] for f in sorted(best['facets'])}))
        selected.append(best['row']);covered.update(best['matched']);covered_units.update(best['units'])
        duplicates=[x for x in options if (x['identity']==best['identity'] or (best['family'] is not None and x['family']==best['family'])) and x['row']['template_id']!=tid]
        excluded.extend(dict(template_id=x['row']['template_id'],reason='selected_source_family',selected_id=tid) for x in duplicates)
        options=[x for x in options if x['identity']!=best['identity'] and (best['family'] is None or x['family']!=best['family'])]
    return selected,dict(selected=trace,excluded=excluded,ranking=ranking,eligible_pool=initial_pool,
        query_signals=hits,query_facets=facet_hits,prior_lesson_units=sorted(prior_units),
        unmatched_query_skills=sorted(query-available_skills-core_focus),
        source_family_exclusion_applied=source_family is not None)


def _projection_receipts(role,ids,bank):
    from host.r2r.teaching import card,dynamic_is_detailed
    from shared.identity import canonical
    out=[]
    for position,tid in enumerate(ids):
        detailed=dynamic_is_detailed(role,ids,position)
        payload=canonical(card(bank[tid],role,detailed))
        out.append(dict(template_id=tid,detailed=detailed,projection_utf8_bytes=len(payload.encode()),projection_sha256=digest(payload.encode())))
    return out


def select_bundle(text,count=None,*,source_family=None):
    from host.template_selector import library
    index,index_sha=teaching_index()
    gen=library('generator','r2r-en')
    gs,ge=_choose(gen,text,index,core_rows('generator'),4,6,count,source_family=source_family)
    rev=library('reviewer','r2r-en');pairs={r['pair_id']:r for r in rev if r.get('pair_id')}
    if len(pairs)!=sum(bool(r.get('pair_id')) for r in rev):raise ValueError('Duplicate Reviewer pair')
    ids=[r['template_id'] for r in gs]
    if any(i not in pairs for i in ids):raise ValueError('Missing paired R2R Reviewer')
    paired=[pairs[i] for i in ids]
    for g,r in zip(gs,paired):
        _verify(r,index[r['template_id']])
        if _source(g)!=_source(r):raise ValueError('Dynamic paired source mismatch')
    ds,de=_choose([r for r in rev if not r.get('pair_id')],text,index,core_rows('reviewer'),2,3,exclude=[_source(r) for r in paired],prior=paired,source_family=source_family)
    rids=[r['template_id'] for r in paired+ds]
    ge['fixed_core_overlap']=[dict(template_id=r['template_id'],match='exact_text' if normalized(_source(r))==normalized(text) else 'route_family') for r in core_rows('generator') if normalized(_source(r))==normalized(text) or (source_family is not None and index[r['template_id']].get('route_family')==source_family)]
    ge['fixed_core_overlap_policy']='reported_not_filtered; evaluation exclusion must be handled by the dataset protocol'
    ge['projection']=_projection_receipts('generator',ids,{r['template_id']:r for r in gs})
    revidence=dict(paired=[dict(template_id=r['template_id'],pair_id=r['pair_id'],selection_reason='frozen_generator_pair') for r in paired],diagnostics=de,projection=_projection_receipts('reviewer',rids,{r['template_id']:r for r in paired+ds}))
    return dict(generator=ids,reviewer=rids,evidence={'generator':ge,'reviewer':revidence},source_sha256=digest(text.encode()),teaching_index_sha256=index_sha,policy='source_relation_complementarity',core_source_overlaps=[r['template_id'] for role in ('generator','reviewer') for r in core_rows(role) if normalized(_source(r))==normalized(text)])


def validate_selection(role,ids,mode='adaptive',*,source_text=None):
    from host.template_selector import library
    if role not in ('generator','reviewer'):raise ValueError('Invalid R2R role')
    rows=library(role,'r2r-en');bank={r['template_id']:r for r in rows};index,_=teaching_index()
    if len(ids)!=len(set(ids)) or any(i not in bank for i in ids):raise ValueError('Invalid R2R selected IDs')
    for i in ids:_verify(bank[i],index[i])
    if mode=='all':
        if list(ids)!=[r['template_id'] for r in rows]:raise ValueError('Offline all mode must use the complete ordered library')
        return
    if mode!='adaptive':raise ValueError('Unknown selection mode')
    if source_text is not None:
        if not isinstance(source_text,str):raise TypeError('R2R source must be a string')
        facets=facet_signals(source_text)
        invalid=[tid for tid in ids if not applicability(index[tid],facets)]
        if invalid:raise ValueError('Inapplicable R2R specialist selection: '+repr(invalid))
    if role=='generator':
        if not 4<=len(ids)<=6:raise ValueError('R2R Generator requires 4..6 Dynamic examples')
        return
    ps=[i for i in ids if bank[i].get('pair_id')];ds=[i for i in ids if not bank[i].get('pair_id')]
    eligible={r['template_id']:r for r in library('generator','r2r-en')}
    if not 4<=len(ps)<=6 or not 2<=len(ds)<=3 or list(ids)!=ps+ds or any(bank[i]['pair_id'] not in eligible for i in ps):raise ValueError('R2R Reviewer requires ordered eligible pairs then diagnostics')
    for i in ps:
        if _source(bank[i])!=_source(eligible[bank[i]['pair_id']]):raise ValueError('Reviewer pair source mismatch')
