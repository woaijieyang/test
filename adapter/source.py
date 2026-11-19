"""Read-only source adapter for R2R English and RxR en-US.

The adapter extracts the instruction and stable task identity only. It never
normalizes whitespace, selects a cut, rewrites text, reads scores or passes GT
and trajectory metadata to either language model.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json, re
from shared.identity import need as _need, text_hash, ContractError


def need(test, message, **details):
    _need(test, message, module='adapter.source', **details)

PROFILES = {('R2R', 'en'): 'r2r-en', ('RxR', 'en-US'): 'rxr-en-us'}
DATASET_ALIASES = {
    'r2r': 'R2R', 'r2r_vlnce': 'R2R', 'r2r_vlnce_v1-3': 'R2R', 'room-to-room': 'R2R',
    'rxr': 'RxR', 'room-across-room': 'RxR',
}

def _dataset_name(value: Any) -> str:
    need(isinstance(value, str) and value.strip(), 'dataset must be explicit',
         code='SOURCE_DATASET_INVALID', path='/dataset', actual=value, expected='Nonblank dataset name')
    value = value.strip()
    return DATASET_ALIASES.get(value.lower(), value)

def _instruction_candidates(row: dict, dataset: str):
    found = []
    for key in ('original_instruction', 'instruction_text'):
        if key in row and row[key] is not None:
            found.append((key, row[key]))
    ins = row.get('instruction')
    if isinstance(ins, dict) and ins.get('instruction_text') is not None:
        found.append(('instruction.instruction_text', ins['instruction_text']))  # R2R VLN-CE nested field
    elif isinstance(ins, str):
        if dataset == 'RxR':
            found.append(('instruction', ins))  # RxR guide JSONL
        else:
            need(False, 'R2R instruction must be nested instruction.instruction_text or instruction_text',
                 code='SOURCE_FIELD_SHAPE_INVALID', path='/instruction', actual_type='str',
                 expected='Nested instruction.instruction_text or a canonical instruction_text field')
    return found

def _task_key(row: dict, dataset: str, language: str, split: str) -> str:
    explicit = row.get('task_key')
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    if dataset == 'R2R':
        episode = row.get('episode_id')
        need(episode is not None, 'R2R requires task_key or episode_id', code='SOURCE_ID_MISSING', path='/episode_id')
        return f'r2r:{split}:{episode}'
    instruction_id = row.get('instruction_id')
    need(instruction_id is not None, 'RxR requires task_key or instruction_id', code='SOURCE_ID_MISSING', path='/instruction_id')
    return f'rxr:{split}:{language}:{instruction_id}'

@dataclass(frozen=True)
class Source:
    key: str
    dataset: str
    language: str
    raw: str
    split: str = 'unspecified'
    provenance: dict | None = None  # Host-only IDs; never added to the LLM payload.

    def __post_init__(self):
        need((self.dataset, self.language) in PROFILES, 'Unsupported dataset/language profile', code='SOURCE_PROFILE_UNSUPPORTED', path='/language', actual=[self.dataset,self.language])
        need(isinstance(self.key, str) and self.key.strip(), 'Missing task key', code='SOURCE_ID_MISSING', path='/task_key')
        if self.provenance is None:
            object.__setattr__(self, 'provenance', {})
        need(isinstance(self.raw, str) and self.raw.strip(), 'Empty/blank source', code='SOURCE_TEXT_INVALID', path='/original_instruction')
        try:
            self.raw.encode('utf-8', errors='strict')
        except UnicodeEncodeError as e:
            raise ContractError('Source is not valid UTF-8 encodable text', code='SOURCE_ENCODING_INVALID', module='adapter.source', path='/original_instruction', start=e.start, end=e.end) from e

    @property
    def sha(self):
        return text_hash(self.raw)

    @property
    def edges(self):
        # Unicode code-point offsets into the decoded original; never trim the stored value.
        left = len(self.raw) - len(self.raw.lstrip())
        right = len(self.raw.rstrip())
        return left, right

    @property
    def profile(self):
        return PROFILES[self.dataset, self.language]

    @property
    def prefix(self):
        return self.raw[:self.edges[0]]

    @property
    def body(self):
        a, b = self.edges
        return self.raw[a:b]

    @property
    def suffix(self):
        return self.raw[self.edges[1]:]

    def outer_whitespace(self) -> tuple[str, str]:
        """Return the exact decoded leading and trailing Unicode whitespace, in order."""
        start, end = self.edges
        return self.raw[:start], self.raw[end:]

    def identity(self):
        return {'task_key': self.key, 'dataset': self.dataset, 'language': self.language,
                'split': self.split, 'source_sha256': self.sha, 'profile': self.profile,
                'provenance': dict(self.provenance or {})}

    def features(self):
        body, suffix = self.body, self.suffix
        return {
            'profile': self.profile, 'prefix': self.prefix, 'suffix': suffix,
            'body_CRLF': body.count('\r\n'), 'body_LF': '\n' in body,
            'suffix_LF': '\n' in suffix, 'any_LF': '\n' in self.raw,
            'body_double_space': '  ' in body, 'any_double_space': '  ' in self.raw,
            'suffix_only_ascii_spaces': bool(suffix) and not suffix.strip(' '),
            'suffix_exactly_one_space': suffix == ' ',
            'bare_CR': '\r' in self.raw.replace('\r\n', ''), 'has_TAB': '\t' in self.raw,
            'literal_backslash_n': '\\n' in self.raw,
            'no_space_after_punctuation': bool(re.search(r'[.!?][A-Za-z]', body)),
            'non_ascii': sorted({f'U+{ord(c):04X}' for c in self.raw if ord(c) > 127}),
        }

def from_record(row: dict, *, dataset: str | None = None, split: str | None = None) -> Source:
    """Accept canonical rows, R2R nested instruction objects, and RxR guide JSONL rows."""
    need(isinstance(row, dict), 'record must be a JSON object', code='SOURCE_RECORD_INVALID', path='', actual_type=type(row).__name__)
    ds = _dataset_name(dataset if dataset is not None else row.get('dataset'))
    need(ds in ('R2R','RxR'), 'Unsupported dataset', code='SOURCE_DATASET_UNSUPPORTED', path='/dataset', actual=ds, expected=['R2R','RxR'])
    language = row.get('language')
    if ds == 'R2R':
        language = language or 'en'  # VLN-CE R2R source rows may omit a language field.
        need(language == 'en', 'Only R2R English is in scope', code='SOURCE_LANGUAGE_UNSUPPORTED', path='/language', actual=language, expected='en')
    else:
        need(language == 'en-US', 'Only RxR en-US is in scope', code='SOURCE_LANGUAGE_UNSUPPORTED', path='/language', actual=language, expected='en-US')
    need((ds, language) in PROFILES, 'Unsupported dataset/language profile')
    candidates = _instruction_candidates(row, ds)
    need(bool(candidates), 'Instruction text not found', code='SOURCE_INSTRUCTION_MISSING', path='/instruction', checked_paths=['/original_instruction','/instruction_text','/instruction/instruction_text']+(['/instruction'] if ds=='RxR' else []))
    text = candidates[0][1]
    location='/' + candidates[0][0].replace('.', '/')
    need(isinstance(text, str) and text.strip(), 'Instruction must be nonblank text', code='SOURCE_TEXT_INVALID', path=location, actual_type=type(text).__name__, blank=isinstance(text,str) and not bool(text.strip()))
    encoding_path=location
    try:
        text.encode('utf-8', errors='strict')
        for name, value in candidates[1:]:
            encoding_path='/' + name.replace('.', '/')
            if isinstance(value,str):value.encode('utf-8', errors='strict')
    except UnicodeEncodeError as e:
        raise ContractError('Source field is not valid UTF-8 encodable text', code='SOURCE_ENCODING_INVALID', module='adapter.source', path=encoding_path, start=e.start, end=e.end) from e
    for name, value in candidates[1:]:
        need(value == text, f'Conflicting instruction fields: {candidates[0][0]} vs {name}',
             code='SOURCE_FIELDS_CONFLICT', path='/'+name.replace('.','/'), reference_path=location,
             actual_type=type(value).__name__, reference_sha256=text_hash(text),
             conflicting_sha256=text_hash(value) if isinstance(value,str) else None)
    digest = text_hash(text)
    supplied = row.get('source_sha256') or row.get('original_instruction_sha256')
    hash_path='/source_sha256' if row.get('source_sha256') else '/original_instruction_sha256'
    need(supplied is None or supplied == digest, 'Source SHA-256 mismatch', code='SOURCE_HASH_MISMATCH', path=hash_path, actual=supplied, expected=digest, source_path=location)
    sp = str(split if split is not None else row.get('split', 'unspecified'))
    key = _task_key(row, ds, language, sp)
    # Host-only provenance for split-overlap audits and paired evaluation.
    # This object is never serialized into Generator/Reviewer model messages.
    scene_value = row.get('scene_id') or row.get('scan')
    scan_id = row.get('scan')
    if not scan_id and isinstance(scene_value, str):
        scan_id = Path(scene_value).stem if scene_value.endswith('.glb') else scene_value
    provenance = {
        'record_id': str(row.get('id') if row.get('id') is not None else row.get('record_id')) if (row.get('id') is not None or row.get('record_id') is not None) else None,
        'episode_id': str(row.get('episode_id')) if row.get('episode_id') is not None else None,
        'instruction_id': str(row.get('instruction_id')) if row.get('instruction_id') is not None else None,
        'path_id': str(row.get('path_id')) if row.get('path_id') is not None else None,
        'trajectory_id': str(row.get('trajectory_id')) if row.get('trajectory_id') is not None else None,
        'scene_id': scene_value,
        'scan_id': scan_id,
        'source_record_role': row.get('role'),
    }
    return Source(key, ds, language, text, sp, provenance)

def load_record(path, *, dataset: str | None = None, split: str | None = None) -> Source:
    # Decode JSON bytes exactly once as UTF-8. Never use unicode_escape, strip,
    # split/join, NFC/NFKC or case normalization on the instruction value.
    try:
        raw = json.loads(Path(path).read_bytes().decode('utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        details={'code':'SOURCE_LOAD_FAILED','module':'adapter.source','path':'','file':str(path),'exception_type':type(e).__name__}
        if isinstance(e,json.JSONDecodeError):details.update(line=e.lineno,column=e.colno)
        raise ContractError('Cannot load source JSON record', **details) from e
    return from_record(raw, dataset=dataset, split=split)
