"""Source-only relational example ranking, consulted exclusively by RxR."""
from __future__ import annotations

from collections import Counter
import math
import re

RELATION_PATTERNS = {
    'local_correction': r'\b(?:sorry|actually|i mean|or rather|rather once)\b',
    'conditional_viewpoint': r'\bif\b[^.;!?]{0,85}\b(?:look|turn|see|notice)\b',
    'conditional_route': r'\b(?:otherwise|unless)\b|\bif\b[^.;!?]{0,80}\b(?:closed|blocked|not open)\b',
    'paired_spatial_choice': r'\b(?:leftmost|rightmost)\b|\b(?:two|both)\b[^.;!?]{0,60}\b(?:doors?|doorways?|archways?|stairs?)\b',
    'terminal_refinement': r'\b(?:halfway|midway|one step|just one step|foot of|in front of|between)\b',
    'ordinal_origin': r'\b(?:first|second|third|last)\b[^.;!?]{0,40}\b(?:door|doorway|hallway|flight)\b',
    'bounded_step': r'\b(?:one|two|three|a|another|1|2|3)\s+(?:large\s+)?steps?\b',
    'return_identity': r'\b(?:return|retrace|backtrack|same door|walk back through|came from|of which you came)\b',
    'terminal_facing': r'\b(?:facing|looking at)\b[^.;!?]{0,150}\b(?:done|finished|destination)\b',
    'negative_entry': r"\b(?:do not|don't|without|never)\b[^.;!?]{0,45}\b(?:enter|through|outside|go)\b",
    'late_target_description': r'\b(?:it|the doorway|the door|that door)\s+(?:has|is|will)\b',
}


def features(text):
    """Return retrieval signals, never a segmentation decision or oracle label."""
    from host.template_selector import features as common_features
    cues, words = common_features(text)
    # Keep common matching unchanged for the other Profile. The old generic
    # if/otherwise cue must not teach that all conditional observations branch.
    cues.discard('conditional_observation')
    for name, pattern in RELATION_PATTERNS.items():
        if re.search(pattern, text, re.I):
            cues.add(name)
    tokens = re.findall(r"[a-z]+", text.casefold())
    phrases = Counter(tuple(tokens[i:i + 5]) for i in range(max(0, len(tokens) - 4)))
    if any(n > 1 for n in phrases.values()):
        cues.add('oral_repetition')
    return cues, words


def rank_examples(rows, text, count, excluded=()):
    """Relevance plus complementary relation coverage; stable ties, no verdict quotas.

    Core remains mandatory. Discount (not suppress) relational lessons already
    present in Core so Dynamic can add precision rather than merely echo nouns.
    A training example is never preferred just because it came from training.
    """
    from host.template_selector import source, normalized, relations
    from host.compile import core_library
    if type(count) is not int or count < 0:
        raise ValueError('Example count must be a nonnegative integer')
    cues, words = features(text)
    query_relations = relations(text)
    special = cues & (set(RELATION_PATTERNS) | {'oral_repetition'})
    blocked = {normalized(text), *(normalized(x) for x in excluded)}
    options, document_frequency = [], Counter()
    for row in rows:
        if row.get('dataset_scope') != 'RxR' or row.get('language') != 'en-US':
            raise ValueError('RxR retrieval received a foreign teaching record')
        identity = normalized(source(row))
        if identity in blocked:
            continue
        tags, terms = features(source(row))
        tags.update(row.get('retrieval_tags', []))
        document_frequency.update(tags | terms)
        options.append((row, identity, tags, terms))
    weights = {token: 1 + math.log((len(options) + 1) / (frequency + 1))
               for token, frequency in document_frequency.items()}
    role = rows[0]['role'] if rows else 'generator'
    core_covered = set()
    for row in core_library(role, 'rxr-en-us'):
        core_covered.update(features(source(row))[0] & special)
    candidates = []
    for row, identity, tags, terms in options:
        common = cues & tags
        exact_relations = query_relations & relations(source(row))
        relational_hits = special & tags
        score = (sum(weights[token] for token in common)
                 + sum(weights[token] for token in words & terms) / math.sqrt(max(1, len(terms)))
                 + 4 * len(exact_relations) + 2 * len(relational_hits)
                 - 0.12 * len(tags - cues))
        candidates.append((row, identity, score, relational_hits, exact_relations))
    chosen, covered, covered_links = [], set(), set()
    while candidates and len(chosen) < count:
        def utility(item):
            novelty = sum(0.5 if cue in core_covered else 1.0 for cue in item[3] - covered)
            return (-item[2] - 1.5 * novelty - 1.5 * len(item[4] - covered_links), item[0]['template_id'])
        row, identity, _, hits, links = min(candidates, key=utility)
        chosen.append(row)
        covered.update(hits)
        covered_links.update(links)
        candidates = [item for item in candidates if item[1] != identity]
    return chosen
