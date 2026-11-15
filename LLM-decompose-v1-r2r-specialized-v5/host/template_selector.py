"""Deterministic source-only retrieval for uploaded v1.5.2 teaching examples."""
from collections import Counter
from functools import lru_cache
from pathlib import Path
import json
import math
import re

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXAMPLES = None  # Automatically select 8..12.
PROFILES = {'r2r-en': 'R2R', 'rxr-en-us': 'RxR'}
PATTERNS = {
    'ordinal_target_selection': r'first|second|third|fourth|last|1st|2nd|3rd',
    'stairs_or_level_change': r'stairs?|staircase|stairway|landing|upstairs|downstairs',
    'return_or_revisit': r'return|again|retrace|backtrack|same|back to',
    'conditional_observation': r'if|otherwise|unless',
    'bounded_motion': r'steps?|halfway|paces?|feet|meters?',
    'doorway_selection_and_crossing': r'doors?|doorway|archway|entrance|threshold',
    'orientation_or_reference_frame': r'left|right|behind|facing|clockwise',
    'room_transition': r'enter|exit|leave|room|hallway',
    'intermediate_stop_or_wait': r'stop|wait|stand',
    'until': r'until', 'before': r'before', 'after': r'after|once|when',
    'correction': r'actually|sorry|i mean|instead', 'negation': r"not|never|without|don't",
    'endpoint': r'edge|end|base|bottom|top|foot|near|beside',
    'description': r'you will see|on your|there is|there are',
}
STOP = set('the an a is are it you your will of and to on with then that in at from there have be for this'.split())


def source(row):
    return (row.get('input') or row['review_input'])['original_instruction']


def normalized(text):
    return ' '.join(text.casefold().split())


def features(text):
    words = re.findall(r"[a-z]+", text.casefold())
    lex = {w for w in words if w not in STOP}
    cues = {name for name, pat in PATTERNS.items()
            if re.search(r'\b(?:' + pat + r')\b', text, re.I)}
    return cues, lex


@lru_cache(maxsize=4)
def library(role, profile):
    if role not in ('generator', 'reviewer') or profile not in PROFILES:
        raise ValueError('Unsupported role/profile')
    files = sorted((ROOT/role/'templates'/PROFILES[profile]).glob('*/*.json'))
    rows = [json.loads(f.read_bytes()) for f in files]
    if not rows or len({r['template_id'] for r in rows}) != len(rows):
        raise ValueError('Empty library or duplicate template IDs')
    return rows


def select_examples(role, profile, source_text, count=DEFAULT_EXAMPLES, mode='adaptive'):
    rows = library(role, profile)
    if mode == 'all':
        return [r['template_id'] for r in rows]
    if mode != 'adaptive':
        raise ValueError('Unknown selection mode')
    cues, words = features(source_text)
    if count is None:
        count = 8 + min(4, len(cues - {'orientation_or_reference_frame', 'room_transition', 'intermediate_stop_or_wait'}) // 2
                        + int(len(source_text.split()) >= 65))
    if type(count) is not int or not 1 <= count <= len(rows):
        raise ValueError('Invalid example count')
    options = []
    df = Counter()
    for row in rows:
        text = source(row)
        if normalized(text) == normalized(source_text):
            continue
        tags, terms = features(text)
        tags.update(row.get('retrieval_tags', []))
        df.update(tags | terms)
        options.append((row, tags, terms, normalized(text)))
    weight = {t: 1 + math.log((len(options)+1)/(freq+1)) for t, freq in df.items()}
    def relevance(item):
        row, tags, terms, _ = item
        return (sum(weight[t] for t in cues & tags) +
                sum(weight[t] for t in words & terms) / math.sqrt(max(1,len(terms))) -
                .12 * len(tags - cues))
    chosen, covered, verdicts = [], set(), set()
    while options and len(chosen) < count:
        def rank(item):
            row, tags, terms, _ = item
            verdict = row.get('expected_review', {}).get('verdict')
            return (relevance(item) + .8 * sum(weight[t] for t in (cues & tags) - covered)
                    + int(role == 'reviewer' and verdict not in verdicts))
        row, tags, _, identity = max(options, key=rank)
        chosen.append(row['template_id'])
        covered.update(tags)
        verdicts.add(row.get('expected_review', {}).get('verdict'))
        options = [x for x in options if x[3] != identity]
    return chosen
