from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[1]

class ContractError(ValueError):
    """Technical or evidence-linkage violation; NOT a source-language verdict."""

class ProvenanceError(ContractError):
    """A claimed copied source range cannot be validated without guessing."""

def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8', errors='strict')).hexdigest()

def sha_obj(obj: Any) -> str:
    return sha_text(canonical_json(obj))

def require(test: bool, message: str) -> None:
    if not test:
        raise ContractError(message)

def parse_json(text: str) -> Any:
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ContractError(f'duplicate JSON key: {key}')
            result[key]=value
        return result
    def nonfinite(value):raise ContractError(f'nonfinite JSON constant: {value}')
    return json.loads(text,object_pairs_hook=pairs,parse_constant=nonfinite)

def read_json(path: Path) -> Any:
    return parse_json(path.read_bytes().decode('utf-8',errors='strict'))

def quote_in(quote: str, text: str, label: str) -> None:
    require(isinstance(quote, str) and bool(quote.strip()) and quote in text, f'{label}: exact nonblank quote not found')
