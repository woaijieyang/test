"""Explicit author-side repairs for reviewed RxR teaching representations.

This module never participates in online judging. It normalizes authored local
coverage references and supplies exact, still-present evidence for two omission
lessons. Absence remains proved by the source/finding, not by fabricated quotes.
"""
from __future__ import annotations
import re
from tools.rxr_positive_repairs import evidence, field


def finalize(rows):
    for row in rows.values():
        if row['role'] != 'reviewer':
            continue
        audit = row['expected_review']
        coverage = audit['source_coverage']
        used = {c['requirement_id'] for c in coverage}
        if len(used) != len(coverage):
            raise ValueError(f"Duplicate requirement identity: {row['template_id']}")
        if 'SRC-CHANGE' in used:
            numbers = [int(x[4:]) for x in used if re.fullmatch(r'SRC-[0-9]{2,}', x)]
            replacement = f'SRC-{max(numbers, default=0) + 1:02d}'
            for c in coverage:
                if c['requirement_id'] == 'SRC-CHANGE':
                    c['requirement_id'] = replacement
            # Only structural references change; source and candidate text do not.
            for group in ('findings', 'stage_checks', 'handoffs'):
                for obj in audit.get(group, []):
                    obj['source_requirement_ids'] = [
                        replacement if x == 'SRC-CHANGE' else x
                        for x in obj.get('source_requirement_ids', [])
                    ]
        tid = row['template_id']
        if tid in ('RxR-DIAG-05', 'RxR-DIAG-15'):
            stages = row['review_input']['candidate']['subtasks']
            if tid == 'RxR-DIAG-05':
                quote = "once you're facing that shelf, you have reached your destination."
                text = ('The candidate retains the final shelf-facing completion condition. '
                        'Its missing initial orientation and hallway transition are established '
                        'by the source coverage and omission finding, not by an absent candidate quote.')
            else:
                quote = "Stand in front of the bidet, and you're done."
                text = ('The candidate retains the final bidet-front placement. This does not '
                        'restore the omitted turn-around, bathroom entry and hallway turn; '
                        'those missing events are identified by source evidence in the finding.')
            evidence(stages, 0, quote)
            audit['stage_checks'][0]['conditions'] = field(text, quote)
        # No unsupported mapping or permissive schema fallback is allowed.
        known = {c['requirement_id'] for c in coverage}
        if any(not re.fullmatch(r'SRC-[0-9]{2,}', x) for x in known):
            raise ValueError(f"Invalid authored coverage identity: {tid}")
        for group in ('findings', 'stage_checks', 'handoffs'):
            for obj in audit.get(group, []):
                if not set(obj.get('source_requirement_ids', [])) <= known:
                    raise ValueError(f"Unknown authored coverage reference: {tid}/{group}")
