"""R2R-only complementary teaching selection; never a semantic planner.

The caller supplies validated libraries and feature extractors. No compiler or
runtime imports are allowed here, so offline and live selection share one path.
"""
from collections import Counter
import math

# Only grounded relationship signals can justify optional extra examples.
SPECIFIC = frozenset({
    'transit_continuation', 'attribute_description', 'hallway_endpoint_turn',
    'endpoint_refinement', 'ordinal_navigation', 'terminal_relation',
    'doorway_crossing', 'conditional_observation', 'negation',
    'return_or_revisit', 'bounded_motion', 'correction', 'path_branch',
})


def _source(row):
    return (row.get('input') or row['review_input'])['original_instruction']


def _normal(text):
    return ' '.join(text.casefold().split())


def _signals(text, feature_fn, relation_fn):
    cues, words = feature_fn(text)
    relations = relation_fn(text)
    signals = {'cue:' + key for key in cues}
    signals.update('relation:' + '|'.join(key) for key in relations)
    important = {'cue:' + key for key in cues & SPECIFIC}
    important.update('relation:' + '|'.join(key) for key in relations)
    return signals, important, words


def _prepare(rows, text, core, feature_fn, relation_fn, excluded):
    query, important, words = _signals(text, feature_fn, relation_fn)
    core_coverage = set()
    for row in core:
        signals, _, _ = _signals(_source(row), feature_fn, relation_fn)
        core_coverage.update(query & signals)
    blocked = {_normal(text), *(_normal(item) for item in excluded)}
    options, frequencies = [], Counter()
    for row in rows:
        identity = _normal(_source(row))
        if identity in blocked:
            continue
        signals, _, terms = _signals(_source(row), feature_fn, relation_fn)
        frequencies.update(terms)
        options.append((row, identity, signals & query, terms))
    weights = {term: 1 + math.log((len(options) + 1) / (n + 1))
               for term, n in frequencies.items()}
    ranked = []
    for row, identity, coverage, terms in options:
        lexical = sum(weights[t] for t in words & terms) / math.sqrt(max(1, len(terms)))
        precise = len(coverage & important)
        core_overlap = len(coverage & core_coverage) / max(1, len(coverage))
        score = 2 * len(coverage) + 3 * precise + lexical - .75 * core_overlap
        ranked.append(dict(row=row, identity=identity, coverage=coverage,
                           score=score, cost=len(_source(row).split())))
    return ranked, important, core_coverage


def select(rows, text, *, minimum, maximum, core, feature_fn, relation_fn,
           evidence_fn, count=None, excluded=()):
    """Select a deterministic base set; add extras only for uncovered relations.

    Explicit counts are supported for callers needing a frozen configuration;
    adaptive production selection is not driven by instruction length. Core
    overlap is a soft penalty, not a reason to exclude a closer demonstration.
    """
    if count is not None and (type(count) is not int or not minimum <= count <= maximum):
        raise ValueError(f'R2R example count must be an integer in {minimum}..{maximum}')
    options, important, core_coverage = _prepare(
        rows, text, core, feature_fn, relation_fn, excluded)
    chosen, covered, trace = [], set(), []
    limit = maximum if count is None else count
    while options and len(chosen) < limit:
        uncovered = important - core_coverage - covered
        base_required = len(chosen) < (minimum if count is None else count)
        eligible = options if base_required else [r for r in options if r['coverage'] & uncovered]
        if not eligible:
            break
        def key(item):
            gain = item['coverage'] - covered
            complement = gain - core_coverage
            return (-(item['score'] + 1.5 * len(gain) + len(complement)),
                    item['cost'], item['row']['template_id'])
        winner = min(eligible, key=key)
        row, coverage = winner['row'], winner['coverage']
        extra = sorted(coverage & uncovered)
        trace.append({
            'template_id': row['template_id'],
            'selection_reason': ('configured_count' if count is not None else
                                 'base_complement' if base_required else 'uncovered_relation'),
            'added_coverage': sorted(coverage - covered),
            'core_overlap': sorted(coverage & core_coverage),
            'optional_coverage': extra if not base_required else [],
            'matched_source_spans': evidence_fn(text, coverage),
        })
        chosen.append(row)
        covered.update(coverage)
        options = [item for item in options if item['identity'] != winner['identity']]
    if len(chosen) < (minimum if count is None else count):
        raise ValueError('Insufficient source-disjoint R2R teaching examples')
    return chosen, trace


def explain(rows, text, ids, *, minimum, core, feature_fn, relation_fn, evidence_fn):
    """Describe the supplied frozen ordering, never silently select a new set."""
    options, important, core_coverage = _prepare(rows, text, core, feature_fn, relation_fn, ())
    by_id = {item['row']['template_id']: item for item in options}
    trace, covered = [], set()
    for position, template_id in enumerate(ids):
        if template_id not in by_id:
            raise ValueError(f'R2R selection is not source-disjoint: {template_id}')
        item = by_id[template_id]
        coverage = item['coverage']
        new = coverage & (important - covered - core_coverage)
        trace.append(dict(template_id=template_id,
                          selection_reason='base_complement' if position < minimum else
                          'uncovered_relation' if new else 'explicit_frozen_selection',
                          added_coverage=sorted(coverage - covered),
                          core_overlap=sorted(coverage & core_coverage),
                          optional_coverage=sorted(new) if position >= minimum else [],
                          matched_source_spans=evidence_fn(text, coverage)))
        covered.update(coverage)
    return trace
