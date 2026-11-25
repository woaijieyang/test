"""Validate R2R phase demonstrations before injection; never run authoring code.

The intentionally wrong R0 is valid protocol data, not a semantic gold label.
Only the expected G1/R1 output is required to pass its active phase contract.
"""
from copy import deepcopy
from functools import lru_cache
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = {('generator', 'repair'): 'r2r_repair_examples.json',
         ('reviewer', 'recheck'): 'r2r_recheck_examples.json'}


@lru_cache(maxsize=8)
def _validated(role, phase, raw, rule_bytes):
    from host import protocol
    data = json.loads(raw)
    if not isinstance(data, list) or not data:
        raise ValueError('Missing R2R phase demonstrations')
    active_rules = set(re.findall(r'^#{2,3} ([GR]-P[012](?:-[A-Z][0-9]?)?)\s+—', rule_bytes.decode('utf-8'), re.M))
    prefix = 'G-' if role == 'generator' else 'R-'
    seen = set()
    for item in data:
        if not isinstance(item, dict):
            raise ValueError('Invalid R2R phase demonstration')
        identity = item.get('id')
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError('Duplicate or empty R2R phase demonstration identity')
        seen.add(identity)
        if (item.get('phase') != phase or item.get('source_kind') != 'authored_synthetic'
                or item.get('is_official_dataset_record') is not False):
            raise ValueError('Wrong R2R phase demonstration identity/provenance')
        rules = item.get('rule_ids')
        if (not isinstance(rules, list) or not rules
                or any(not isinstance(r, str) or not r.startswith(prefix) or r not in active_rules for r in rules)
                or len(set(rules)) != len(rules)):
            raise ValueError('Invalid active rule link in R2R phase demonstration')
        task = item['input']
        source = task['original_instruction']
        if not isinstance(source, str) or not source.strip():
            raise ValueError('Empty R2R phase demonstration source')
        expected = item['expected_output']
        if role == 'generator':
            protocol.reviewer(source, task['candidate'], task['review'])
            protocol.feedback(source, task['review'], expected)
        else:
            protocol.reviewer(source, task['prior_candidate'], task['prior_review'],
                              rendered_instruction=task['prior_rendered_instruction'])
            protocol.reviewer(source, task['candidate'], expected,
                              rendered_instruction=task['rendered_instruction'],
                              prior_review=task['prior_review'],
                              prior_candidate=task['prior_candidate'],
                              prior_rendered_instruction=task['prior_rendered_instruction'])
    return data


def phase_examples(role, phase):
    """Read current bytes each time; cached validation cannot hide disk changes."""
    try:
        filename = FILES[(role, phase)]
    except KeyError as exc:
        raise ValueError('Unsupported R2R phase teaching request') from exc
    raw = (ROOT / role / 'dataset_rules' / filename).read_bytes()
    rules = (ROOT / role / 'dataset_rules/r2r_en.md').read_bytes()
    return deepcopy(_validated(role, phase, raw, rules))
