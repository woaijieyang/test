"""Hashes are over declared encodings; no stdout or end-of-line conversion."""
from __future__ import annotations
import hashlib, json

def text_hash(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def canonical(x: object) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def obj_hash(x: object) -> str:
    return text_hash(canonical(x))

class ContractError(ValueError):
    """Backward-compatible error with optional, JSON-ready diagnostic context."""
    def __init__(self, message, **details):
        super().__init__(message)
        self.details = dict(details)

    def to_dict(self):
        return {'code': 'CONTRACT_VIOLATION', **self.details, 'message': str(self)}

def need(test, message, **details):
    if not test: raise ContractError(message, **details)
