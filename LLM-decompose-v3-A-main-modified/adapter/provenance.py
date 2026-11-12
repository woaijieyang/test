"""Verifiable exact mappings, not inferred semantic alignments.
No fuzzy matching or guessed first repeated occurrence. Optional exact surface-token alignment is in alignment.py; it is not semantic parsing.
"""
from __future__ import annotations
from typing import Any, Sequence
import unicodedata
from .source import SourceRecord
from contracts.common import ProvenanceError, require

def exact_occurrences(source: SourceRecord, quote: str) -> list[tuple[int,int]]:
    if not quote:raise ProvenanceError('empty source fragment')
    hits=[];pos=source.body_start
    while True:
        at=source.original_instruction.find(quote,pos,source.body_end)
        if at<0:break
        hits.append((at,at+len(quote)));pos=at+1
    return hits

def unique_fragment(source: SourceRecord, quote: str, *, kind: str='COPY') -> dict[str,Any]:
    if kind not in {'COPY','MOVE'}:raise ProvenanceError('invalid fragment kind')
    hits=exact_occurrences(source,quote)
    if len(hits)!=1:raise ProvenanceError(f'fragment has {len(hits)} occurrences; use verified host offsets or edit classification, never guess')
    return {'kind':kind,'source_span':list(hits[0]),'text':quote,'origin':'verified_unique_exact_match'}

def explicit_fragment(source: SourceRecord, start: int, end: int, quote: str, *, kind: str='COPY') -> dict[str,Any]:
    if kind not in {'COPY','MOVE'}:raise ProvenanceError('invalid kind')
    if type(start) is not int or type(end) is not int or not source.body_start<=start<end<=source.body_end:
        raise ProvenanceError('source offsets outside the body')
    if source.original_instruction[start:end]!=quote:raise ProvenanceError('host span and source quote disagree')
    return {'kind':kind,'source_span':[start,end],'text':quote,'origin':'explicit_verified_host_span'}

def legal_boundary(text: str, pos: int) -> bool:
    """Do not make a stage boundary inside a word, contraction, number or combining cluster."""
    if pos <= 0 or pos >= len(text):return True
    left,right=text[pos-1],text[pos]
    word=lambda c: c.isalnum() or c=='_' or unicodedata.category(c).startswith('M')
    if word(left) and word(right):return False
    joins="'’‐‑-"
    if right in joins and word(left) and pos+1<len(text) and word(text[pos+1]):return False
    if left in joins and pos>1 and word(text[pos-2]) and word(right):return False
    if right=='.' and left.isdigit() and pos+1<len(text) and text[pos+1].isdigit():return False
    if left=='.' and pos>1 and text[pos-2].isdigit() and right.isdigit():return False
    return not (left=='\r' and right=='\n')

def boundary_partition(source: SourceRecord, subtasks: Sequence[str]) -> tuple[list[list[dict]],list[dict]] | None:
    """Exact ordered full-body coverage establishes unambiguous context, even for repeats.
    Only whitespace gaps (or zero-length gaps) may separate the chosen stages.
    """
    if not subtasks:return None
    cursor=source.body_start; stages=[];boundaries=[];s=source.original_instruction
    for i,text in enumerate(subtasks):
        if not text or text!=text.strip() or not s.startswith(text,cursor):return None
        end=cursor+len(text)
        if end>source.body_end:return None
        stages.append([explicit_fragment(source,cursor,end,text)])
        cursor=end
        if i<len(subtasks)-1:
            gap_start=cursor
            if not legal_boundary(s,cursor):raise ProvenanceError('Stage boundary splits a source token')
            while cursor<source.body_end and s[cursor].isspace():cursor+=1
            boundaries.append({'after_stage':i,'source_span':[gap_start,cursor],'old_text':s[gap_start:cursor],'new_text':'\n','origin':'approved_stage_boundary'})
    if cursor!=source.body_end:return None
    return stages,boundaries

def assembled_stage_maps(source: SourceRecord, subtasks: Sequence[str]) -> list[list[dict]]:
    # Unique whole-stage copies are provable. Other regions are EDIT, never fictitious COPY.
    all_hits=[exact_occurrences(source,t) for t in subtasks]
    uniques=[h[0] for h in all_hits if len(h)==1]
    moved=any(uniques[i][0]>uniques[i+1][0] for i in range(len(uniques)-1))
    result=[]
    for text,hits in zip(subtasks,all_hits):
        if len(hits)==1:
            op=explicit_fragment(source,*hits[0],text,kind='MOVE' if moved else 'COPY')
            op['origin']='verified_unique_whole_stage_match';result.append([op])
        else:
            result.append([{'kind':'EDIT','text':text,'origin':'ambiguous_exact_occurrences' if hits else 'unmapped_edit_region',
                            'possible_source_spans':[list(x) for x in hits]}])
    return result
