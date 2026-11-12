"""Conservative surface alignment BEFORE review; never infer route meaning.

Only exact, case/punctuation-sensitive token runs are matched. A unique run can
restore the source's whitespace, without changing the candidate's lexical tokens.
Ties never select the first occurrence. This is surface correspondence, NOT author
intent, event identity, semantic entailment, or a completion certificate.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any
import re
from .source import SourceRecord
from .provenance import exact_occurrences, explicit_fragment
from contracts.common import ProvenanceError

TOKEN = re.compile(r"\w+(?:['’\-\u2010\u2011]\w+)*|[^\w\s]", re.UNICODE)

def _ordinary(text: str) -> bool:
    return not any(c.isspace() and c != ' ' for c in text) and '  ' not in text

def align_stages(source: SourceRecord, stages: list[str]) -> tuple[list[str], list[list[dict[str, Any]]], list[dict[str, Any]]]:
    """Return prepared stage text, exact maps and logged whitespace restorations.

    Supports mixed COPY/MOVE and EDIT while failing closed where nonordinary
    source spacing has multiple different plausible origins. It never fuzzily
    matches synonyms, case changes, punctuation changes or token reordering.
    """
    raw = source.original_instruction
    sm = list(TOKEN.finditer(raw, source.body_start, source.body_end))
    sw = [m.group() for m in sm]
    occur: dict[str, list[int]] = defaultdict(list)
    for j, w in enumerate(sw):
        occur[w].append(j)
    result: list[str] = []
    mapped: list[list[dict[str, Any]]] = []
    ledger: list[dict[str, Any]] = []
    for stage_index, draft in enumerate(stages):
        if not draft or draft != draft.strip():
            raise ProvenanceError('Authored stage edges must be explicit; no silent trimming')
        whole = exact_occurrences(source, draft)
        if len(whole) == 1:
            op = explicit_fragment(source, *whole[0], draft)
            op['origin'] = 'verified_unique_whole_stage_match'
            result.append(draft); mapped.append([op]); continue
        tm = list(TOKEN.finditer(draft)); tw = [m.group() for m in tm]
        if not tm:
            raise ProvenanceError('Stage has no non-whitespace content')
        chunks: list[dict] = []
        i = 0
        while i < len(tm):
            best, starts = 0, []
            for j in occur.get(tw[i], []):
                n = 0
                while i+n < len(tw) and j+n < len(sw) and tw[i+n] == sw[j+n]:
                    n += 1
                if n > best:
                    best, starts = n, [j]
                elif n == best:
                    starts.append(j)
            n = best or 1
            a, b = tm[i].start(), tm[i+n-1].end()
            proposal = draft[a:b]
            ranges = [(sm[j].start(), sm[j+n-1].end()) for j in starts]
            # A common one-word or punctuation match is not enough provenance.
            informative = sum(any(c.isalnum() for c in w) for w in tw[i:i+n]) >= 2
            if len(starts) == 1 and informative:
                u, v = ranges[0]
                native = raw[u:v]
                # Changed gaps may be ordinary missing/single spaces only; new
                # TAB/CRLF/double-space must not be laundered as a source copy.
                for k in range(1, n):
                    pgap = draft[tm[i+k-1].end():tm[i+k].start()]
                    sgap = raw[sm[starts[0]+k-1].end():sm[starts[0]+k].start()]
                    if pgap != sgap and not _ordinary(pgap):
                        raise ProvenanceError('Candidate introduced unverified nonstandard spacing inside a source run')
                op = explicit_fragment(source, u, v, native)
                op['origin'] = 'unique_exact_token_run_surface_only'
                op['draft_span'] = [a, b]
                if native != proposal:
                    ledger.append({'kind':'SOURCE_WHITESPACE_RESTORED_BEFORE_REVIEW', 'stage':stage_index,
                                   'source_span':[u,v], 'draft_text':proposal, 'prepared_text':native,
                                   'scope':'Whitespace only; unique surface match, not semantic evidence'})
            else:
                if len(ranges) > 1 and informative:
                    strings = {raw[u:v] for u,v in ranges}
                    if len(strings) > 1 and any(not _ordinary(t) for t in strings):
                        raise ProvenanceError('Repeated source run has differing native whitespace; supply verified explicit maps or exact fallback')
                op = {'kind':'EDIT','text':proposal,'origin':'ambiguous_surface_match' if ranges else 'unmapped_edit_region',
                      'possible_source_spans':[list(x) for x in ranges], 'draft_span':[a,b]}
            chunks.append(op)
            i += n
        ops: list[dict] = []
        for k, op in enumerate(chunks):
            if k:
                prev = chunks[k-1]
                gap = draft[prev['draft_span'][1]:op['draft_span'][0]]
                u = prev.get('source_span'); v = op.get('source_span')
                if u is not None and v is not None and u[1] <= v[0] and not raw[u[1]:v[0]].strip():
                    native = raw[u[1]:v[0]]
                    if gap != native and not _ordinary(gap):
                        raise ProvenanceError('Unverified special spacing at a copied seam')
                    if native:
                        seam = explicit_fragment(source, u[1], v[0], native)
                        seam['origin'] = 'verified_adjacent_source_gap'
                        ops.append(seam)
                    if gap != native:
                        ledger.append({'kind':'SOURCE_WHITESPACE_RESTORED_BEFORE_REVIEW','stage':stage_index,
                                       'source_span':[u[1],v[0]], 'draft_text':gap,'prepared_text':native,
                                       'scope':'Source-adjacent gap only'})
                elif gap:
                    if gap != ' ':
                        raise ProvenanceError('New/unmapped fragment gap must be one ASCII space')
                    ops.append({'kind':'SEAM','text':gap,'origin':'authored_new_seam'})
            ops.append(op)
        # Merge adjacent edits so final validation can reject noncanonical edit spacing.
        coalesced: list[dict] = []
        for op in ops:
            if coalesced and coalesced[-1]['kind']=='EDIT' and op['kind']=='EDIT':
                coalesced[-1]['text'] += op['text']
            else:
                coalesced.append(op)
        text = ''.join(op['text'] for op in coalesced)
        if [m.group() for m in TOKEN.finditer(text)] != tw:
            raise ProvenanceError('Surface preparation attempted a lexical change')
        result.append(text); mapped.append(coalesced)
    # COPY/MOVE expresses surface ordering only. Reuse is explicitly not a new event.
    positions=[op['source_span'][0] for st in mapped for op in st if op['kind']=='COPY']
    moved=any(a>b for a,b in zip(positions,positions[1:]))
    seen=set()
    for st in mapped:
        for op in st:
            if op['kind']=='COPY':
                key=tuple(op['source_span']);op['source_span_reused']=key in seen;seen.add(key)
                if moved:op['kind']='MOVE'
    return result, mapped, ledger
