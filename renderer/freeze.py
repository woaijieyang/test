"""Freeze reviewed text once. Conservative mechanical lexical matching is NOT a semantic proof."""
from __future__ import annotations
import re
from dataclasses import dataclass
from collections import defaultdict
from adapter.source import Source
from shared.identity import canonical,obj_hash,text_hash,need
# Whitespace around a decimal point, apostrophe or intra-word hyphen can
# change a route token. Treat intact compounds as single comparison tokens.
TOK = re.compile(r"\d+(?:\.\d+)+|\w+(?:['’-]\w+)*|[^\w\s]", re.UNICODE)
@dataclass(frozen=True)
class Preview:
    key:str
    source_sha256:str
    mode:str
    rendered:str
    stages:tuple[str,...]
    ledger_json:str
    @property
    def sha(self):return text_hash(self.rendered)
    @property
    def snapshot(self):return obj_hash([self.key,self.source_sha256,self.mode,self.rendered,self.stages,self.ledger_json])

def _own_source(src):
    a,b=src.edges
    return Preview(src.key,src.sha,'SOURCE_EXACT',src.raw,(src.raw,),canonical({'source_envelope':[a,b],'spans_unit':'Unicode code points, 0-based, half-open in decoded source','events':[{'op':'COPY','src':[0,len(src.raw)],'dst':[0,len(src.raw)]}],'cuts':[],'unused_source':[]}))

def unchanged(src):return _own_source(src)

def _tokens(text):
    return [m.group() for m in TOK.finditer(text)]


# ASCII full stops delimit comparison units, except inside decimal numbers.
SENTENCE = re.compile(r'.+?(?:(?<!\d)\.|\.(?!\d)|\Z)', re.DOTALL)


def _units(text):
    for match in SENTENCE.finditer(text):
        raw = match.group()
        body = raw.strip()
        if body:
            start = match.start() + len(raw) - len(raw.lstrip())
            yield start, start + len(body), body


def freeze(src: Source, parts: list[str], separator: str = '\n') -> Preview:
    """Freeze accepted stage boundaries and restore formatting of unchanged text."""
    need(separator in ('\n', ' '), 'Unknown separator')
    need(isinstance(parts, list) and parts and all(isinstance(p, str) and p.strip() for p in parts),
         'Empty/invalid plan')
    rows = [p.strip() for p in parts]
    start, end = src.edges
    body = src.body
    source_tokens = list(TOK.finditer(body))
    stage_tokens = [_tokens(row) for row in rows]
    ordered = [word for stage in stage_tokens for word in stage] == [m.group() for m in source_tokens]

    source_units = defaultdict(list)
    for a, b, text in _units(body):
        source_units[tuple(_tokens(text))].append((a, b))
    events, cuts, built = [], [], []
    dst, token_index = start, 0
    last_source_end = None
    last_stage_end = None
    for stage, row in enumerate(rows):
        first_source = None
        pieces = []
        previous_end = 0
        previous_source_end = None
        if ordered:
            first = source_tokens[token_index].start()
            token_index += len(stage_tokens[stage])
            last = source_tokens[token_index - 1].end()
            units = [(0, len(row), row, [(first, last)])]
        else:
            units = [(a, b, text, source_units.get(tuple(_tokens(text)), []))
                     for a, b, text in _units(row)]
        for a, b, text, matches in units:
            span = matches[0] if len(matches) == 1 else None
            gap = row[previous_end:a]
            if previous_source_end is not None and span and span[0] >= previous_source_end:
                native_gap = body[previous_source_end:span[0]]
                if not native_gap.strip():
                    gap = native_gap
            if gap:
                pieces.append(gap)
                events.append(dict(op='SEAM', stage=stage, dst=[dst, dst + len(gap)], value=gap))
                dst += len(gap)
            value = body[slice(*span)] if span else text
            op = 'EDIT' if not span else 'MOVE' if last_source_end is not None and span[0] < last_source_end else 'COPY'
            events.append(dict(op=op, stage=stage, proposed=text, value=value,
                               src=[start + n for n in span] if span else None,
                alternatives=[[start + a, start + b] for a, b in matches] if not span else [],
                dst=[dst, dst + len(value)]))
            if not pieces:
                first_source = span[0] if span else None
            pieces.append(value)
            dst += len(value)
            previous_end = b
            previous_source_end = span[1] if span else None
            if span:
                last_source_end = span[1]
        if stage:
            if last_stage_end is not None and first_source is not None and first_source >= last_stage_end:
                native_gap = body[last_stage_end:first_source]
                if not native_gap.strip():
                    cuts[-1].update(src=[start + last_stage_end, start + first_source], old=native_gap)
        built.append(''.join(pieces))
        last_stage_end = previous_source_end
        if stage + 1 < len(rows):
            cuts.append(dict(after_stage=stage, src=None, old=None, new=separator, dst=[dst, dst + len(separator)]))
            dst += len(separator)
    # Stage boundaries and internal formatting are settled. Only the source
    # owns the outer envelope, including when a candidate supplied it already.
    rendered = src.prefix + separator.join(built) + src.suffix
    if ordered and len(rows) == 1:
        # Preserve the existing SOURCE_EXACT preview/ledger contract.
        return Preview(src.key, src.sha, 'SOURCE_EXACT', rendered, (rendered,), _own_source(src).ledger_json)
    mode = 'BOUNDARY_ONLY' if ordered else 'ASSEMBLED_SINGLE' if len(rows) == 1 else 'ASSEMBLED_MULTI'
    ledger = dict(source_envelope=[start, end], events=events, cuts=cuts, spans_unit='Unicode code points')
    return Preview(src.key, src.sha, mode, rendered, tuple(built), canonical(ledger))
