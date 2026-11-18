"""Hashes are over declared encodings; no stdout or end-of-line conversion."""
from __future__ import annotations
import hashlib, json

def text_hash(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def canonical(x: object) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def obj_hash(x: object) -> str:
    return text_hash(canonical(x))

class ContractError(ValueError): pass

def need(test, message):
    if not test: raise ContractError(message)
