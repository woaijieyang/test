"""Deterministic data-set/role-specific few-shot selection. No LLM, GT, scores or trajectory access.

Select at most DEFAULT_EXAMPLES=8 on every role invocation: 3 stable core + 5
source-feature matches. The chosen IDs are frozen for G0/G1 and R0/R1.
The full 35-entry libraries remain available for explicitly controlled ablation.
"""
from __future__ import annotations
from pathlib import Path
from functools import lru_cache
import json,re,hashlib
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_EXAMPLES=8
CORE={
 'r2r-en':('R2R-01','R2R-05','R2R-12'),
 'rxr-en-us':('RXR-01','RXR-04','RXR-15'),
}
PROFILES={'r2r-en':'r2r.json','rxr-en-us':'rxr_en_us.json'}
PATTERNS={
 'ordinal':r'\b(first|second|third|next|last|[1-9](?:st|nd|rd|th))\b',
 'temporal_until':r'\buntil\b',
 'temporal_before':r'\bbefore\b',
 'temporal_after':r'\b(after|once|when)\b',
 'conditional':r'\b(if|otherwise|either|or)\b',
 'stop_pose':r'\b(stop|wait|halt|stand|face|facing)\b',
 'steps_stairs':r'\b(stair|stairs|step|steps|halfway|landing)\b',
 'return_history':r'\b(back|again|return|through the same)\b',
 'reference_frame':r'\b(left|right|behind|ahead|around|facing)\b',
 'door_identity':r'\b(door|doorway|entrance|opening|archway)\b',
 'terminal_approach':r'\b(towards?|near)\b',
 'crossing':r'\b(through|across|past|between|cross|pass)\b',
 'correction':r'\b(sorry|actually|i mean|rather than|no wait)\b',
 'description':r'\b(you see|you will see|looks like|there is|you are)\b',
}
@lru_cache(maxsize=4)
def library(role,profile):
    if role not in ('generator','reviewer') or profile not in PROFILES:raise ValueError('Unsupported role/profile')
    path=ROOT/role/'templates'/PROFILES[profile]
    rows=json.loads(path.read_text(encoding='utf-8'))
    assert len(rows)==35, f'Expected 35 curated examples in {path}, got {len(rows)}'
    ids=[r['example_id'] for r in rows]
    assert len(ids)==len(set(ids))
    return rows

def tags(s):return {k for k,p in PATTERNS.items() if re.search(p,s,re.I)}

def select_examples(role,profile,source_text,count=DEFAULT_EXAMPLES,mode='adaptive'):
    """Stable selection using source-only surface features; no semantic certificates.

    mode='all' explicitly takes the full library, never silently enabled by caller.
    """
    rows=library(role,profile)
    if mode not in ('adaptive','all'):raise ValueError('Unknown example selection mode')
    if mode=='all':return [r['example_id'] for r in rows]
    if type(count) is not int or not 1<=count<=35:raise ValueError('example_count must be 1..35')
    base=tuple(x.replace('R2R-','R2R-REVIEW-').replace('RXR-','RXR-REVIEW-') for x in CORE[profile]) if role=='reviewer' else CORE[profile]
    index={r['example_id']:r for r in rows}
    current=tags(source_text);source_sha=hashlib.sha256(source_text.encode()).hexdigest()
    excluded={r['example_id'] for r in rows if r['input']['original_instruction']==source_text or r['provenance']['source_sha256']==source_sha}
    chosen=[x for x in base if x not in excluded][:count]
    options=[]
    for j,r in enumerate(rows):
        rid=r['example_id']
        if rid in excluded or rid in chosen:continue
        rec_tags=set(r.get('selection_tags',[])) or tags(r['input']['original_instruction'])
        intersection=current&rec_tags
        score=8*len(intersection) - max(0,len(rec_tags-current))
        # Prefer coverage of hard conditions over lexical overlap with a generic 'turn'.
        score += 4*len(intersection & {'ordinal','temporal_until','temporal_before','conditional','return_history','correction'})
        options.append((-score,j,rid,rec_tags))
    options.sort(key=lambda t:(t[0],t[1]))
    while len(chosen)<count and options:
        best=None
        selected_tags=set().union(*(set(index[x].get('selection_tags',[])) or tags(index[x]['input']['original_instruction']) for x in chosen)) if chosen else set()
        for i,(negscore,j,rid,rec_tags) in enumerate(options):
            score=-negscore
            marginal=len((rec_tags&current)-selected_tags)
            val=score+3*marginal
            if best is None or val>best[0]:best=(val,i)
        chosen.append(options.pop(best[1])[2])
    return chosen
