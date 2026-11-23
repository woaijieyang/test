"""Exact offline evidence projection through one authored candidate edit.

A repeated phrase is not silently assigned to its first occurrence when the
possible occurrences have different mutation effects. This checks text
alignment, not semantic entailment or navigation quality.
"""
from __future__ import annotations


def mapped_quote(source, candidate, quote, start, old, new, *, occurrence=None):
    if not all(isinstance(x, str) for x in (source, candidate, quote, old, new)):
        raise ValueError('Evidence projection requires exact strings')
    if not quote or not old or old == new or isinstance(start, bool) or not isinstance(start, int):
        raise ValueError('Evidence projection requires a nonempty quote and a real authored edit')
    end_edit = start + len(old)
    if start < 0 or source[start:end_edit] != old or candidate != source[:start] + new + source[end_edit:]:
        raise ValueError('Candidate does not match the single declared edit')
    positions = []
    pos = source.find(quote)
    while pos >= 0:
        positions.append(pos)
        pos = source.find(quote, pos + 1)
    if not positions:
        raise ValueError('Cannot locate exact evidence occurrence: ' + repr(quote))
    if occurrence is not None:
        if isinstance(occurrence, bool) or not isinstance(occurrence, int) or occurrence not in positions:
            raise ValueError('Explicit evidence occurrence is not an exact quote start')
        positions = [occurrence]
    shift = len(new) - len(old)
    projected = []
    for pos in positions:
        end = pos + len(quote)
        touched = pos < end_edit and end > start
        left = pos if pos <= start else pos + shift if pos >= end_edit else start
        right = end if end <= start else end + shift if end >= end_edit else start + len(new)
        value = candidate[left:right]
        if not touched and value != quote:
            raise ValueError('Unchanged evidence projection drifted')
        projected.append((value, touched, pos))
    if len({(value, touched) for value, touched, _ in projected}) > 1:
        raise ValueError('Ambiguous repeated evidence crosses different events; author an exact occurrence or a longer quote')
    return projected[0]
